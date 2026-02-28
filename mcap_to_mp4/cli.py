#!/usr/bin/env python3
# https://github.com/Tiryoh/mcap-to-mp4
# Copyright 2024-2026 Daisuke Sato <tiryoh@gmail.com>
# MIT License

import argparse
import io
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from statistics import mean, median
from typing import List, Optional

import imageio
import mcap
import numpy as np
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory
from PIL import Image

IMAGE_SCHEMAS = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
NANOSECONDS_PER_SECOND = 1_000_000_000
DEFAULT_FALLBACK_FPS = 30.0
MAX_GAP_MULTIPLIER = 10.0
MEMORY_CHECK_INTERVAL = 100
KB_PER_MB = 1024
BYTES_PER_MB = 1024 * 1024


class Spinner:
    """Animated spinner for terminal output."""

    def __init__(self, message="Processing"):
        self._message = message
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._count = 0

    @property
    def count(self):
        with self._lock:
            return self._count

    @count.setter
    def count(self, value):
        with self._lock:
            self._count = value

    def _spin(self):
        for char in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop_event.is_set():
                break
            print(f"\r{char} {self._message} ({self.count} frames found)", end="", flush=True)
            time.sleep(0.1)

    def start(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        print()


def print_progress_bar(current, total, memory_mb=None, bar_length=40):
    if total == 0:
        return
    fraction = current / total
    filled = int(bar_length * fraction)
    bar = "█" * filled + "░" * (bar_length - filled)
    mem_str = f" | Memory: ~{memory_mb:.0f} MB" if memory_mb is not None else ""
    print(f"\r  [{bar}] {current}/{total} frames ({fraction:.0%}){mem_str}   ", end="", flush=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="input bag file path to read")
    parser.add_argument("-t", "--topic", help="topic name to convert." +
                        "if not specified, the topic list will be shown")
    parser.add_argument("-o", "--output", help="output file name", default="output.mp4")
    parser.add_argument("--timestamp-timing", action="store_true",
                        help="use sensor_msgs/Image.header.stamp based VFR timing")
    return parser.parse_args()


def check_file_exists(file_path: os.PathLike) -> None:
    if not os.path.isfile(file_path):
        raise RuntimeError("File does not exist")


def get_image_topic_list(mcap_file_path: str) -> List[str]:
    topic_list = []
    with open(mcap_file_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        if summary is None:
            return []
        schemas = summary.schemas
        for channel in summary.channels.values():
            schema = schemas.get(channel.schema_id)
            if schema is not None and schema.name in IMAGE_SCHEMAS:
                topic_list.append(channel.topic)
    return list(set(topic_list))


def _sanitize_path(file_path: str) -> str:
    """Validate that a file path does not contain shell-dangerous characters."""
    dangerous_chars = set(";|&`$(){}[]!#~")
    if any(c in dangerous_chars for c in file_path):
        raise ValueError(f"Invalid characters in file path: {file_path}")
    return file_path


def get_header_stamp_ns(ros_msg) -> Optional[int]:
    header = getattr(ros_msg, "header", None)
    stamp = getattr(header, "stamp", None)
    if stamp is None:
        return None

    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if nanosec is None:
        nanosec = getattr(stamp, "nsec", None)
    if sec is None or nanosec is None:
        return None

    try:
        return int(sec) * NANOSECONDS_PER_SECOND + int(nanosec)
    except (TypeError, ValueError):
        return None


def build_vfr_durations_ns(timestamps_ns: List[int]) -> List[int]:
    if len(timestamps_ns) == 0:
        return []

    fallback_duration_ns = int(NANOSECONDS_PER_SECOND / DEFAULT_FALLBACK_FPS)
    if len(timestamps_ns) == 1:
        return [fallback_duration_ns]

    raw_deltas = [timestamps_ns[i + 1] - timestamps_ns[i] for i in range(len(timestamps_ns) - 1)]
    positive_deltas = [d for d in raw_deltas if d > 0]
    reference_duration_ns = (
        int(median(positive_deltas)) if positive_deltas else fallback_duration_ns
    )

    durations_ns: List[int] = []
    for index, raw_delta in enumerate(raw_deltas, start=1):
        max_gap_ns = max(int(reference_duration_ns * MAX_GAP_MULTIPLIER), reference_duration_ns)

        if raw_delta <= 0:
            adjusted_delta = reference_duration_ns
            print(f"Warning: non-increasing timestamp at frame index {index}. "
                  f"Clamped to {adjusted_delta} ns.")
        elif raw_delta > max_gap_ns:
            adjusted_delta = max_gap_ns
            print(f"Warning: large timestamp gap at frame index {index}. "
                  f"Clamped from {raw_delta} ns to {adjusted_delta} ns.")
        else:
            adjusted_delta = raw_delta

        durations_ns.append(adjusted_delta)
        reference_duration_ns = adjusted_delta

    durations_ns.append(reference_duration_ns)
    return durations_ns


def quote_concat_path(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"


def encode_vfr(output_file: str, image_paths: List[str], durations_ns: List[int]) -> None:
    if len(image_paths) != len(durations_ns):
        raise RuntimeError("Image path and duration counts do not match")

    with tempfile.TemporaryDirectory(prefix="mcap_to_mp4_vfr_") as temp_dir:
        list_path = os.path.join(temp_dir, "list.txt")
        with open(list_path, "w", encoding="utf-8") as list_file:
            for image_path, duration_ns in zip(image_paths, durations_ns):
                list_file.write(f"file {quote_concat_path(image_path)}\n")
                list_file.write(f"duration {duration_ns / NANOSECONDS_PER_SECOND:.9f}\n")
            # Repeat the last file so concat demuxer applies the last duration.
            list_file.write(f"file {quote_concat_path(image_paths[-1])}\n")

        ffmpeg_command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-vsync", "vfr",
            "-pix_fmt", "yuv420p",
            output_file,
        ]

        try:
            subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg command is not available") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg failed: {e.stderr.strip()}") from e


def _get_peak_memory_mb():
    """Get peak RSS in MB (self + children)."""
    try:
        import resource
        rss_self = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        rss = rss_self + rss_children
        # ru_maxrss is in bytes on macOS, kilobytes on Linux
        if sys.platform == 'darwin':
            return rss / BYTES_PER_MB
        else:
            return rss / KB_PER_MB
    except (ValueError, OSError, ImportError):
        return None


def _decode_frame(schema, ros_msg):
    """Decode a single frame from a ROS message. Returns (img, img_channel, used_encoding)."""
    if schema.name == "sensor_msgs/msg/CompressedImage":
        img = Image.open(io.BytesIO(ros_msg.data)).convert("RGB")
        img_channel = len(img.getbands())
        used_encoding = getattr(ros_msg, "format", None)
        return img, img_channel, used_encoding

    img_channel = int(len(ros_msg.data) / (ros_msg.height * ros_msg.width))
    img_array = np.frombuffer(ros_msg.data, dtype=np.uint8).reshape(
        (ros_msg.height, ros_msg.width, img_channel))

    # Convert BGR (bgr8) to RGB
    encoding = getattr(ros_msg, "encoding", "").lower()
    used_encoding = encoding or None
    if encoding == "bgr8" and img_channel == 3:
        img_array = img_array[:, :, ::-1]  # BGR -> RGB

    img = Image.fromarray(img_array)
    return img, img_channel, used_encoding


def _check_memory_warning(frame_idx, current_memory_mb, memory_warning_shown):
    """Check memory and warn if needed. Returns (current_memory_mb, memory_warning_shown)."""
    if frame_idx % MEMORY_CHECK_INTERVAL != 0:
        return current_memory_mb, memory_warning_shown

    current_memory_mb = _get_peak_memory_mb()
    if current_memory_mb is not None and not memory_warning_shown:
        try:
            avail = (os.sysconf('SC_PAGE_SIZE')
                     * os.sysconf('SC_AVPHYS_PAGES'))
            avail_mb = avail / BYTES_PER_MB
            if avail_mb < current_memory_mb:
                memory_warning_shown = True
                print(
                    f"\nWARNING: Memory usage "
                    f"(~{current_memory_mb:.0f} MB) "
                    f"exceeds available memory "
                    f"({avail_mb:.0f} MB)!")
                answer = input(
                    "Continue anyway? [y/N]: ").strip().lower()
                if answer != 'y':
                    print("Aborted.")
                    sys.exit(1)
        except (ValueError, OSError):
            pass

    return current_memory_mb, memory_warning_shown


def convert_to_mp4(input_file, topic, output_file, timestamp_timing=False) -> None:
    input_file = _sanitize_path(input_file)
    output_file = _sanitize_path(output_file)
    # --- Pass 1: scan timestamps and count frames (no decoding) ---
    timestamps = []
    spinner = Spinner("Scanning frames")
    spinner.start()

    try:
        with open(input_file, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                if (schema is not None
                        and schema.name in IMAGE_SCHEMAS and channel.topic == topic):
                    timestamps.append(message.log_time)
                    spinner.count = len(timestamps)
    finally:
        spinner.stop()

    total_frames = len(timestamps)
    print(f"Total {total_frames} frames")
    if total_frames < 2:
        print("image data too short!!!")
        sys.exit(1)

    if not timestamp_timing:
        diff_timestamp = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]
        mean_interval = mean(diff_timestamp)
        if mean_interval == 0:
            print("Error: all timestamps are identical, cannot calculate FPS")
            sys.exit(1)
        video_fps = 1 / mean_interval * 10**9

    # --- Pass 2: decode and write/save frames one by one ---
    print("Converting frames...")
    used_encoding = None
    img_channel = 3
    frame_idx = 0
    memory_warning_shown = False
    current_memory_mb = None
    warned_missing_stamp = False

    if timestamp_timing:
        # VFR path: save frames as PNGs to temp dir, collect header.stamps
        temp_dir = tempfile.mkdtemp(prefix="mcap_to_mp4_")
        image_paths: List[str] = []
        timestamps_ns: List[int] = []

        try:
            with open(input_file, "rb") as f:
                reader = make_reader(f, decoder_factories=[DecoderFactory()])
                for schema, channel, message, ros_msg in reader.iter_decoded_messages():
                    if (schema is not None
                            and schema.name in IMAGE_SCHEMAS and channel.topic == topic):
                        img, img_channel, enc = _decode_frame(schema, ros_msg)
                        if enc is not None:
                            used_encoding = enc

                        image_path = os.path.join(temp_dir, f"frame_{frame_idx:06d}.png")
                        img.save(image_path)
                        image_paths.append(image_path)

                        timestamp_ns = get_header_stamp_ns(ros_msg)
                        if timestamp_ns is None:
                            timestamp_ns = int(message.log_time)
                            if not warned_missing_stamp:
                                print("\nWarning: header.stamp is missing. "
                                      "Falling back to message.log_time for those frames.")
                                warned_missing_stamp = True
                        timestamps_ns.append(timestamp_ns)

                        frame_idx += 1
                        current_memory_mb, memory_warning_shown = _check_memory_warning(
                            frame_idx, current_memory_mb, memory_warning_shown)
                        print_progress_bar(frame_idx, total_frames, current_memory_mb)

            print()
            print("Saving file...")
            durations_ns = build_vfr_durations_ns(timestamps_ns)
            encode_vfr(output_file, image_paths, durations_ns)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        # CFR path: stream frames directly to imageio writer
        video_writer = imageio.get_writer(output_file, fps=video_fps)
        try:
            with open(input_file, "rb") as f:
                reader = make_reader(f, decoder_factories=[DecoderFactory()])
                for schema, channel, message, ros_msg in reader.iter_decoded_messages():
                    if (schema is not None
                            and schema.name in IMAGE_SCHEMAS and channel.topic == topic):
                        img, img_channel, enc = _decode_frame(schema, ros_msg)
                        if enc is not None:
                            used_encoding = enc

                        video_writer.append_data(np.array(img))
                        frame_idx += 1
                        current_memory_mb, memory_warning_shown = _check_memory_warning(
                            frame_idx, current_memory_mb, memory_warning_shown)
                        print_progress_bar(frame_idx, total_frames, current_memory_mb)
        finally:
            video_writer.close()
        print()

    if img_channel == 3:
        if used_encoding == "bgr8":
            print("Converted from BGR (bgr8) to RGB image format")
        else:
            print("Converted as RGB image format")
    else:
        print(f"Converted as {img_channel} channel image format")
    print("Done.")


def main():
    args = parse_arguments()
    print(f"mcap version: {mcap.__version__}")
    check_file_exists(args.input)

    # If topic is not specified, show the topic list
    if args.topic is None:
        print("Available topics:")
        print(get_image_topic_list(args.input))
        sys.exit(0)

    print(f"Converting {args.topic} to MP4...")
    convert_to_mp4(args.input, args.topic, args.output, args.timestamp_timing)


if __name__ == "__main__":
    main()
