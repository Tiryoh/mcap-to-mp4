#!/usr/bin/env python3
# https://github.com/Tiryoh/mcap-to-mp4
# Copyright 2024 Daisuke Sato <tiryoh@gmail.com>
# MIT License

import argparse
import os
import subprocess
import sys
import tempfile
from statistics import mean
from typing import List, Optional, Tuple

import imageio
import mcap
import numpy as np
from PIL import Image
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

NANOSECONDS_PER_SECOND = 1_000_000_000
DEFAULT_FALLBACK_FPS = 30.0
MAX_GAP_MULTIPLIER = 10.0


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
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for schema, channel, message, ros_msg in reader.iter_decoded_messages():
            if schema is not None and \
                    schema.name == "sensor_msgs/msg/Image":
                topic_list.append(channel.topic)
    return list(set(topic_list))


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


def read_frames_and_timestamps(input_file: str, topic: str, timestamp_timing: bool) \
        -> Tuple[List[np.ndarray], List[int], int, Optional[str]]:
    frames: List[np.ndarray] = []
    timestamps_ns: List[int] = []
    img_channel = 0
    used_encoding = None
    warned_missing_stamp = False

    with open(input_file, "rb") as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for schema, channel, message, ros_msg in reader.iter_decoded_messages():
            if schema is not None \
                    and schema.name == "sensor_msgs/msg/Image" and channel.topic == topic:
                img_channel = int(len(ros_msg.data) / (ros_msg.height * ros_msg.width))
                img_array = np.frombuffer(ros_msg.data, dtype=np.uint8).reshape(
                    (ros_msg.height, ros_msg.width, img_channel))

                # Convert BGR (bgr8) to RGB
                encoding = getattr(ros_msg, "encoding", "").lower()
                used_encoding = encoding or used_encoding
                if encoding == "bgr8" and img_channel == 3:
                    img_array = img_array[:, :, ::-1]  # BGR -> RGB

                frames.append(np.array(Image.fromarray(img_array)))

                if timestamp_timing:
                    timestamp_ns = get_header_stamp_ns(ros_msg)
                    if timestamp_ns is None:
                        timestamp_ns = int(message.log_time)
                        if not warned_missing_stamp:
                            print("Warning: header.stamp is missing. "
                                  "Falling back to message.log_time for those frames.")
                            warned_missing_stamp = True
                else:
                    timestamp_ns = int(message.log_time)

                timestamps_ns.append(timestamp_ns)
                print(".", end="")
    return frames, timestamps_ns, img_channel, used_encoding


def build_vfr_durations_ns(timestamps_ns: List[int]) -> List[int]:
    if len(timestamps_ns) == 0:
        return []

    fallback_duration_ns = int(NANOSECONDS_PER_SECOND / DEFAULT_FALLBACK_FPS)
    if len(timestamps_ns) == 1:
        return [fallback_duration_ns]

    raw_deltas = [timestamps_ns[i + 1] - timestamps_ns[i] for i in range(len(timestamps_ns) - 1)]
    positive_deltas = [d for d in raw_deltas if d > 0]
    reference_duration_ns = int(mean(positive_deltas)) if positive_deltas else fallback_duration_ns

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


def encode_cfr(output_file: str, frames: List[np.ndarray], timestamps_ns: List[int]) -> None:
    if len(frames) < 2:
        print("image data too short!!!")
        sys.exit(1)

    deltas = [timestamps_ns[i + 1] - timestamps_ns[i] for i in range(len(timestamps_ns) - 1)]
    positive_deltas = [d for d in deltas if d > 0]
    if len(positive_deltas) == 0:
        raise RuntimeError("Failed to determine FPS because timestamps are not increasing")

    video_fps = NANOSECONDS_PER_SECOND / mean(positive_deltas)
    video_writer = imageio.get_writer(output_file, fps=video_fps)
    for frame in frames:
        video_writer.append_data(frame)
    video_writer.close()


def quote_concat_path(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"


def encode_vfr(output_file: str, frames: List[np.ndarray], durations_ns: List[int]) -> None:
    if len(frames) != len(durations_ns):
        raise RuntimeError("Frame and duration counts do not match")

    with tempfile.TemporaryDirectory(prefix="mcap_to_mp4_") as temp_dir:
        image_paths: List[str] = []
        for index, frame in enumerate(frames):
            image_path = os.path.join(temp_dir, f"frame_{index:06d}.png")
            Image.fromarray(frame).save(image_path)
            image_paths.append(image_path)

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


def convert_to_mp4(input_file, topic, output_file, timestamp_timing=False) -> None:
    frames, timestamps_ns, img_channel, used_encoding = read_frames_and_timestamps(
        input_file, topic, timestamp_timing)
    print()
    print(f"Total {len(frames)} frames")
    if len(frames) == 0:
        print("No image data found!!!")
        sys.exit(1)

    if img_channel == 3:
        if used_encoding == "bgr8":
            print("Converted from BGR (bgr8) to RGB image format")
        else:
            print("Converted as RGB image format")
    else:
        print(f"Converted as {img_channel} channel image format")
    print("Saving file...")
    if timestamp_timing:
        durations_ns = build_vfr_durations_ns(timestamps_ns)
        encode_vfr(output_file, frames, durations_ns)
    else:
        encode_cfr(output_file, frames, timestamps_ns)
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
