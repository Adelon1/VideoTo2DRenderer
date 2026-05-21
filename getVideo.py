import json
import shutil
import subprocess
import time

import constants as C
import inputs


def main():
    start_time = time.time()

    check_tools()
    ensure_video_folder()

    youtube_link = get_youtube_link()
    config = build_download_config(youtube_link)

    print_job_info(youtube_link)

    if download_is_current(config):
        print("Source video already exists with the same download settings. Skipping.")
        return

    if not youtube_link:
        raise RuntimeError(
            "No YouTube link found in inputs.py, and the existing source video "
            "does not match the current download cache."
        )

    clear_old_source_video()
    write_download_info(config=config, status="in_progress")

    download_video(youtube_link)

    write_download_info(config=config, status="complete")

    elapsed = time.time() - start_time
    print(f"Video downloaded successfully: {C.PATH_SOURCE_VIDEO}")
    print(f"Elapsed: {elapsed:.2f}s")


# ============================================================
# Setup
# ============================================================

def check_tools():
    for tool in ["yt-dlp", "ffmpeg"]:
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} is not installed or not in PATH.\n"
                "On Arch, install with:\n"
                "sudo pacman -S yt-dlp ffmpeg"
            )


def ensure_video_folder():
    C.PATH_VIDEO_FOLDER.mkdir(parents=True, exist_ok=True)


def get_youtube_link():
    return (inputs.YOUTUBE_LINK or "").strip()


def print_job_info(youtube_link):
    print()
    print("VideoTo2DRenderer download job")
    print("------------------------------")
    print(f"Source video:  {C.PATH_SOURCE_VIDEO}")
    print(f"Download info: {C.PATH_DOWNLOAD_INFO}")
    print(f"YouTube link:  {youtube_link or '(empty)'}")
    print()


# ============================================================
# Cache
# ============================================================

def build_download_config(youtube_link):
    return {
        "download_cache_version": C.DOWNLOAD_CACHE_VERSION,
        "youtube_link": youtube_link,
        "output_file": str(C.PATH_SOURCE_VIDEO.resolve()),
        "yt_dlp_format": C.YTDLP_FORMAT,
        "merge_output_format": C.YTDLP_MERGE_OUTPUT_FORMAT,
    }


def download_is_current(current_config):
    if not C.PATH_SOURCE_VIDEO.exists():
        return False

    if C.PATH_SOURCE_VIDEO.stat().st_size == 0:
        return False

    if not C.PATH_DOWNLOAD_INFO.exists():
        return False

    try:
        previous = json.loads(C.PATH_DOWNLOAD_INFO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    return (
        previous.get("status") == "complete"
        and previous.get("config") == current_config
    )


def write_download_info(config, status):
    data = {
        "status": status,
        "config": config,
    }

    C.PATH_DOWNLOAD_INFO.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


# ============================================================
# Download
# ============================================================

def clear_old_source_video():
    if C.PATH_SOURCE_VIDEO.exists():
        print(f"Removing old source video: {C.PATH_SOURCE_VIDEO}")
        C.PATH_SOURCE_VIDEO.unlink()


def download_video(youtube_link):
    print(f"Downloading video from: {youtube_link}")

    command = [
        "yt-dlp",
        "--no-playlist",
        "-f", C.YTDLP_FORMAT,
        "--merge-output-format", C.YTDLP_MERGE_OUTPUT_FORMAT,
        "-o", str(C.PATH_SOURCE_VIDEO),
        youtube_link,
    ]

    try:
        subprocess.run(
            command,
            check=True,
            cwd=C.PATH_VIDEO_FOLDER,
        )

    except subprocess.CalledProcessError as exc:
        write_download_info(
            config=build_download_config(youtube_link),
            status="failed",
        )

        raise RuntimeError(f"yt-dlp failed with exit code {exc.returncode}") from exc


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    main()
