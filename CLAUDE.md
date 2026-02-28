# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mcap-to-mp4 is a Python CLI tool that converts ROS 2 rosbag2 recordings (MCAP format) to MP4 video files. It does not require a ROS 2 runtime.

## Commands

```bash
# Install dependencies (dev)
uv sync --group dev

# Run the tool
uv run mcap-to-mp4 <path_to_mcap> -t <topic_name> -o <output.mp4>

# Run tests
uv run pytest tests

# Lint
uv run flake8 .

# Type check
uv run mypy --config-file .mypy.ini .

# Run all pre-push checks (flake8, mypy, pytest)
prek run --all-files --stage pre-push

# Install pre-push hook (first time setup)
prek install --hook-type pre-push
```

## Architecture

The codebase is a single-module CLI tool in `mcap_to_mp4/cli.py`:

- **`parse_arguments()`** — argparse setup for `input`, `-t/--topic`, `-o/--output`
- **`get_image_topic_list()`** — scans MCAP file for `sensor_msgs/msg/Image` and `sensor_msgs/msg/CompressedImage` topics
- **`convert_to_mp4()`** — reads MCAP messages, decodes image frames (handling BGR8→RGB conversion for uncompressed, PIL decompression for compressed), calculates FPS from mean timestamp intervals, writes MP4 via imageio/ffmpeg

Entry point: `mcap-to-mp4` → `mcap_to_mp4.cli:main`

## Git / Pull Request Workflow

- Do NOT use `git rebase` on PR branches. PR review comments are tied to commits, and rebasing makes them hard to find.
- PRs are squash-merged, so there is no need to keep commit history clean. Prefer additional commits over rewriting history.

## Code Style

- Max line length: 99 (configured in `.flake8`)
- Google import order style (flake8-isort)
- MyPy with `ignore_missing_imports = True`
- Python 3.10+, managed with uv (hatchling build backend)
