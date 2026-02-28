import io
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest
from PIL import Image

from mcap_to_mp4.cli import (DEFAULT_FALLBACK_FPS, MAX_GAP_MULTIPLIER,
                             NANOSECONDS_PER_SECOND, build_vfr_durations_ns,
                             check_file_exists, convert_to_mp4, encode_vfr,
                             get_header_stamp_ns, get_image_topic_list,
                             parse_arguments)


def test_parse_arguments():
    with patch('sys.argv', ['script.py', 'input.mcap', '-t', '/camera/image', '-o', 'video.mp4',
                            '--timestamp-timing']):
        args = parse_arguments()
        assert args.input == 'input.mcap'
        assert args.topic == '/camera/image'
        assert args.output == 'video.mp4'
        assert args.timestamp_timing is True


def test_parse_arguments_minimal():
    with patch('sys.argv', ['script.py', 'input.mcap']):
        args = parse_arguments()
        assert args.input == 'input.mcap'
        assert args.topic is None
        assert args.output == 'output.mp4'
        assert args.timestamp_timing is False


def test_check_file_exists_valid():
    with patch('os.path.isfile', return_value=True):
        assert check_file_exists('existing.mcap') is None


def test_check_file_exists_invalid():
    with patch('os.path.isfile', return_value=False):
        with pytest.raises(RuntimeError, match="File does not exist"):
            check_file_exists('nonexistent.mcap')


def test_get_header_stamp_ns():
    ros_msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=2)))
    assert get_header_stamp_ns(ros_msg) == NANOSECONDS_PER_SECOND + 2


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


def create_mock_ros_msg(height=480, width=640, channels=3, encoding="rgb8",
                        sec=0, nanosec=0, with_header=True, data_override=None):
    mock_msg = MagicMock()
    mock_msg.height = height
    mock_msg.width = width
    if data_override is None:
        mock_msg.data = np.zeros((height, width, channels), dtype=np.uint8).tobytes()
    else:
        mock_msg.data = data_override
    mock_msg.encoding = encoding
    if with_header:
        mock_msg.header = SimpleNamespace(stamp=SimpleNamespace(sec=sec, nanosec=nanosec))
    else:
        mock_msg.header = None
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
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=1_000_000 + t),
            create_mock_ros_msg(),
        )
        for t in range(3)
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
    base_time = NANOSECONDS_PER_SECOND
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=base_time + (t * base_time)),
            create_mock_ros_msg(),
        )
        for t in range(3)
    ]

    mock_writer_instance = MagicMock()
    mock_get_writer = MagicMock(return_value=mock_writer_instance)

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
         patch('mcap_to_mp4.cli.imageio.get_writer', mock_get_writer), \
         patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

    expected_fps = 1.0
    mock_get_writer.assert_called_once_with("output.mp4", fps=pytest.approx(expected_fps, rel=0.1))


def test_build_vfr_durations_ns_policy():
    durations = build_vfr_durations_ns([0, 100, 100, 5000])
    assert durations == [100, 100, int(100 * MAX_GAP_MULTIPLIER), int(100 * MAX_GAP_MULTIPLIER)]


def test_build_vfr_durations_ns_single_frame():
    durations = build_vfr_durations_ns([12345])
    assert durations == [int(NANOSECONDS_PER_SECOND / DEFAULT_FALLBACK_FPS)]


def test_build_vfr_durations_ns_uses_median_reference():
    durations = build_vfr_durations_ns([0, 1_000_000, 1_000_100, 1_000_200])
    assert durations == [1_000, 100, 100, 100]


def test_convert_to_mp4_timestamp_timing_calls_vfr():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=1_000_000 + t),
            create_mock_ros_msg(
                sec=0,
                nanosec=(t + 1) * 100,
            ),
        )
        for t in range(3)
    ]

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.encode_vfr') as mock_encode_vfr, \
            patch('mcap_to_mp4.cli.tempfile.mkdtemp', return_value='/tmp/test'), \
            patch('mcap_to_mp4.cli.shutil.rmtree'), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4", timestamp_timing=True)

    mock_encode_vfr.assert_called_once()


def test_encode_vfr_calls_ffmpeg():
    image_paths = ["/tmp/frame_000000.png", "/tmp/frame_000001.png"]
    durations = [100_000_000, 100_000_000]

    with patch('mcap_to_mp4.cli.subprocess.run') as mock_run:
        encode_vfr("output.mp4", image_paths, durations)

    assert mock_run.call_count == 1
    ffmpeg_command = mock_run.call_args.args[0]
    assert ffmpeg_command[0] == "ffmpeg"
    assert "-f" in ffmpeg_command
    assert "concat" in ffmpeg_command
    assert "-vsync" in ffmpeg_command
    assert "vfr" in ffmpeg_command
