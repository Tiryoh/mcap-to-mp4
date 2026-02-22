# mcap-to-mp4

A tool for converting ROS 2 image topics recorded in rosbag2 [MCAP](https://mcap.dev/) files into MP4 videos

**English**  
This tool provides a simple way to convert ROS 2 image topics recorded in **rosbag2** **MCAP** files into standard MP4 video files.  
It is especially useful for visualizing and sharing regularly published image streams, such as camera feeds.  
The tool assumes that input messages are recorded at a roughly fixed rate, and generates an MP4 using the *average frame interval* of the input messages.  
As a result, the generated videos are well suited for experiment reviews, demos, and presentations.  

**日本語**  
このツールは、rosbag2 の **MCAP** ファイルに記録された ROS 2 の画像トピックを、標準的な MP4 動画ファイルに変換します。  
カメラ映像のように、一定周期で発行される画像ストリームの可視化や共有に特に便利です。  
入力メッセージがおおむね一定周期で記録されていることを前提とし、生成される MP4 は入力メッセージ間の平均フレーム間隔を用いて出力します。  
そのため、実験の振り返りやデモ、プレゼンテーションに適しています。  

## Requirements

**Note:** This tool does **NOT** require a ROS 2 runtime environment.  
You only need Python and the following dependencies:

* Python3
    * mcap
    * mcap-ros2-support
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

### uv

```sh
# Install
uv tool install mcap-to-mp4
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

Install the package from source (optional)

```sh
# optional
git clone https://github.com/Tiryoh/mcap-to-mp4.git
cd mcap-to-mp4
pip install -e .
mcap-to-mp4 --help
```

### uv

Install the package from PyPI

```sh
uv tool install mcap-to-mp4
```

Install the package from source (optional)

```sh
# optional
git clone https://github.com/Tiryoh/mcap-to-mp4.git
cd mcap-to-mp4
uv sync --group dev
# Run with uv run
uv run mcap-to-mp4 --help
```

Download sample mcap rosbag2 file

```sh
wget "https://drive.usercontent.google.com/download?id=1TxKxq-SN_9ryiFxH6kQG07Gy90_bpnWW&confirm=xxx" -O "realsense_rosbag2.zip"
unzip realsense_rosbag2.zip
```

Run

```sh
# With pip or uv tool install:
mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4

# With uv sync (source install):
uv run mcap-to-mp4 ./rosbag2_2024_02_18-23_35_48/rosbag2_2024_02_18-23_35_48_0.mcap -t /camera/color/image_raw -o output.mp4
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


## Notes

* Memory check: During conversion, the tool estimates memory usage and displays it.
  * **Linux** (including **WSL**): Estimated memory usage is displayed. If available system memory is low, a warning is shown and you will be prompted to continue or abort.
  * **macOS**: Estimated memory usage is displayed. Available memory check is not supported.
  * **Windows** (non-WSL): Memory check is not supported.

## License

Copyright 2024-2026 Daisuke Sato

This repository is licensed under the MIT license, see [LICENSE](./LICENSE).  
Unless attributed otherwise, everything in this repository is under the MIT license.

## Related Projects

* https://github.com/roboto-ai/robologs-ros-actions
* https://github.com/mlaiacker/rosbag2video
