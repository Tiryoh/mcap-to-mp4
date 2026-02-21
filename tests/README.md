# Tests

## Unit Tests (`test_cli.py`)

Mock-based tests for individual functions in `mcap_to_mp4/cli.py`.

| Test | Description |
|------|-------------|
| `test_parse_arguments` | Verify argument parsing with all options specified |
| `test_parse_arguments_minimal` | Verify defaults when only input is given |
| `test_check_file_exists_valid` | Existing file does not raise |
| `test_check_file_exists_invalid` | Missing file raises `RuntimeError` |
| `test_get_image_topic_list` | Returns Image topics from mocked MCAP summary |
| `test_get_image_topic_list_compressed` | Returns CompressedImage topics |
| `test_convert_to_mp4_frame_count` | Correct number of frames written to video writer |
| `test_convert_to_mp4_compressed_image` | CompressedImage frames are written correctly |
| `test_convert_to_mp4_identical_timestamps` | Identical timestamps cause `sys.exit(1)` |
| `test_convert_to_mp4_fps` | FPS passed to `imageio.get_writer` matches timestamp intervals |

## End-to-End Tests (`test_e2e.py`)

Real MCAP-to-MP4 conversion tests using `mcap_ros2.writer.Writer` to generate MCAP files, then verifying the output MP4 content.

| Test | Description |
|------|-------------|
| `test_e2e_image_rgb8` | 3 solid-color `rgb8` Image frames → MP4. Verify frame count and colors. |
| `test_e2e_image_bgr8` | 3 solid-color `bgr8` Image frames → MP4. Verify BGR→RGB conversion. |
| `test_e2e_compressed_rgb` | 3 JPEG CompressedImage frames → MP4. Verify colors (with JPEG tolerance). |
| `test_e2e_compressed_color_passthrough` | Feed non-primary colors through JPEG pipeline. Verify pixel values are preserved as-is (no channel swap). |
| `test_e2e_topic_list` | MCAP with Image, CompressedImage, and String topics. Verify `get_image_topic_list()` returns only image topics. |
| `test_e2e_image_multicolor[R-G/R-B/G-B]` | Single frame with top/bottom halves in different colors (`rgb8`). Verify spatial color layout. |
| `test_e2e_image_multicolor_bgr8[R-G/R-B/G-B]` | Same split-color test with `bgr8`. Verify BGR→RGB preserves spatial layout. |
| `test_e2e_image_highres` | 3 solid-color frames at 640×480 resolution. Verify correctness at higher resolution. |
| `test_e2e_fps_calculation` | Frames with 100ms intervals (10 fps). Verify output MP4 FPS metadata. |

## Running Tests

```bash
# Run all tests
uv run pytest tests -v

# Run only E2E tests
uv run pytest tests/test_e2e.py -v

# Run only unit tests
uv run pytest tests/test_cli.py -v
```
