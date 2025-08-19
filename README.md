# mcap-to-mp4

A tool to convert ROS 2 topics recorded with rosbag2 recordings in [mcap](https://mcap.dev/) format into MP4 files

**English**  
This tool provides a simple way to convert ROS 2 topics stored in **rosbag2** recordings using the **MCAP** format into standard MP4 video files.  
It is especially useful for visualizing and sharing regularly published topics such as camera streams or sensor data.  
Since the tool assumes that topics are subscribed at a fixed rate, the generated MP4 uses the *average frame interval* of the input messages.  
This makes the resulting video well-suited for experiment reviews, demos, or presentations.  

**日本語**  
このツールは、**rosbag2** で **MCAP** 形式として記録された ROS 2 トピックを、標準的な MP4 動画ファイルに変換します。  
カメラストリームやセンサーデータなど、一定周期で発行されるトピックを可視化・共有するのに特に便利です。  
トピックが一定周期でサブスクライブできることを前提としており、生成される MP4 は各フレーム間隔の平均値を採用して出力します。  
そのため、実験の振り返りやデモ、プレゼンテーションに適しています。  

## Requirements

**Note:** This tool does **NOT** require a ROS 2 runtime environment.  
You only need Python and the following dependencies:

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

