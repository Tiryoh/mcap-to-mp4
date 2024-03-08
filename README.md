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

```
# Install
git clone https://github.com/Tiryoh/mcap-to-mp4.git
pip install -e .
# Run
mcap-to-mp4 $path_to_the_mcap_file -t $topic_name -o $outputfilename
```


### Docker

```
# Build
git clone https://github.com/Tiryoh/mcap-to-mp4.git
docker build -t tiryoh/mcap-to-mp4 .
# Run
docker run --rm -it -v "$(PWD):/works" tiryoh/mcap-to-mp4 $path_to_the_mcap_file -t $topic_name -o $outputfilename
```
## Usage

### pip

Download sample mcap rosbag2 file

```
wget "https://drive.usercontent.google.com/download?id=1TxKxq-SN_9ryiFxH6kQG07Gy90_bpnWW&confirm=xxx" -O "realsense_rosbag2.zip"
unzip realsense_rosbag2.zip
```

Install the package

```
git clone https://github.com/Tiryoh/mcap-to-mp4.git
pip install -e .
```

Run

```
mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4
```

### Docker

Download sample mcap rosbag2 file

```
wget "https://drive.usercontent.google.com/download?id=1TxKxq-SN_9ryiFxH6kQG07Gy90_bpnWW&confirm=xxx" -O "realsense_rosbag2.zip"
unzip realsense_rosbag2.zip
```

Install the package

```
git clone https://github.com/Tiryoh/mcap-to-mp4.git
docker build -t tiryoh/mcap-to-mp4 .
```

Run

```
docker run --rm -it -v "$(PWD):/works" tiryoh/mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4
```


## License

Copyright 2024 Daisuke Sato

This repository is licensed under the MIT license, see [LICENSE](./LICENSE).  
Unless attributed otherwise, everything in this repository is under the MIT license.
