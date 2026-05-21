from fractions import Fraction
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser

import constants as C


def main():
    start_time = time.time()

    check_inputs()

    output_fps = get_effective_output_fps()
    rendered_frame_count = get_rendered_frame_count()
    overlay_settings = build_overlay_settings()

    config = build_video_config(
        output_fps=output_fps,
        rendered_frame_count=rendered_frame_count,
        overlay_settings=overlay_settings,
    )

    print_job_info(
        output_fps=output_fps,
        rendered_frame_count=rendered_frame_count,
        overlay_settings=overlay_settings,
    )

    if output_video_is_current(config):
        print("Output video already exists with the same assembly settings. Skipping.")
        return

    if C.SHOW_ORIGINAL_VIDEO and C.WAIT_BEFORE_VIDEO_ASSEMBLY:
        overlay_settings = interactive_overlay_setup(
            output_fps=output_fps,
            overlay_settings=overlay_settings,
        )

        config = build_video_config(
            output_fps=output_fps,
            rendered_frame_count=rendered_frame_count,
            overlay_settings=overlay_settings,
        )

    clear_old_output_video()
    write_video_info(config=config, status="in_progress")

    assemble_video(
        output_fps=output_fps,
        rendered_frame_count=rendered_frame_count,
        overlay_settings=overlay_settings,
    )

    write_video_info(config=config, status="complete")

    elapsed = time.time() - start_time
    print(f"Wrote video: {C.PATH_OUTPUT_VIDEO}")
    print(f"Elapsed: {elapsed:.2f}s")


# ============================================================
# Setup
# ============================================================

def check_inputs():
    for tool in ["ffmpeg", "ffprobe"]:
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} is not installed or not in PATH.")

    if not C.PATH_SOURCE_VIDEO.exists():
        raise RuntimeError(
            f"Source video not found: {C.PATH_SOURCE_VIDEO}\n"
            "Run getVideo.py first."
        )

    if not C.PATH_RENDERED_FRAMES_FOLDER.exists():
        raise RuntimeError(
            f"Rendered frames folder not found: {C.PATH_RENDERED_FRAMES_FOLDER}\n"
            "Run svg_to_desmos_img.py first."
        )


def print_job_info(output_fps, rendered_frame_count, overlay_settings):
    print()
    print("VideoTo2DRenderer Desmos-image-to-video job")
    print("-------------------------------------------")
    print(f"Rendered frames:      {C.PATH_RENDERED_FRAMES_FOLDER}")
    print(f"Source video:         {C.PATH_SOURCE_VIDEO}")
    print(f"Output video:         {C.PATH_OUTPUT_VIDEO}")
    print(f"Video info:           {C.PATH_VIDEO_INFO}")
    print(f"Rendered frame count: {rendered_frame_count}")
    print(f"Output FPS:           {output_fps}")
    print(f"Add audio:            {C.ADD_AUDIO}")
    print(f"Show original video:  {C.SHOW_ORIGINAL_VIDEO}")

    if C.SHOW_ORIGINAL_VIDEO:
        print(f"Overlay x:            {overlay_settings['x']}")
        print(f"Overlay y:            {overlay_settings['y']}")
        print(f"Overlay scale:        {overlay_settings['scale']}")

    print()


# ============================================================
# Rendered frames / FPS
# ============================================================

def get_rendered_frame_count():
    """
    Returns the number of continuous rendered frames:
        frame_00000.png
        frame_00001.png
        ...

    This stage fails if no rendered frames exist.
    """
    if C.PATH_DESMOS_IMG_INFO.exists():
        try:
            data = json.loads(C.PATH_DESMOS_IMG_INFO.read_text(encoding="utf-8"))

            if data.get("status") == "complete":
                count = data.get("rendered_frames")

                if isinstance(count, int) and count > 0:
                    verify_rendered_frames_exist(count)
                    return count

        except json.JSONDecodeError:
            pass

    count = count_continuous_frames()

    if count <= 0:
        raise RuntimeError(
            f"No rendered PNG frame sequence found in: {C.PATH_RENDERED_FRAMES_FOLDER}\n"
            "Run svg_to_desmos_img.py first."
        )

    return count


def verify_rendered_frames_exist(count):
    for index in range(count):
        path = C.PATH_RENDERED_FRAMES_FOLDER / f"frame_{index:05d}.png"

        if not path.exists():
            raise RuntimeError(
                f"Missing rendered frame: {path}\n"
                "Run svg_to_desmos_img.py again."
            )


def count_continuous_frames():
    count = 0

    while True:
        path = C.PATH_RENDERED_FRAMES_FOLDER / f"frame_{count:05d}.png"

        if not path.exists():
            return count

        count += 1


def get_effective_output_fps():
    if C.OUTPUT_FPS is not None:
        return str(C.OUTPUT_FPS)

    return get_video_fps(C.PATH_SOURCE_VIDEO)


def get_video_fps(video_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate",
        "-of", "json",
        str(video_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    stream = data["streams"][0]

    fps_text = stream.get("avg_frame_rate")

    if not fps_text or fps_text == "0/0":
        fps_text = stream.get("r_frame_rate")

    if not fps_text or fps_text == "0/0":
        raise RuntimeError(f"Could not determine FPS for {video_path}")

    fps = Fraction(fps_text)

    if fps.denominator == 1:
        return str(fps.numerator)

    return f"{fps.numerator}/{fps.denominator}"


def fps_to_fraction(fps):
    if isinstance(fps, Fraction):
        return fps

    if isinstance(fps, int):
        return Fraction(fps, 1)

    if isinstance(fps, float):
        return Fraction(fps).limit_denominator(100000)

    return Fraction(str(fps))


def get_source_offset_seconds(output_fps):
    fps_fraction = fps_to_fraction(output_fps)

    return float(Fraction(C.START_INDEX, 1) / fps_fraction)


# ============================================================
# Overlay setup
# ============================================================

def build_overlay_settings():
    return {
        "x": int(C.ORIGINAL_VIDEO_OVERLAY_X),
        "y": int(C.ORIGINAL_VIDEO_OVERLAY_Y),
        "scale": float(C.ORIGINAL_VIDEO_OVERLAY_SCALE),
    }


def interactive_overlay_setup(output_fps, overlay_settings):
    create_overlay_preview_html()
    generate_overlay_preview(output_fps=output_fps, overlay_settings=overlay_settings)

    webbrowser.open(C.PATH_OVERLAY_PREVIEW_HTML.resolve().as_uri())

    print()
    print("Original-video overlay preview opened.")
    print("Controls:")
    print("  w/a/s/d  move overlay")
    print("  + / -    scale overlay")
    print("  Enter    start video assembly")
    print("  q        cancel")
    print()

    if not sys.stdin.isatty():
        input("Terminal does not support single-key input. Press Enter to start.")
        return overlay_settings

    if os.name == "nt":
        return interactive_overlay_setup_windows(output_fps, overlay_settings)

    return interactive_overlay_setup_unix(output_fps, overlay_settings)


def interactive_overlay_setup_windows(output_fps, overlay_settings):
    import msvcrt

    while True:
        key = msvcrt.getch().decode(errors="ignore").lower()

        if key in ("\r", "\n"):
            return overlay_settings

        if key == "q":
            raise KeyboardInterrupt("Video assembly cancelled by user.")

        update_overlay_from_key(key, overlay_settings)
        generate_overlay_preview(output_fps, overlay_settings)
        print_overlay_settings(overlay_settings)


def interactive_overlay_setup_unix(output_fps, overlay_settings):
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while True:
            key = sys.stdin.read(1).lower()

            if key in ("\r", "\n"):
                return overlay_settings

            if key == "q":
                raise KeyboardInterrupt("Video assembly cancelled by user.")

            update_overlay_from_key(key, overlay_settings)
            generate_overlay_preview(output_fps, overlay_settings)
            print_overlay_settings(overlay_settings)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def update_overlay_from_key(key, overlay_settings):
    if key == "w":
        overlay_settings["y"] -= C.OVERLAY_MOVE_STEP
    elif key == "s":
        overlay_settings["y"] += C.OVERLAY_MOVE_STEP
    elif key == "a":
        overlay_settings["x"] -= C.OVERLAY_MOVE_STEP
    elif key == "d":
        overlay_settings["x"] += C.OVERLAY_MOVE_STEP
    elif key in ("+", "="):
        overlay_settings["scale"] += C.OVERLAY_SCALE_STEP
    elif key in ("-", "_"):
        overlay_settings["scale"] -= C.OVERLAY_SCALE_STEP

    overlay_settings["scale"] = max(0.01, overlay_settings["scale"])


def print_overlay_settings(overlay_settings):
    print(
        f"Overlay: x={overlay_settings['x']}, "
        f"y={overlay_settings['y']}, "
        f"scale={overlay_settings['scale']:.3f}"
    )


def create_overlay_preview_html():
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Overlay Preview</title>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #222;
      color: white;
      font-family: sans-serif;
      text-align: center;
    }}

    img {{
      max-width: 100vw;
      max-height: 95vh;
      object-fit: contain;
    }}

    #info {{
      padding: 8px;
    }}
  </style>
</head>
<body>
  <div id="info">Overlay preview auto-refreshes. Use terminal controls.</div>
  <img id="preview" src="{C.FILE_OVERLAY_PREVIEW_IMAGE}">
  <script>
    const img = document.getElementById("preview");

    setInterval(() => {{
      img.src = "{C.FILE_OVERLAY_PREVIEW_IMAGE}?t=" + Date.now();
    }}, 500);
  </script>
</body>
</html>
"""

    C.PATH_OVERLAY_PREVIEW_HTML.write_text(html, encoding="utf-8")


def generate_overlay_preview(output_fps, overlay_settings):
    first_frame = C.PATH_RENDERED_FRAMES_FOLDER / "frame_00000.png"

    if not first_frame.exists():
        raise RuntimeError(f"Missing first rendered frame: {first_frame}")

    offset_seconds = get_source_offset_seconds(output_fps)
    filter_complex = build_overlay_filter(overlay_settings)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(first_frame),
        "-ss", str(offset_seconds),
        "-i", str(C.PATH_SOURCE_VIDEO),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-frames:v", "1",
        str(C.PATH_OVERLAY_PREVIEW_IMAGE),
    ]

    subprocess.run(cmd, check=True)


# ============================================================
# Cache
# ============================================================

def build_video_config(output_fps, rendered_frame_count, overlay_settings):
    return {
        "video_assembly_cache_version": C.VIDEO_ASSEMBLY_CACHE_VERSION,

        "source_video": file_signature(C.PATH_SOURCE_VIDEO),

        "rendered_frames_folder": str(C.PATH_RENDERED_FRAMES_FOLDER.resolve()),
        "rendered_frame_count": rendered_frame_count,
        "rendered_frames_fingerprint": fingerprint_rendered_frames(rendered_frame_count),

        "output_video": str(C.PATH_OUTPUT_VIDEO.resolve()),
        "output_fps": str(output_fps),

        "start_index": C.START_INDEX,

        "add_audio": C.ADD_AUDIO,
        "show_original_video": C.SHOW_ORIGINAL_VIDEO,

        "overlay_settings": overlay_settings if C.SHOW_ORIGINAL_VIDEO else None,
    }


def output_video_is_current(current_config):
    if not C.PATH_OUTPUT_VIDEO.exists():
        return False

    if C.PATH_OUTPUT_VIDEO.stat().st_size == 0:
        return False

    if not C.PATH_VIDEO_INFO.exists():
        return False

    try:
        previous = json.loads(C.PATH_VIDEO_INFO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    return (
        previous.get("status") == "complete"
        and previous.get("config") == current_config
    )


def write_video_info(config, status):
    data = {
        "status": status,
        "config": config,
    }

    C.PATH_VIDEO_INFO.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def file_signature(path):
    path = path.resolve()
    stat = path.stat()

    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def fingerprint_rendered_frames(rendered_frame_count):
    hasher = hashlib.sha256()

    for index in range(rendered_frame_count):
        path = C.PATH_RENDERED_FRAMES_FOLDER / f"frame_{index:05d}.png"

        if not path.exists():
            raise RuntimeError(f"Missing rendered frame: {path}")

        stat = path.stat()
        item = f"{path.name}|{stat.st_size}|{stat.st_mtime_ns}\n"
        hasher.update(item.encode("utf-8"))

    return hasher.hexdigest()


# ============================================================
# Video assembly
# ============================================================

def clear_old_output_video():
    if C.PATH_OUTPUT_VIDEO.exists():
        print(f"Removing old output video: {C.PATH_OUTPUT_VIDEO}")
        C.PATH_OUTPUT_VIDEO.unlink()


def assemble_video(output_fps, rendered_frame_count, overlay_settings):
    input_pattern = C.PATH_RENDERED_FRAMES_FOLDER / "frame_%05d.png"

    needs_source_video = C.ADD_AUDIO or C.SHOW_ORIGINAL_VIDEO
    offset_seconds = get_source_offset_seconds(output_fps)

    cmd = [
        "ffmpeg",
        "-y",
        "-framerate", str(output_fps),
        "-i", str(input_pattern),
    ]

    if needs_source_video:
        cmd += [
            "-ss", str(offset_seconds),
            "-i", str(C.PATH_SOURCE_VIDEO),
        ]

    if C.SHOW_ORIGINAL_VIDEO:
        cmd += [
            "-filter_complex", build_overlay_filter(overlay_settings),
            "-map", "[vout]",
        ]
    else:
        cmd += ["-map", "0:v"]

    if C.ADD_AUDIO:
        cmd += [
            "-map", "1:a?",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    cmd += [
        "-frames:v", str(rendered_frame_count),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(C.PATH_OUTPUT_VIDEO),
    ]

    print()
    print("Assembling video...")
    print(" ".join(cmd))

    subprocess.run(cmd, check=True)


def build_overlay_filter(overlay_settings):
    scale = overlay_settings["scale"]
    x = overlay_settings["x"]
    y = overlay_settings["y"]

    return (
        f"[1:v]scale=iw*{scale}:ih*{scale}[orig];"
        f"[0:v][orig]overlay={x}:{y}:format=auto[vout]"
    )


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    main()
