from pathlib import Path
from fractions import Fraction
import json
import shutil
import subprocess
import sys

import constants

import numpy as np


# =====================
# Settings you can edit
# =====================

INPUT_MP4 = Path(constants.FOLDER_NAME) / constants.SOURCE_VIDEO_NAME
OUTPUT_DIR = Path(constants.FOLDER_NAME) / "output_svg"
RUN_INFO_FILE = OUTPUT_DIR / "processing_info.txt"

# Set to None to use the video's original FPS.
FPS = constants.FPS

# Set to None to use the video's original width.
SCALE_WIDTH = constants.SCALE_WIDTH

# Use "edges" for Desmos-style line art.
# Use "threshold" for black/white silhouette style.
MODE = "edges"

# Used only in MODE = "threshold"
THRESHOLD = 140

# Used only in MODE = "edges"
EDGE_THRESHOLD = 35

# Potrace simplification/noise settings
TURD_SIZE = 8
OPT_TOLERANCE = 0.8

# Set to None for the whole video.
# Set to a small number like 10 for testing.
FRAME_LIMIT = constants.FRAME_LIMIT


def main():
    check_tools()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    video_info = get_video_info(INPUT_MP4)

    effective_fps = video_info["fps"] if FPS is None else to_fraction(FPS)
    width, height = get_output_size(video_info, SCALE_WIDTH)

    config = build_config(
        video_info=video_info,
        effective_fps=effective_fps,
        width=width,
        height=height,
    )

    print(f"Input: {INPUT_MP4}")
    print(f"Source size: {video_info['source_width']}x{video_info['source_height']}")
    print(f"Output size: {width}x{height}")
    print(f"FPS: {format_fraction(effective_fps)}")
    print(f"Mode: {MODE}")
    print(f"Output folder: {OUTPUT_DIR}")

    if already_processed(config):
        print("Already processed with the same settings. Skipping.")
        return

    clear_old_svg_files()

    write_run_info(config, processed_frames=0, status="in_progress")

    frame_count = process_video_to_svgs(
        width=width,
        height=height,
        effective_fps=effective_fps,
    )

    write_run_info(config, processed_frames=frame_count, status="complete")

    print(f"Done. Created {frame_count} SVG files.")


def check_tools():
    for tool in ["ffmpeg", "ffprobe", "potrace"]:
        if shutil.which(tool) is None:
            print(f"Error: {tool} is not installed or not in PATH.")
            sys.exit(1)


def get_video_info(video_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,duration",
        "-show_entries",
        "format=duration",
        "-of", "json",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    stream = data["streams"][0]
    format_data = data.get("format", {})

    source_width = int(stream["width"])
    source_height = int(stream["height"])

    fps = parse_fps(stream.get("avg_frame_rate"))

    if fps is None:
        fps = parse_fps(stream.get("r_frame_rate"))

    if fps is None:
        raise RuntimeError("Could not detect video FPS.")

    duration = stream.get("duration") or format_data.get("duration")
    duration = float(duration) if duration is not None else None

    nb_frames = stream.get("nb_frames")
    nb_frames = int(nb_frames) if nb_frames and nb_frames.isdigit() else None

    input_path = Path(video_path)
    stat = input_path.stat()

    return {
        "input_file": str(input_path.resolve()),
        "input_size_bytes": stat.st_size,
        "input_modified_ns": stat.st_mtime_ns,
        "source_width": source_width,
        "source_height": source_height,
        "fps": fps,
        "duration": duration,
        "nb_frames": nb_frames,
    }


def parse_fps(value):
    if not value or value == "0/0":
        return None

    try:
        fps = Fraction(value)
    except ValueError:
        return None

    if fps <= 0:
        return None

    return fps


def to_fraction(value):
    if isinstance(value, Fraction):
        return value

    if isinstance(value, int):
        return Fraction(value, 1)

    if isinstance(value, float):
        return Fraction(value).limit_denominator(100000)

    if isinstance(value, str):
        return Fraction(value)

    raise TypeError(f"Cannot convert {value!r} to FPS fraction.")


def format_fraction(value):
    if value.denominator == 1:
        return str(value.numerator)

    return f"{value.numerator}/{value.denominator}"


def get_output_size(video_info, scale_width):
    source_width = video_info["source_width"]
    source_height = video_info["source_height"]

    if scale_width is None:
        return source_width, source_height

    target_width = int(scale_width)
    target_height = round(source_height * target_width / source_width)

    return target_width, target_height


def build_config(video_info, effective_fps, width, height):
    return {
        "script_version": 2,

        "input_file": video_info["input_file"],
        "input_size_bytes": video_info["input_size_bytes"],
        "input_modified_ns": video_info["input_modified_ns"],

        "source_width": video_info["source_width"],
        "source_height": video_info["source_height"],
        "source_fps": format_fraction(video_info["fps"]),
        "source_duration": video_info["duration"],
        "source_nb_frames": video_info["nb_frames"],

        "requested_fps": "source" if FPS is None else str(FPS),
        "effective_fps": format_fraction(effective_fps),

        "requested_scale_width": "source" if SCALE_WIDTH is None else SCALE_WIDTH,
        "output_width": width,
        "output_height": height,

        "mode": MODE,
        "threshold": THRESHOLD,
        "edge_threshold": EDGE_THRESHOLD,
        "turd_size": TURD_SIZE,
        "opt_tolerance": OPT_TOLERANCE,
        "frame_limit": FRAME_LIMIT,
    }


def already_processed(current_config):
    if not RUN_INFO_FILE.exists():
        return False

    try:
        previous = json.loads(RUN_INFO_FILE.read_text())
    except json.JSONDecodeError:
        print("Found old processing_info.txt, but it is not valid JSON. Reprocessing.")
        return False

    previous_config = previous.get("config")
    previous_status = previous.get("status")
    previous_frame_count = previous.get("processed_frames")

    if previous_config != current_config:
        print("Settings changed since last run. Reprocessing.")
        return False

    if previous_status != "complete":
        print("Previous run was not complete. Reprocessing.")
        return False

    if previous_frame_count is None:
        print("Previous run info has no frame count. Reprocessing.")
        return False

    actual_svg_count = len(list(OUTPUT_DIR.glob("frame_*.svg")))

    if actual_svg_count != previous_frame_count:
        print(
            f"Expected {previous_frame_count} SVG files, "
            f"but found {actual_svg_count}. Reprocessing."
        )
        return False

    return True


def write_run_info(config, processed_frames, status):
    data = {
        "status": status,
        "processed_frames": processed_frames,
        "config": config,
    }

    RUN_INFO_FILE.write_text(json.dumps(data, indent=2))


def clear_old_svg_files():
    old_files = list(OUTPUT_DIR.glob("frame_*.svg"))

    if old_files:
        print(f"Removing {len(old_files)} old SVG files...")

    for path in old_files:
        path.unlink()


def process_video_to_svgs(width, height, effective_fps):
    frame_size = width * height

    filter_parts = []

    if FPS is not None:
        filter_parts.append(f"fps={format_fraction(effective_fps)}")

    if SCALE_WIDTH is not None:
        filter_parts.append(f"scale={width}:{height}")

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", INPUT_MP4,
    ]

    if filter_parts:
        ffmpeg_cmd += ["-vf", ",".join(filter_parts)]

    ffmpeg_cmd += [
        "-f", "rawvideo",
        "-pix_fmt", "gray",
    ]

    if FRAME_LIMIT is not None:
        ffmpeg_cmd += ["-frames:v", str(FRAME_LIMIT)]

    ffmpeg_cmd += ["-"]

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    frame_index = 0

    try:
        while True:
            raw_frame = process.stdout.read(frame_size)

            if len(raw_frame) == 0:
                break

            if len(raw_frame) != frame_size:
                print("Warning: incomplete frame received, stopping.")
                break

            gray = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width))

            black_white = process_frame(gray)

            pbm_data = bitmap_to_pbm(black_white, width, height)

            output_svg = OUTPUT_DIR / f"frame_{frame_index:05d}.svg"

            run_potrace(pbm_data, output_svg)

            frame_index += 1

            if frame_index % 10 == 0:
                print(f"Processed {frame_index} frames...")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Stopping ffmpeg...")
        process.kill()
        process.wait()
        raise

    process.wait()

    if process.returncode != 0:
        stderr = process.stderr.read().decode(errors="replace")
        raise RuntimeError(f"ffmpeg failed:\n{stderr}")

    return frame_index


def process_frame(gray):
    if MODE == "threshold":
        # Dark pixels become black, light pixels become white.
        return gray < THRESHOLD

    if MODE == "edges":
        # Simple edge detection.
        gray_int = gray.astype(np.int16)

        dx = np.abs(gray_int[:, 1:] - gray_int[:, :-1])
        dy = np.abs(gray_int[1:, :] - gray_int[:-1, :])

        edges = np.zeros_like(gray, dtype=np.uint8)
        edges[:, 1:] = np.maximum(edges[:, 1:], dx)
        edges[1:, :] = np.maximum(edges[1:, :], dy)

        # Strong edges become black.
        return edges > EDGE_THRESHOLD

    raise ValueError(f"Unknown MODE: {MODE}")


def bitmap_to_pbm(black_pixels, width, height):
    """
    Converts a boolean image to binary PBM format.

    In PBM:
    1 = black
    0 = white
    """
    packed_bits = np.packbits(
        black_pixels.astype(np.uint8),
        axis=1,
        bitorder="big",
    )

    header = f"P4\n{width} {height}\n".encode("ascii")

    return header + packed_bits.tobytes()


def run_potrace(pbm_data, output_svg):
    cmd = [
        "potrace",
        "-s",
        "--turdsize", str(TURD_SIZE),
        "--opttolerance", str(OPT_TOLERANCE),
        "-o", str(output_svg),
        "-",
    ]

    result = subprocess.run(
        cmd,
        input=pbm_data,
        capture_output=True,
    )

    if result.returncode != 0:
        print("Potrace error:")
        print(result.stderr.decode(errors="replace"))
        raise RuntimeError("potrace failed")


if __name__ == "__main__":
    main()