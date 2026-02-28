"""End-to-end tests: create real MCAP files, convert to MP4, and verify output."""

import io
from dataclasses import dataclass

import imageio
import numpy as np
import pytest
from mcap_ros2.writer import Writer
from PIL import Image

from mcap_to_mp4.cli import convert_to_mp4, get_image_topic_list

# --- Message definitions (inline ROS2 IDL) ---

IMAGE_MSGDEF = (
    "uint32 height\n"
    "uint32 width\n"
    "string encoding\n"
    "uint8 is_bigendian\n"
    "uint32 step\n"
    "uint8[] data"
)

COMPRESSED_IMAGE_MSGDEF = "string format\nuint8[] data"

STRING_MSGDEF = "string data"


# --- Dataclasses matching the msgdefs (for CDR serialization) ---

@dataclass
class ImageMsg:
    height: int = 0
    width: int = 0
    encoding: str = ""
    is_bigendian: int = 0
    step: int = 0
    data: bytes = b""


@dataclass
class CompressedImageMsg:
    format: str = ""
    data: bytes = b""


@dataclass
class StringMsg:
    data: str = ""


# --- Default test parameters ---

DEFAULT_WIDTH = 64
DEFAULT_HEIGHT = 48
DEFAULT_FPS = 10
DEFAULT_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # red, green, blue
COLOR_TOLERANCE = 30  # allow for H.264/JPEG compression artifacts


# --- Helper functions ---

def create_test_mcap_image(path, topic="/camera/image", width=DEFAULT_WIDTH,
                           height=DEFAULT_HEIGHT, colors=None, fps=DEFAULT_FPS,
                           encoding="rgb8"):
    """Create an MCAP file with sensor_msgs/msg/Image messages.

    Each frame is a solid color from the ``colors`` list.
    """
    if colors is None:
        colors = DEFAULT_COLORS
    interval_ns = int(1e9 / fps)

    with open(path, "wb") as f:
        writer = Writer(f)
        schema = writer.register_msgdef("sensor_msgs/msg/Image", IMAGE_MSGDEF)
        for i, color_rgb in enumerate(colors):
            if encoding == "bgr8":
                pixel = (color_rgb[2], color_rgb[1], color_rgb[0])
            else:
                pixel = color_rgb
            img_array = np.full((height, width, 3), pixel, dtype=np.uint8)
            msg = ImageMsg(
                height=height,
                width=width,
                encoding=encoding,
                step=width * 3,
                data=img_array.tobytes(),
            )
            writer.write_message(topic, schema, msg,
                                 log_time=1_000_000_000 + i * interval_ns)
        writer.finish()


def create_test_mcap_image_split(path, topic="/camera/image", width=DEFAULT_WIDTH,
                                 height=DEFAULT_HEIGHT, top_color=(255, 0, 0),
                                 bottom_color=(0, 255, 0), encoding="rgb8",
                                 fps=DEFAULT_FPS):
    """Create an MCAP file with a single Image frame split into two halves."""
    interval_ns = int(1e9 / fps)

    with open(path, "wb") as f:
        writer = Writer(f)
        schema = writer.register_msgdef("sensor_msgs/msg/Image", IMAGE_MSGDEF)

        img_array = np.zeros((height, width, 3), dtype=np.uint8)
        half = height // 2
        top_rgb = top_color
        bot_rgb = bottom_color
        if encoding == "bgr8":
            top_rgb = (top_color[2], top_color[1], top_color[0])
            bot_rgb = (bottom_color[2], bottom_color[1], bottom_color[0])
        img_array[:half] = top_rgb
        img_array[half:] = bot_rgb

        # Write exactly 2 identical frames (convert_to_mp4 requires >=2 for FPS calc).
        # Tests must assert len(frames) == 2 to detect frame-drop regressions.
        for i in range(2):
            msg = ImageMsg(
                height=height,
                width=width,
                encoding=encoding,
                step=width * 3,
                data=img_array.tobytes(),
            )
            writer.write_message(topic, schema, msg,
                                 log_time=1_000_000_000 + i * interval_ns)
        writer.finish()


def create_test_mcap_compressed(path, topic="/camera/image/compressed",
                                width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                                colors=None, fps=DEFAULT_FPS):
    """Create an MCAP file with sensor_msgs/msg/CompressedImage (JPEG) messages."""
    if colors is None:
        colors = DEFAULT_COLORS
    interval_ns = int(1e9 / fps)

    with open(path, "wb") as f:
        writer = Writer(f)
        schema = writer.register_msgdef("sensor_msgs/msg/CompressedImage",
                                        COMPRESSED_IMAGE_MSGDEF)
        for i, color_rgb in enumerate(colors):
            img = Image.new("RGB", (width, height), color_rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            msg = CompressedImageMsg(format="jpeg", data=buf.getvalue())
            writer.write_message(topic, schema, msg,
                                 log_time=1_000_000_000 + i * interval_ns)
        writer.finish()


def read_mp4_frames(path):
    """Read all frames from an MP4 file. Returns list of numpy arrays."""
    with imageio.get_reader(str(path)) as reader:
        return [reader.get_data(i) for i in range(reader.count_frames())]


def read_mp4_fps(path):
    """Read the FPS metadata from an MP4 file."""
    with imageio.get_reader(str(path)) as reader:
        return reader.get_meta_data()["fps"]


def assert_frame_color(frame, expected_rgb, tolerance=COLOR_TOLERANCE):
    """Assert that the mean color of a frame is close to expected RGB."""
    # imageio returns an ndarray subclass (imageio.core.util.Array) whose
    # __array_wrap__ is incompatible with NumPy 2.0+.  Converting to a plain
    # ndarray via np.asarray() avoids the DeprecationWarning.
    actual = np.mean(np.asarray(frame), axis=(0, 1))
    assert np.allclose(actual, expected_rgb, atol=tolerance), \
        f"Expected ~{expected_rgb}, got {actual}"


# --- Tests ---

class TestE2EImageRGB8:
    def test_e2e_image_rgb8(self, tmp_path):
        """Convert 3 solid-color rgb8 frames to MP4 and verify colors."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image(mcap_path, encoding="rgb8")

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 3
        for frame, expected in zip(frames, DEFAULT_COLORS):
            assert_frame_color(frame, expected)

    def test_e2e_image_bgr8(self, tmp_path):
        """Convert 3 bgr8 frames to MP4. Verify BGR->RGB conversion."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image(mcap_path, encoding="bgr8")

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 3
        # Colors should be in RGB order despite bgr8 input
        for frame, expected in zip(frames, DEFAULT_COLORS):
            assert_frame_color(frame, expected)


class TestE2ECompressed:
    def test_e2e_compressed_rgb(self, tmp_path):
        """Convert 3 JPEG CompressedImage frames to MP4."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_compressed(mcap_path)

        convert_to_mp4(mcap_path, "/camera/image/compressed", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 3
        for frame, expected in zip(frames, DEFAULT_COLORS):
            assert_frame_color(frame, expected)

    def test_e2e_compressed_color_passthrough(self, tmp_path):
        """Verify CompressedImage colors pass through without channel swapping.

        The CompressedImage code path uses PIL (Image.open().convert('RGB'))
        and does NOT apply any BGR→RGB conversion.  This test feeds non-primary
        colors (blue, green, red) to confirm that pixel values are preserved
        as-is through the JPEG→MP4 pipeline.
        """
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        swapped_colors = [(c[2], c[1], c[0]) for c in DEFAULT_COLORS]
        create_test_mcap_compressed(mcap_path, colors=swapped_colors)

        convert_to_mp4(mcap_path, "/camera/image/compressed", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 3
        for frame, expected in zip(frames, swapped_colors):
            assert_frame_color(frame, expected)


class TestE2ETopicList:
    def test_e2e_topic_list(self, tmp_path):
        """Verify get_image_topic_list returns only image topics."""
        mcap_path = str(tmp_path / "test.mcap")

        with open(mcap_path, "wb") as f:
            writer = Writer(f)
            s_image = writer.register_msgdef("sensor_msgs/msg/Image", IMAGE_MSGDEF)
            s_compressed = writer.register_msgdef("sensor_msgs/msg/CompressedImage",
                                                  COMPRESSED_IMAGE_MSGDEF)
            s_string = writer.register_msgdef("std_msgs/msg/String", STRING_MSGDEF)

            img = np.full((4, 4, 3), [255, 0, 0], dtype=np.uint8)
            writer.write_message(
                "/camera/image", s_image,
                ImageMsg(4, 4, "rgb8", 0, 12, img.tobytes()),
                log_time=1_000_000_000,
            )
            writer.write_message(
                "/camera/compressed", s_compressed,
                CompressedImageMsg("jpeg", b"\xff\xd8"),
                log_time=1_000_000_000,
            )
            # Non-image topic with image-sounding name
            writer.write_message(
                "/camera/info", s_string,
                StringMsg("camera info"),
                log_time=1_000_000_000,
            )
            writer.finish()

        topics = get_image_topic_list(mcap_path)
        assert sorted(topics) == ["/camera/compressed", "/camera/image"]
        assert "/camera/info" not in topics


MULTICOLOR_PARAMS = [
    pytest.param((255, 0, 0), (0, 255, 0), id="R-G"),
    pytest.param((255, 0, 0), (0, 0, 255), id="R-B"),
    pytest.param((0, 255, 0), (0, 0, 255), id="G-B"),
]


class TestE2EMulticolor:
    @pytest.mark.parametrize("top,bottom", MULTICOLOR_PARAMS)
    def test_e2e_image_multicolor(self, tmp_path, top, bottom):
        """Single frame with top-half / bottom-half different colors (rgb8)."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image_split(mcap_path, top_color=top, bottom_color=bottom,
                                     encoding="rgb8")

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 2
        for frame in frames:
            h = frame.shape[0]
            quarter = h // 4
            upper = frame[:quarter]
            lower = frame[h - quarter:]
            assert_frame_color(upper, top)
            assert_frame_color(lower, bottom)

    @pytest.mark.parametrize("top,bottom", MULTICOLOR_PARAMS)
    def test_e2e_image_multicolor_bgr8(self, tmp_path, top, bottom):
        """Split-color test with bgr8 encoding. Verify BGR->RGB preserves layout."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image_split(mcap_path, top_color=top, bottom_color=bottom,
                                     encoding="bgr8")

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 2
        for frame in frames:
            h = frame.shape[0]
            quarter = h // 4
            upper = frame[:quarter]
            lower = frame[h - quarter:]
            assert_frame_color(upper, top)
            assert_frame_color(lower, bottom)


class TestE2EHighRes:
    def test_e2e_image_highres(self, tmp_path):
        """Convert 3 solid-color frames at 640x480 resolution."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image(mcap_path, width=640, height=480)

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        frames = read_mp4_frames(mp4_path)
        assert len(frames) == 3
        for frame, expected in zip(frames, DEFAULT_COLORS):
            assert_frame_color(frame, expected)


class TestE2EFPS:
    def test_e2e_fps_calculation(self, tmp_path):
        """Verify output MP4 FPS matches input timestamp intervals (10 fps)."""
        mcap_path = str(tmp_path / "test.mcap")
        mp4_path = str(tmp_path / "output.mp4")
        create_test_mcap_image(mcap_path, fps=10)

        convert_to_mp4(mcap_path, "/camera/image", mp4_path)

        fps = read_mp4_fps(mp4_path)
        assert abs(fps - 10.0) < 1.0, f"Expected ~10 fps, got {fps}"
