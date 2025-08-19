#!/usr/bin/env python3
# https://github.com/Tiryoh/mcap-to-mp4
# Copyright 2024 Daisuke Sato <tiryoh@gmail.com>
# MIT License

import argparse
import os
import sys
from typing import List

import imageio
import mcap
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory
import numpy as np
from PIL import Image
from statistics import mean


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
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for schema, channel, message, ros_msg in reader.iter_decoded_messages():
            if schema is not None and \
                    schema.name == "sensor_msgs/msg/Image":
                topic_list.append(channel.topic)
    return list(set(topic_list))


def convert_to_mp4(input_file, topic, output_file) -> None:
    ims = []
    diff_timestamp = []
    prev_timestamp = 0
    used_encoding = None  # track last seen encoding (only used for bgr8 notification)

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

                img = Image.fromarray(img_array)
                ims.append(img)
                if not prev_timestamp == 0:
                    diff_timestamp.append(message.log_time - prev_timestamp)
                prev_timestamp = message.log_time
                print(".", end="")
    print()
    print(f"Total {len(diff_timestamp)+1} frames")
    if (len(diff_timestamp) == 0):
        print("image data too short!!!")
        sys.exit(1)
    if img_channel == 3:
        if used_encoding == "bgr8":
            print("Converted from BGR (bgr8) to RGB image format")
        else:
            print("Converted as RGB image format")
    else:
        print(f"Converted as {img_channel} channel image format")
    print("Saving file...")
    video_fps = 1/mean(diff_timestamp[1:])*10**9
    video_writer = imageio.get_writer(output_file, fps=video_fps)
    for frame in ims:
        video_writer.append_data(np.array(frame))
    video_writer.close()
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
