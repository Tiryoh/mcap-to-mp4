from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest

from mcap_to_mp4.cli import (check_file_exists, convert_to_mp4,
                             get_image_topic_list, parse_arguments)


def test_parse_arguments():
    with patch('sys.argv', ['script.py', 'input.mcap', '-t', '/camera/image', '-o', 'video.mp4']):
        args = parse_arguments()
        assert args.input == 'input.mcap'
        assert args.topic == '/camera/image'
        assert args.output == 'video.mp4'


def test_parse_arguments_minimal():
    with patch('sys.argv', ['script.py', 'input.mcap']):
        args = parse_arguments()
        assert args.input == 'input.mcap'
        assert args.topic is None
        assert args.output == 'output.mp4'


def test_check_file_exists_valid():
    with patch('os.path.isfile', return_value=True):
        assert check_file_exists('existing.mcap') is None


def test_check_file_exists_invalid():
    with patch('os.path.isfile', return_value=False):
        with pytest.raises(RuntimeError, match="File does not exist"):
            check_file_exists('nonexistent.mcap')


def test_get_image_topic_list():
    mock_reader = MagicMock()
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    mock_channel = MagicMock()
    mock_channel.topic = "/camera/image"

    mock_reader.iter_decoded_messages.return_value = [
        (mock_schema, mock_channel, None, None)
    ]

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader):
        with patch('builtins.open', mock_open()):
            topics = get_image_topic_list('test.mcap')
            assert topics == ['/camera/image']


def create_mock_ros_msg(height=480, width=640, channels=3):
    mock_msg = MagicMock()
    mock_msg.height = height
    mock_msg.width = width
    mock_msg.data = np.zeros((height, width, channels), dtype=np.uint8).tobytes()
    return mock_msg


def test_convert_to_mp4_frame_count():
    mock_reader = MagicMock()
    # MagicMock(name=)とするとMagicMockオブジェクト自体の識別用の名前を設定してしまう
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"

    messages = [
        (
            mock_schema,                         # schema
            MagicMock(topic="/camera/image"),    # channel
            MagicMock(log_time=1000000 + t),     # message
            create_mock_ros_msg()                # ros_msg
        )
        for t in range(3)  # 3フレーム分
    ]
    mock_reader.iter_decoded_messages.return_value = messages

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

        assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_fps():
    mock_reader = MagicMock()
    # MagicMock(name=)とするとMagicMockオブジェクト自体の識別用の名前を設定してしまう
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    # タイムスタンプを1秒間隔で設定
    base_time = 1_000_000_000  # 1秒 = 10^9 ナノ秒
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=base_time + (t * base_time)),  # 1秒ごとに増加
            create_mock_ros_msg()
        )
        for t in range(3)
    ]
    mock_reader.iter_decoded_messages.return_value = messages

    # writerのモックを2段階で設定
    # get_writerのモック全体を直接置き換え
    mock_writer_instance = MagicMock()
    mock_get_writer = MagicMock(return_value=mock_writer_instance)

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
         patch('mcap_to_mp4.cli.imageio.get_writer', mock_get_writer), \
         patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

        expected_fps = 1.0  # 1秒間隔なので1fps
        mock_get_writer.assert_called_once_with("output.mp4",
                                                fps=pytest.approx(expected_fps, rel=0.1))
