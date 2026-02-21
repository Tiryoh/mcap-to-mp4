#!/usr/bin/env python3
# https://github.com/Tiryoh/mcap-to-mp4
# Copyright 2024-2026 Daisuke Sato <tiryoh@gmail.com>
# MIT License

import argparse
import io
import itertools
import os
import sys
import threading
import time
from statistics import mean
from typing import List

import imageio
import mcap
import numpy as np
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory
from PIL import Image

IMAGE_SCHEMAS = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
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


def convert_to_mp4(input_file, topic, output_file) -> None:
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

    diff_timestamp = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]
    mean_interval = mean(diff_timestamp)
    if mean_interval == 0:
        print("Error: all timestamps are identical, cannot calculate FPS")
        sys.exit(1)
    video_fps = 1 / mean_interval * 10**9

    # --- Pass 2: decode and write frames one by one ---
    print("Converting frames...")
    used_encoding = None
    img_channel = 3
    video_writer = imageio.get_writer(output_file, fps=video_fps)
    frame_idx = 0
    # Periodic memory monitoring:
    #   Memory usage is checked every MEMORY_CHECK_INTERVAL frames because
    #   ffmpeg/imageio allocates internal buffers gradually — measuring too
    #   early underestimates actual usage. By re-checking periodically, we
    #   can detect if memory grows beyond what's available and warn the user
    #   before an OOM occurs.
    #
    #   Peak RSS is measured via resource.getrusage:
    #     - RUSAGE_SELF: Python process (interpreter, libraries, mcap reader,
    #       numpy/PIL buffers, up to 3 frame copies: img_array, PIL Image,
    #       numpy array for video_writer)
    #     - RUSAGE_CHILDREN: child processes (ffmpeg spawned by imageio)
    #   Both are summed because gtime/time -v reports the combined peak,
    #   and ffmpeg can use significant memory for video encoding.
    memory_warning_shown = False
    current_memory_mb = None

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

    try:
        with open(input_file, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, channel, message, ros_msg in reader.iter_decoded_messages():
                if (schema is not None
                        and schema.name in IMAGE_SCHEMAS and channel.topic == topic):
                    if schema.name == "sensor_msgs/msg/CompressedImage":
                        img = Image.open(io.BytesIO(ros_msg.data)).convert("RGB")
                        img_channel = len(img.getbands())
                        used_encoding = getattr(ros_msg, "format", used_encoding)
                    else:
                        img_channel = int(
                            len(ros_msg.data) / (ros_msg.height * ros_msg.width))
                        img_array = np.frombuffer(ros_msg.data, dtype=np.uint8).reshape(
                            (ros_msg.height, ros_msg.width, img_channel))

                        # Convert BGR (bgr8) to RGB
                        encoding = getattr(ros_msg, "encoding", "").lower()
                        used_encoding = encoding or used_encoding
                        if encoding == "bgr8" and img_channel == 3:
                            img_array = img_array[:, :, ::-1]  # BGR -> RGB

                        img = Image.fromarray(img_array)

                    video_writer.append_data(np.array(img))
                    frame_idx += 1

                    # Periodic memory measurement every MEMORY_CHECK_INTERVAL frames
                    if frame_idx % MEMORY_CHECK_INTERVAL == 0:
                        current_memory_mb = _get_peak_memory_mb()
                        # Check available memory (Linux / WSL only;
                        # SC_AVPHYS_PAGES is not available on macOS)
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
    convert_to_mp4(args.input, args.topic, args.output)


if __name__ == "__main__":
    main()
