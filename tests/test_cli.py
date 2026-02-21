import io
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest
from PIL import Image

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
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    mock_channel = MagicMock()
    mock_channel.topic = "/camera/image"
    mock_channel.schema_id = 1

    mock_summary = MagicMock()
    mock_summary.schemas = {1: mock_schema}
    mock_summary.channels = {1: mock_channel}

    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

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


def create_mock_compressed_ros_msg(height=480, width=640):
    """Create a mock CompressedImage message with JPEG data."""
    mock_msg = MagicMock()
    mock_msg.format = "jpeg"
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    mock_msg.data = buf.getvalue()
    return mock_msg


def setup_two_pass_reader(messages):
    """Create a side_effect for make_reader that supports two-pass reading.

    First call (pass 1): returns a reader with iter_messages() yielding 3-tuples.
    Second call (pass 2): returns a reader with iter_decoded_messages() yielding 4-tuples.
    """
    def factory(*args, **kwargs):  # noqa: U100 - matches make_reader() signature
        mock_reader = MagicMock()
        if 'decoder_factories' not in kwargs:
            # Pass 1: iter_messages returns (schema, channel, message) 3-tuples
            mock_reader.iter_messages.return_value = [
                (schema, channel, message)
                for schema, channel, message, ros_msg in messages
            ]
        else:
            # Pass 2: iter_decoded_messages returns full 4-tuples
            mock_reader.iter_decoded_messages.return_value = messages
        return mock_reader
    return factory


def test_convert_to_mp4_frame_count():
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

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

        assert mock_writer.append_data.call_count == 3


def test_get_image_topic_list_compressed():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/CompressedImage"
    mock_channel = MagicMock()
    mock_channel.topic = "/camera/image/compressed"
    mock_channel.schema_id = 1

    mock_summary = MagicMock()
    mock_summary.schemas = {1: mock_schema}
    mock_summary.channels = {1: mock_channel}

    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader):
        with patch('builtins.open', mock_open()):
            topics = get_image_topic_list('test.mcap')
            assert topics == ['/camera/image/compressed']


def test_convert_to_mp4_compressed_image():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/CompressedImage"

    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image/compressed"),
            MagicMock(log_time=1000000 + t),
            create_mock_compressed_ros_msg()
        )
        for t in range(3)
    ]

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image/compressed", "output.mp4")

        assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_identical_timestamps():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"

    same_time = 1000000
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=same_time),
            create_mock_ros_msg()
        )
        for _ in range(3)
    ]

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):

        with pytest.raises(SystemExit, match="1"):
            convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")


def test_convert_to_mp4_fps():
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

    # writerのモックを2段階で設定
    # get_writerのモック全体を直接置き換え
    mock_writer_instance = MagicMock()
    mock_get_writer = MagicMock(return_value=mock_writer_instance)

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
         patch('mcap_to_mp4.cli.imageio.get_writer', mock_get_writer), \
         patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

        expected_fps = 1.0  # 1秒間隔なので1fps
        mock_get_writer.assert_called_once_with("output.mp4",
                                                fps=pytest.approx(expected_fps, rel=0.1))
