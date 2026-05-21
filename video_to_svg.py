from fractions import Fraction
import json
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

import constants as C


def main():
    start_time = time.time()

    check_tools()
    ensure_folders()

    video_info = get_video_info(C.PATH_SOURCE_VIDEO)

    effective_fps = video_info["fps"] if C.FPS is None else to_fraction(C.FPS)
    width, height = get_output_size(video_info, C.SCALE_WIDTH)

    config = build_config(
        video_info=video_info,
        effective_fps=effective_fps,
        width=width,
        height=height,
    )

    print_project_info(
        video_info=video_info,
        width=width,
        height=height,
        effective_fps=effective_fps,
    )

    if already_processed(config):
        print("SVG frames already exist with the same settings. Skipping.")
        return

    clear_old_svg_files()

    write_run_info(
        config=config,
        processed_frames=0,
        status="in_progress",
    )

    frame_count = process_video_to_svgs(
        width=width,
        height=height,
        effective_fps=effective_fps,
    )

    write_run_info(
        config=config,
        processed_frames=frame_count,
        status="complete",
    )

    elapsed = time.time() - start_time

    print(f"Done. Created {frame_count} SVG files.")
    print(f"Elapsed: {elapsed:.2f}s")


# ============================================================
# Setup
# ============================================================

def check_tools():
    for tool in ["ffmpeg", "ffprobe"]:
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} is not installed or not in PATH.")

    if C.VIDEO_PROCESSING_MODE == "threshold":
        if shutil.which("potrace") is None:
            raise RuntimeError("potrace is not installed or not in PATH.")

    if not C.PATH_SOURCE_VIDEO.exists():
        raise RuntimeError(f"Source video not found: {C.PATH_SOURCE_VIDEO}")


def ensure_folders():
    C.PATH_VIDEO_FOLDER.mkdir(parents=True, exist_ok=True)
    C.PATH_SVG_FOLDER.mkdir(parents=True, exist_ok=True)


def print_project_info(video_info, width, height, effective_fps):
    print()
    print("VideoTo2DRenderer SVG job")
    print("-------------------------")
    print(f"Project root:       {C.PROJECT_ROOT}")
    print(f"Video folder:       {C.PATH_VIDEO_FOLDER}")
    print(f"Source video:       {C.PATH_SOURCE_VIDEO}")
    print(f"Output SVG folder:  {C.PATH_SVG_FOLDER}")
    print(f"Processing info:    {C.PATH_PROCESSING_INFO}")
    print(f"Source size:        {video_info['source_width']}x{video_info['source_height']}")
    print(f"Output size:        {width}x{height}")
    print(f"FPS:                {format_fraction(effective_fps)}")
    print(f"Mode:               {C.VIDEO_PROCESSING_MODE}")
    print(f"Frame limit:        {C.FRAME_LIMIT}")
    print()


# ============================================================
# Video metadata
# ============================================================

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
        str(video_path),
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

    video_path = video_path.resolve()
    stat = video_path.stat()

    return {
        "input_file": str(video_path),
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


# ============================================================
# Cache / processing info
# ============================================================

def build_config(video_info, effective_fps, width, height):
    return {
        "video_to_svg_cache_version": C.VIDEO_TO_SVG_CACHE_VERSION,

        "input_file": video_info["input_file"],
        "input_size_bytes": video_info["input_size_bytes"],
        "input_modified_ns": video_info["input_modified_ns"],

        "source_width": video_info["source_width"],
        "source_height": video_info["source_height"],
        "source_fps": format_fraction(video_info["fps"]),
        "source_duration": video_info["duration"],
        "source_nb_frames": video_info["nb_frames"],

        "requested_fps": "source" if C.FPS is None else str(C.FPS),
        "effective_fps": format_fraction(effective_fps),

        "requested_scale_width": "source" if C.SCALE_WIDTH is None else C.SCALE_WIDTH,
        "output_width": width,
        "output_height": height,

        "frame_limit": C.FRAME_LIMIT,

        "video_processing_mode": C.VIDEO_PROCESSING_MODE,

        "threshold": C.THRESHOLD,

        "canny_blur_size": C.CANNY_BLUR_SIZE,
        "canny_low_threshold": C.CANNY_LOW_THRESHOLD,
        "canny_high_threshold": C.CANNY_HIGH_THRESHOLD,
        "edge_min_contour_points": C.EDGE_MIN_CONTOUR_POINTS,
        "edge_simplify_epsilon": C.EDGE_SIMPLIFY_EPSILON,
        "edge_stroke_width": C.EDGE_STROKE_WIDTH,
        "edge_stroke_color": C.EDGE_STROKE_COLOR,

        "potrace_unit": C.POTRACE_UNIT,
        "turd_size": C.TURD_SIZE,
        "opt_tolerance": C.OPT_TOLERANCE,
    }


def already_processed(current_config):
    if not C.PATH_PROCESSING_INFO.exists():
        return False

    try:
        previous = json.loads(C.PATH_PROCESSING_INFO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("processing_info.txt is not valid JSON. Reprocessing.")
        return False

    if previous.get("status") != "complete":
        print("Previous SVG processing was not complete. Reprocessing.")
        return False

    if previous.get("config") != current_config:
        print("SVG processing settings changed. Reprocessing.")
        return False

    expected_frames = previous.get("processed_frames")

    if not isinstance(expected_frames, int) or expected_frames <= 0:
        print("processing_info.txt has invalid frame count. Reprocessing.")
        return False

    actual_svg_count = len(list(C.PATH_SVG_FOLDER.glob("frame_*.svg")))

    if actual_svg_count != expected_frames:
        print(
            f"Expected {expected_frames} SVG files, "
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

    C.PATH_PROCESSING_INFO.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def clear_old_svg_files():
    old_files = list(C.PATH_SVG_FOLDER.glob("frame_*.svg"))

    if old_files:
        print(f"Removing {len(old_files)} old SVG files...")

    for path in old_files:
        path.unlink()


# ============================================================
# Main conversion
# ============================================================

def process_video_to_svgs(width, height, effective_fps):
    frame_size = width * height

    filter_parts = []

    if C.FPS is not None:
        filter_parts.append(f"fps={format_fraction(effective_fps)}")

    if C.SCALE_WIDTH is not None:
        filter_parts.append(f"scale={width}:{height}")

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-i", str(C.PATH_SOURCE_VIDEO),
    ]

    if filter_parts:
        ffmpeg_cmd += ["-vf", ",".join(filter_parts)]

    ffmpeg_cmd += [
        "-f", "rawvideo",
        "-pix_fmt", "gray",
    ]

    if C.FRAME_LIMIT is not None:
        ffmpeg_cmd += ["-frames:v", str(C.FRAME_LIMIT)]

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

            output_svg = C.PATH_SVG_FOLDER / f"frame_{frame_index:05d}.svg"

            write_frame_svg(
                gray=gray,
                output_svg=output_svg,
                width=width,
                height=height,
            )

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


def write_frame_svg(gray, output_svg, width, height):
    if C.VIDEO_PROCESSING_MODE == "edges":
        write_centerline_edge_svg(gray, output_svg, width, height)
        return

    if C.VIDEO_PROCESSING_MODE == "threshold":
        black_white = gray < C.THRESHOLD
        pbm_data = bitmap_to_pbm(black_white, width, height)
        run_potrace(pbm_data, output_svg)
        return

    raise ValueError(f"Unknown VIDEO_PROCESSING_MODE: {C.VIDEO_PROCESSING_MODE}")


# ============================================================
# Better edge mode: Canny → SVG stroke paths
# ============================================================

def write_centerline_edge_svg(gray, output_svg, width, height):
    """
    Creates SVG stroke paths directly from Canny contours.

    Important:
    This does NOT use Potrace.

    Potrace outlines black pixel regions, which is why the old edge mode
    produced two lines for one visual stroke. This mode writes centerline
    SVG paths with fill='none' and stroke='black'.
    """
    edges = detect_canny_edges(gray)

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_NONE,
    )

    path_strings = []

    for contour in contours:
        points = contour.reshape(-1, 2)

        if len(points) < C.EDGE_MIN_CONTOUR_POINTS:
            continue

        points = simplify_contour(points)

        if len(points) < C.EDGE_MIN_CONTOUR_POINTS:
            continue

        path_strings.append(points_to_svg_path(points))

    svg_text = build_stroke_svg(
        width=width,
        height=height,
        path_strings=path_strings,
    )

    output_svg.write_text(svg_text, encoding="utf-8")


def detect_canny_edges(gray):
    blur_size = int(C.CANNY_BLUR_SIZE)

    if blur_size > 1:
        if blur_size % 2 == 0:
            blur_size += 1

        gray = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)

    edges = cv2.Canny(
        gray,
        threshold1=int(C.CANNY_LOW_THRESHOLD),
        threshold2=int(C.CANNY_HIGH_THRESHOLD),
        L2gradient=True,
    )

    return edges


def simplify_contour(points):
    epsilon = float(C.EDGE_SIMPLIFY_EPSILON)

    if epsilon <= 0:
        return points

    contour = points.reshape(-1, 1, 2).astype(np.int32)

    simplified = cv2.approxPolyDP(
        contour,
        epsilon=epsilon,
        closed=False,
    )

    return simplified.reshape(-1, 2)


def points_to_svg_path(points):
    first_x, first_y = points[0]

    commands = [f"M {int(first_x)} {int(first_y)}"]

    for x, y in points[1:]:
        commands.append(f"L {int(x)} {int(y)}")

    return " ".join(commands)


def build_stroke_svg(width, height, path_strings):
    paths = []

    for d in path_strings:
        paths.append(
            f'<path d="{d}" '
            f'fill="none" '
            f'stroke="{C.EDGE_STROKE_COLOR}" '
            f'stroke-width="{C.EDGE_STROKE_WIDTH}" '
            f'stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )

    body = "\n  ".join(paths)

    return f"""<?xml version="1.0" standalone="no"?>
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  {body}
</svg>
"""


# ============================================================
# Threshold mode: bitmap → Potrace
# ============================================================

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
        "--unit", str(C.POTRACE_UNIT),
        "--turdsize", str(C.TURD_SIZE),
        "--opttolerance", str(C.OPT_TOLERANCE),
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


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    main()