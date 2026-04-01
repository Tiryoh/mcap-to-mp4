import io
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest
from PIL import Image

from mcap_to_mp4.cli import (DEFAULT_FALLBACK_FPS, MAX_GAP_MULTIPLIER,
                             NANOSECONDS_PER_SECOND, _decode_frame,
                             _sanitize_path, build_vfr_durations_ns,
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


def test_get_header_stamp_ns_compressed_video():
    """CompressedVideo uses ros_msg.timestamp instead of ros_msg.header.stamp."""
    ros_msg = SimpleNamespace(timestamp=SimpleNamespace(sec=5, nanosec=100))
    assert get_header_stamp_ns(ros_msg) == 5 * NANOSECONDS_PER_SECOND + 100


def test_get_header_stamp_ns_none():
    """Returns None when neither header.stamp nor timestamp is present."""
    ros_msg = SimpleNamespace()
    assert get_header_stamp_ns(ros_msg) is None


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

    expected_fps = 1.0  # 1秒間隔なので1fps
    mock_get_writer.assert_called_once_with("output.mp4",
                                            fps=pytest.approx(expected_fps, rel=0.1))


# --- get_image_topic_list() edge cases ---

def _make_summary(schemas_dict, channels_dict):
    """Helper to build a mock summary with given schemas and channels."""
    mock_summary = MagicMock()
    mock_summary.schemas = schemas_dict
    mock_summary.channels = channels_dict
    return mock_summary


def _make_schema(name, schema_id=1):
    s = MagicMock()
    s.name = name
    s.id = schema_id
    return s


def _make_channel(topic, schema_id, channel_id=1):
    c = MagicMock()
    c.topic = topic
    c.schema_id = schema_id
    c.id = channel_id
    return c


def test_get_image_topic_list_empty_channels():
    mock_summary = _make_summary(schemas_dict={}, channels_dict={})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        assert get_image_topic_list('test.mcap') == []


def test_get_image_topic_list_no_summary():
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = None

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        assert get_image_topic_list('test.mcap') == []


def test_get_image_topic_list_non_image_schema():
    schema = _make_schema("std_msgs/msg/String", schema_id=1)
    channel = _make_channel("/chatter", schema_id=1, channel_id=1)
    mock_summary = _make_summary({1: schema}, {1: channel})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        assert get_image_topic_list('test.mcap') == []


def test_get_image_topic_list_mixed_schemas():
    s1 = _make_schema("sensor_msgs/msg/Image", schema_id=1)
    s2 = _make_schema("sensor_msgs/msg/CompressedImage", schema_id=2)
    s3 = _make_schema("std_msgs/msg/String", schema_id=3)
    c1 = _make_channel("/cam/raw", schema_id=1, channel_id=1)
    c2 = _make_channel("/cam/compressed", schema_id=2, channel_id=2)
    c3 = _make_channel("/chatter", schema_id=3, channel_id=3)
    mock_summary = _make_summary({1: s1, 2: s2, 3: s3}, {1: c1, 2: c2, 3: c3})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        topics = get_image_topic_list('test.mcap')
        assert sorted(topics) == ['/cam/compressed', '/cam/raw']


def test_get_image_topic_list_multiple_image_topics():
    s1 = _make_schema("sensor_msgs/msg/Image", schema_id=1)
    c1 = _make_channel("/cam1", schema_id=1, channel_id=1)
    c2 = _make_channel("/cam2", schema_id=1, channel_id=2)
    mock_summary = _make_summary({1: s1}, {1: c1, 2: c2})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        topics = get_image_topic_list('test.mcap')
        assert sorted(topics) == ['/cam1', '/cam2']


def test_get_image_topic_list_duplicate_topic():
    s1 = _make_schema("sensor_msgs/msg/Image", schema_id=1)
    c1 = _make_channel("/cam", schema_id=1, channel_id=1)
    c2 = _make_channel("/cam", schema_id=1, channel_id=2)
    mock_summary = _make_summary({1: s1}, {1: c1, 2: c2})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        topics = get_image_topic_list('test.mcap')
        assert topics == ['/cam']


def test_get_image_topic_list_schema_not_found():
    # Channel references schema_id=99 which doesn't exist in schemas dict
    c1 = _make_channel("/cam", schema_id=99, channel_id=1)
    mock_summary = _make_summary({}, {1: c1})
    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader), \
            patch('builtins.open', mock_open()):
        assert get_image_topic_list('test.mcap') == []


# --- convert_to_mp4() Pass 1 filtering ---

def test_convert_to_mp4_filters_by_topic():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"

    messages = [
        (mock_schema, MagicMock(topic="/cam1"), MagicMock(log_time=1000000 + t),
         create_mock_ros_msg())
        for t in range(3)
    ] + [
        (mock_schema, MagicMock(topic="/cam2"), MagicMock(log_time=2000000 + t),
         create_mock_ros_msg())
        for t in range(2)
    ]

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/cam1", "output.mp4")
        assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_filters_by_schema():
    img_schema = MagicMock()
    img_schema.name = "sensor_msgs/msg/Image"
    str_schema = MagicMock()
    str_schema.name = "std_msgs/msg/String"

    messages = [
        (img_schema, MagicMock(topic="/cam"), MagicMock(log_time=1000000 + t),
         create_mock_ros_msg())
        for t in range(3)
    ] + [
        (str_schema, MagicMock(topic="/cam"), MagicMock(log_time=2000000 + t),
         MagicMock())
        for t in range(2)
    ]

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/cam", "output.mp4")
        assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_schema_none_skipped():
    img_schema = MagicMock()
    img_schema.name = "sensor_msgs/msg/Image"

    messages = [
        (img_schema, MagicMock(topic="/cam"), MagicMock(log_time=1000000 + t),
         create_mock_ros_msg())
        for t in range(3)
    ] + [
        (None, MagicMock(topic="/cam"), MagicMock(log_time=2000000), MagicMock())
    ]

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/cam", "output.mp4")
        assert mock_writer.append_data.call_count == 3


def test_convert_to_mp4_zero_frames():
    mock_schema = MagicMock()
    mock_schema.name = "std_msgs/msg/String"

    messages = [
        (mock_schema, MagicMock(topic="/chatter"), MagicMock(log_time=1000000),
         MagicMock())
    ]

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('builtins.open', mock_open()):
        with pytest.raises(SystemExit, match="1"):
            convert_to_mp4("dummy.mcap", "/cam", "output.mp4")


def test_convert_to_mp4_one_frame():
    mock_schema = MagicMock()
    mock_schema.name = "sensor_msgs/msg/Image"

    messages = [
        (mock_schema, MagicMock(topic="/cam"), MagicMock(log_time=1000000),
         create_mock_ros_msg())
    ]

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('builtins.open', mock_open()):
        with pytest.raises(SystemExit, match="1"):
            convert_to_mp4("dummy.mcap", "/cam", "output.mp4")


# --- _sanitize_path() ---

def test_sanitize_path_valid():
    assert _sanitize_path("/home/user/data/test.mcap") == "/home/user/data/test.mcap"
    assert _sanitize_path("relative/path.mp4") == "relative/path.mp4"
    assert _sanitize_path("file with spaces.mcap") == "file with spaces.mcap"


def test_get_image_topic_list_compressed_video():
    mock_schema = MagicMock()
    mock_schema.name = "foxglove_msgs/msg/CompressedVideo"
    mock_channel = MagicMock()
    mock_channel.topic = "/camera/compressed_video"
    mock_channel.schema_id = 1

    mock_summary = MagicMock()
    mock_summary.schemas = {1: mock_schema}
    mock_summary.channels = {1: mock_channel}

    mock_reader = MagicMock()
    mock_reader.get_summary.return_value = mock_summary

    with patch('mcap_to_mp4.cli.make_reader', return_value=mock_reader):
        with patch('builtins.open', mock_open()):
            topics = get_image_topic_list('test.mcap')
            assert topics == ['/camera/compressed_video']


def test_convert_to_mp4_compressed_video():
    mock_schema = MagicMock()
    mock_schema.name = "foxglove_msgs/msg/CompressedVideo"

    mock_ros_msg = MagicMock()
    mock_ros_msg.format = "h264"
    mock_ros_msg.data = b"\x00\x00\x00\x01"

    messages = [
        (
            mock_schema,
            MagicMock(topic="/camera/compressed_video"),
            MagicMock(log_time=1000000 + t),
            mock_ros_msg,
        )
        for t in range(3)
    ]

    mock_frame = MagicMock()
    mock_frame.to_ndarray.return_value = np.zeros((480, 640, 3), dtype=np.uint8)

    mock_codec = MagicMock()
    mock_codec.decode.return_value = [mock_frame]

    mock_av = MagicMock()
    mock_av.CodecContext.create.return_value = mock_codec

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader', side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer', return_value=mock_writer), \
            patch.dict('sys.modules', {'av': mock_av}), \
            patch('builtins.open', mock_open()):

        convert_to_mp4("dummy.mcap", "/camera/compressed_video", "output.mp4")

        assert mock_writer.append_data.call_count == 3
        mock_codec.decode.assert_called()


@pytest.mark.parametrize("dangerous_path", [
    "file;rm -rf /",
    "file|cat /etc/passwd",
    "file`whoami`",
    "$(command)",
    "file&bg",
    "path{a,b}",
])
def test_sanitize_path_dangerous_chars(dangerous_path):
    with pytest.raises(ValueError, match="Invalid characters"):
        _sanitize_path(dangerous_path)


# --- VFR tests from origin/main ---

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


# --- _decode_frame error path tests ---


def test_decode_frame_av_import_error():
    """sys.exit(1) when av cannot be imported for CompressedVideo."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00"

    with patch.dict('sys.modules', {'av': None}):
        with pytest.raises(SystemExit) as exc_info:
            _decode_frame(schema, ros_msg, {})
        assert exc_info.value.code == 1


def test_decode_frame_codec_init_failure():
    """sys.exit(1) when codec initialization fails."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "unsupported_codec"
    ros_msg.data = b"\x00"

    MockFFmpegError = type('FFmpegError', (Exception,), {})
    mock_av = MagicMock()
    mock_av.error.FFmpegError = MockFFmpegError
    mock_av.CodecContext.create.side_effect = ValueError(
        "unsupported_codec")

    with pytest.raises(SystemExit) as exc_info:
        _decode_frame(schema, ros_msg, {"_av": mock_av})
    assert exc_info.value.code == 1


def test_decode_frame_empty_decode_returns_none():
    """_decode_frame returns None when decode yields no frames."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00"

    mock_codec = MagicMock()
    mock_codec.decode.return_value = []
    mock_av = MagicMock()

    av_state = {"_av": mock_av, "codec": mock_codec}
    img, ch, enc = _decode_frame(schema, ros_msg, av_state)
    assert img is None
    assert ch == 3
    assert enc == "h264"


def test_decode_frame_decode_error_returns_none():
    """_decode_frame returns None when decode raises FFmpegError."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00"

    MockFFmpegError = type('FFmpegError', (Exception,), {})
    mock_av = MagicMock()
    mock_av.error.FFmpegError = MockFFmpegError

    mock_codec = MagicMock()
    mock_codec.decode.side_effect = MockFFmpegError("bad data")

    av_state = {"_av": mock_av, "codec": mock_codec}
    img, ch, enc = _decode_frame(schema, ros_msg, av_state)
    assert img is None


def test_decode_frame_codec_init_unexpected_exception_propagates():
    """Exceptions outside (ValueError, FFmpegError) propagate."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00"

    MockFFmpegError = type('FFmpegError', (Exception,), {})
    mock_av = MagicMock()
    mock_av.error.FFmpegError = MockFFmpegError
    mock_av.CodecContext.create.side_effect = RuntimeError(
        "unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        _decode_frame(schema, ros_msg, {"_av": mock_av})


def test_decode_frame_multi_frame_warning_once(capsys):
    """Multi-frame warning is printed once across multiple calls."""
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00"

    mock_frame = MagicMock()
    mock_frame.to_ndarray.return_value = np.zeros(
        (2, 2, 3), dtype=np.uint8)

    mock_codec = MagicMock()
    mock_codec.decode.return_value = [mock_frame, mock_frame]
    mock_av = MagicMock()

    av_state = {"_av": mock_av, "codec": mock_codec}

    _decode_frame(schema, ros_msg, av_state)
    _decode_frame(schema, ros_msg, av_state)

    captured = capsys.readouterr()
    assert captured.out.count("Warning: CompressedVideo packet") == 1


# --- convert_to_mp4 skipped frame tests ---


def _make_compressed_video_messages(count, decode_returns):
    """Helper: create CompressedVideo messages for convert_to_mp4 tests.

    decode_returns: list of return values for codec.decode() per message.
    """
    schema = MagicMock()
    schema.name = "foxglove_msgs/msg/CompressedVideo"
    ros_msg = MagicMock()
    ros_msg.format = "h264"
    ros_msg.data = b"\x00\x00\x00\x01"

    messages = [
        (
            schema,
            MagicMock(topic="/cam"),
            MagicMock(log_time=1_000_000 + t),
            ros_msg,
        )
        for t in range(count)
    ]

    mock_frame = MagicMock()
    mock_frame.to_ndarray.return_value = np.zeros(
        (4, 4, 3), dtype=np.uint8)

    mock_codec = MagicMock()
    mock_codec.decode.side_effect = decode_returns

    mock_av = MagicMock()
    mock_av.CodecContext.create.return_value = mock_codec

    return messages, mock_av


def test_convert_to_mp4_cfr_partial_skip_warning(capsys):
    """CFR: partial skip prints warning with timing note."""
    mock_frame = MagicMock()
    mock_frame.to_ndarray.return_value = np.zeros(
        (4, 4, 3), dtype=np.uint8)

    # 3 messages: first two decode ok, third returns empty
    messages, mock_av = _make_compressed_video_messages(
        3, [[mock_frame], [mock_frame], []])

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader',
               side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer',
                  return_value=mock_writer), \
            patch.dict('sys.modules', {'av': mock_av}), \
            patch('builtins.open', mock_open()):
        convert_to_mp4("dummy.mcap", "/cam", "output.mp4")

    captured = capsys.readouterr()
    assert "1 frame(s) could not be decoded" in captured.out
    assert "playback speed may be affected" in captured.out
    assert mock_writer.append_data.call_count == 2


def test_convert_to_mp4_vfr_partial_skip_warning(capsys):
    """VFR: partial skip prints warning and conversion succeeds."""
    mock_frame = MagicMock()
    mock_frame.to_ndarray.return_value = np.zeros(
        (4, 4, 3), dtype=np.uint8)

    messages, mock_av = _make_compressed_video_messages(
        3, [[mock_frame], [mock_frame], []])

    with patch('mcap_to_mp4.cli.make_reader',
               side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.encode_vfr') as mock_vfr, \
            patch('mcap_to_mp4.cli.tempfile.mkdtemp',
                  return_value='/tmp/test'), \
            patch('mcap_to_mp4.cli.shutil.rmtree'), \
            patch.dict('sys.modules', {'av': mock_av}), \
            patch('builtins.open', mock_open()):
        convert_to_mp4(
            "dummy.mcap", "/cam", "output.mp4",
            timestamp_timing=True)

    captured = capsys.readouterr()
    assert "1 frame(s) could not be decoded" in captured.out
    mock_vfr.assert_called_once()


def test_convert_to_mp4_cfr_all_skip_exits():
    """CFR: all frames skipped causes sys.exit(1) and removes output."""
    messages, mock_av = _make_compressed_video_messages(
        3, [[], [], []])

    mock_writer = MagicMock()

    with patch('mcap_to_mp4.cli.make_reader',
               side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.imageio.get_writer',
                  return_value=mock_writer), \
            patch.dict('sys.modules', {'av': mock_av}), \
            patch('builtins.open', mock_open()), \
            patch('mcap_to_mp4.cli.os.path.isfile',
                  return_value=True), \
            patch('mcap_to_mp4.cli.os.remove') as mock_remove:
        with pytest.raises(SystemExit) as exc_info:
            convert_to_mp4("dummy.mcap", "/cam", "output.mp4")
        assert exc_info.value.code == 1
        mock_remove.assert_called_once_with("output.mp4")


def test_convert_to_mp4_vfr_all_skip_exits():
    """VFR: all frames skipped causes sys.exit(1), encode_vfr not called."""
    messages, mock_av = _make_compressed_video_messages(
        3, [[], [], []])

    with patch('mcap_to_mp4.cli.make_reader',
               side_effect=setup_two_pass_reader(messages)), \
            patch('mcap_to_mp4.cli.encode_vfr') as mock_vfr, \
            patch('mcap_to_mp4.cli.tempfile.mkdtemp',
                  return_value='/tmp/test'), \
            patch('mcap_to_mp4.cli.shutil.rmtree'), \
            patch.dict('sys.modules', {'av': mock_av}), \
            patch('builtins.open', mock_open()):
        with pytest.raises(SystemExit) as exc_info:
            convert_to_mp4(
                "dummy.mcap", "/cam", "output.mp4",
                timestamp_timing=True)
        assert exc_info.value.code == 1
    mock_vfr.assert_not_called()
