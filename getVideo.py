import subprocess
from pathlib import Path

import constants
import inputs


def main():
    try:
        work_dir = get_work_dir()
    except ValueError as exc:
        print(exc)
        return

    get_video(work_dir)


def get_work_dir() -> Path:
    folder_name = (constants.FOLDER_NAME or "").strip()
    if not folder_name:
        raise ValueError("constants.FOLDER_NAME is empty. Set a folder name in constants.py.")

    base_dir = Path(__file__).resolve().parent
    work_dir = base_dir / folder_name
    if work_dir.exists() and not work_dir.is_dir():
        raise ValueError(f"constants.FOLDER_NAME points to a file: {work_dir}")

    if not work_dir.exists():
        work_dir.mkdir(parents=True)
    return work_dir


def get_video(work_dir: Path):
    if not inputs.YOUTUBE_LINK:
        print("No YouTube link found in inputs.py. Skipping download.")
        return

    output_path = work_dir / constants.SOURCE_VIDEO_NAME
    if output_path.exists():
        print(f"Video already exists at: {output_path}. Skipping download.")
        return

    print(f"Downloading video from: {inputs.YOUTUBE_LINK}")

    download_Command = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        inputs.YOUTUBE_LINK
    ]

    try:
        subprocess.run(download_Command, check=True, cwd=work_dir)
        print("Video downloaded successfully.")
    except FileNotFoundError:
        print("Error: yt-dlp is not installed or not in your PATH.")
        print("Install it with:")
        print("sudo pacman -S yt-dlp ffmpeg")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while downloading the video: {e}")


if __name__ == "__main__":
    main()