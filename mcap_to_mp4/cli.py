#!/usr/bin/env python3
# https://github.com/Tiryoh/mcap-to-mp4
# Copyright 2024 Daisuke Sato <tiryoh@gmail.com>
# MIT License

import os
import argparse
from typing import List

import mcap
from mcap_ros2.decoder import DecoderFactory
from mcap.reader import make_reader

from PIL import Image
import numpy as np
from statistics import mean
import imageio


def get_image_topic_list(mcap_file_path: str) -> List[str]:
    topic_list = []
    with open(mcap_file_path, "rb") as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for schema, channel, message, ros_msg in reader.iter_decoded_messages():
            if schema.name == "sensor_msgs/msg/Image":  # type: ignore
                topic_list.append(channel.topic)
    return list(set(topic_list))

def main():
    print(f"mcap version: {mcap.__version__}")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="input bag file path to read")
    parser.add_argument("-t", "--topic", help="topic name to convert. if not specified, the topic list will be shown")
    parser.add_argument("-o", "--output", help="output file name", default="output.mp4")
    args = parser.parse_args()

    # check if the file exists
    if not os.path.isfile(args.input):
        RuntimeError("file does not exists")

    # check if the topic exists
    topic_list = get_image_topic_list(args.input)
    if args.topic is None:
        print(topic_list)
    else:
        print(f"Converting {args.topic} to MP4...")
        ims = []
        diff_timestamp = []
        prev_timestamp = 0

        with open(args.input, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, channel, message, ros_msg in reader.iter_decoded_messages():
                if schema.name == "sensor_msgs/msg/Image" and channel.topic == args.topic:
                    img_array = np.frombuffer(ros_msg.data, dtype=np.uint8).reshape((ros_msg.height, ros_msg.width, 3))
                    img = Image.fromarray(img_array)
                    ims.append(img)
                    diff_timestamp.append(message.log_time - prev_timestamp)
                    prev_timestamp = message.log_time
                    print(".", end="")

        print()
        print(f"Total {len(diff_timestamp)+1} frames")
        print("Saving file...")
        video_writer = imageio.get_writer(args.output, fps=1/mean(diff_timestamp[1:])*10**9)
        for frame in ims:
            video_writer.append_data(np.array(frame))
        video_writer.close()
        print("Done.")

if __name__ == "__main__":
    main()
