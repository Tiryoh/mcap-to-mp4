# mcap-to-mp4

A tool to convert ROS topics recored with [mcap](https://mcap.dev/) to MP4 file

## Requirements

* Python3
    * mcap
    * mcap-ros2-support
    * poetry
    * pillow
    * numpy
    * imageio
* ffmpeg

## QuickStart

### pip

```sh
# Install
pip install mcap-to-mp4
# Run
mcap-to-mp4 $path_to_the_mcap_file -t $topic_name -o $outputfilename
```


### Docker

```sh
# Build
git clone https://github.com/Tiryoh/mcap-to-mp4.git
docker build -t tiryoh/mcap-to-mp4 .
# Run
docker run --rm -it -v "${PWD}:/works" tiryoh/mcap-to-mp4 $path_to_the_mcap_file -t $topic_name -o $outputfilename
```
## Usage

### pip

Install the package from PyPI

```sh
pip install mcap-to-mp4
```

Install the pacakge from source (optional)

```sh
# optional
git clone https://github.com/Tiryoh/mcap-to-mp4.git
pip install -e .
```

Download sample mcap rosbag2 file

```sh
wget "https://drive.usercontent.google.com/download?id=1TxKxq-SN_9ryiFxH6kQG07Gy90_bpnWW&confirm=xxx" -O "realsense_rosbag2.zip"
unzip realsense_rosbag2.zip
```

Run

```sh
mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4
```

### Docker

Install the package

```sh
git clone https://github.com/Tiryoh/mcap-to-mp4.git
docker build -t tiryoh/mcap-to-mp4 .
```

Download sample mcap rosbag2 file

```sh
wget "https://drive.usercontent.google.com/download?id=1TxKxq-SN_9ryiFxH6kQG07Gy90_bpnWW&confirm=xxx" -O "realsense_rosbag2.zip"
unzip realsense_rosbag2.zip
```

Run

```sh
docker run --rm -it -v "${PWD}:/works" tiryoh/mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4
```


## License

Copyright 2024 Daisuke Sato

This repository is licensed under the MIT license, see [LICENSE](./LICENSE).  
Unless attributed otherwise, everything in this repository is under the MIT license.

## Related Projects

* https://github.com/roboto-ai/robologs-ros-actions
* https://github.com/mlaiacker/rosbag2video
