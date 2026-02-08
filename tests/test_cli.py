from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest

from mcap_to_mp4.cli import (
    DEFAULT_FALLBACK_FPS,
    MAX_GAP_MULTIPLIER,
    NANOSECONDS_PER_SECOND,
    build_vfr_durations_ns,
    check_file_exists,
    convert_to_mp4,
    encode_vfr,
    get_header_stamp_ns,
    get_image_topic_list,
    parse_arguments,
    read_frames_and_timestamps,
)


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


def test_read_frames_and_timestamps_use_header_stamp():
    mock_reader = MagicMock()
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    timestamps = [100, 200, 500]
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=1_000_000_000 + i),
            create_mock_ros_msg(
                sec=t // NANOSECONDS_PER_SECOND,
                nanosec=t % NANOSECONDS_PER_SECOND,
            ),
        )
        for i, t in enumerate(timestamps)
    ]
    mock_reader.iter_decoded_messages.return_value = messages

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        frames, stamp_ns, _, _ = read_frames_and_timestamps("dummy.mcap", "/camera/image", True)

    assert len(frames) == 3
    assert stamp_ns == timestamps


def test_read_frames_and_timestamps_skip_invalid_frame():
    mock_reader = MagicMock()
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"
    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=10),
            create_mock_ros_msg(height=0, width=640),
        ),
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=20),
            create_mock_ros_msg(height=2, width=2, data_override=b"\x00" * 5),
        ),
        (
            mock_schema,
            MagicMock(topic="/camera/image"),
            MagicMock(log_time=30),
            create_mock_ros_msg(height=2, width=2, channels=3),
        ),
    ]
    mock_reader.iter_decoded_messages.return_value = messages

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        frames, stamp_ns, _, _ = read_frames_and_timestamps("dummy.mcap", "/camera/image", False)

    assert len(frames) == 1
    assert stamp_ns == [30]


def test_convert_to_mp4_frame_count():
    mock_reader = MagicMock()
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
    mock_reader.iter_decoded_messages.return_value = messages

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4")

    assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_fps():
    mock_reader = MagicMock()
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
    mock_reader.iter_decoded_messages.return_value = messages

    mock_writer_instance = MagicMock()
    mock_get_writer = MagicMock(return_value=mock_writer_instance)

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
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
    mock_reader = MagicMock()
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
    mock_reader.iter_decoded_messages.return_value = messages

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('mcap_to_mp4.cli.encode_vfr') as mock_encode_vfr, \
            patch('mcap_to_mp4.cli.encode_cfr') as mock_encode_cfr, \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/camera/image", "output.mp4", timestamp_timing=True)

    mock_encode_vfr.assert_called_once()
    mock_encode_cfr.assert_not_called()


def test_encode_vfr_calls_ffmpeg():
    frames = [
        np.zeros((2, 2, 3), dtype=np.uint8),
        np.zeros((2, 2, 3), dtype=np.uint8),
    ]
    durations = [100_000_000, 100_000_000]

    with patch('mcap_to_mp4.cli.subprocess.run') as mock_run:
        encode_vfr("output.mp4", frames, durations)

    assert mock_run.call_count == 1
    ffmpeg_command = mock_run.call_args.args[0]
    assert ffmpeg_command[0] == "ffmpeg"
    assert "-f" in ffmpeg_command
    assert "concat" in ffmpeg_command
    assert "-vsync" in ffmpeg_command
    assert "vfr" in ffmpeg_command
