# VideoTo2DRenderer

VideoTo2DRenderer is an experimental Python pipeline that turns a video into a Desmos-rendered animation.

The basic idea is:

```text
YouTube/video file
→ source.mp4
→ SVG frame sequence
→ Desmos expressions
→ browser screenshots
→ final rendered video
```

The project is built around rendering one frame at a time. This avoids sending the whole video into Desmos at once, which would be far too large for the browser and the Desmos calculator.

---

## Features

- Download a video with `yt-dlp`.
- Convert video frames to SVG frames.
- Use edge-based vectorization with adaptive segment reduction.
- Convert SVG paths to Desmos expressions.
- Render Desmos frames in a browser through Playwright.
- Render multiple frames in parallel with multiple Chromium workers.
- Save rendered PNG frames.
- Assemble rendered frames into an output video.
- Optionally add the original audio back into the final video.
- Optionally overlay the original video while assembling.
- Skip already-completed steps when the same settings were used.
- Rerender only selected bad/empty screenshots instead of rerendering everything.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/VideoTo2DRenderer.git
cd VideoTo2DRenderer
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install Python requirements:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install Playwright Chromium:

```bash
python -m playwright install chromium
```

---

## System Requirements

The project also needs some command-line tools.

### Arch Linux / Manjaro / EndeavourOS

```bash
sudo pacman -S ffmpeg yt-dlp potrace
```

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install ffmpeg yt-dlp potrace
```

### Why these are needed

- `ffmpeg` and `ffprobe` are used for reading videos, extracting frames, and assembling the final video.
- `yt-dlp` is used for downloading videos.
- `potrace` is only needed if you use threshold/silhouette mode.
- Playwright Chromium is used for automated Desmos rendering and screenshots.

Check that the tools are available:

```bash
ffmpeg -version
ffprobe -version
yt-dlp --version
potrace --version
```

Check Python packages:

```bash
python -c "import numpy; import cv2; import svgpathtools; import playwright; print('Python packages OK')"
```

---

## Basic Usage

Open `constants.py` and set the video link:

```python
YOUTUBE_LINK = "https://www.youtube.com/watch?v=..."
```

Then run the full pipeline:

```bash
python main.py
```

The default pipeline is:

```text
main.py
→ getVideo.py
→ video_to_svg.py
→ svg_to_desmos_img.py
→ desmos_img_to_video.py
```

Wait for the pipeline to finish, then check your video project folder. The final output is saved as:

```text
<FOLDER_VIDEO>/desmos_render.mp4
```

For example:

```text
Bad_Apple/desmos_render.mp4
```

---

## Rerender Selected Empty Screenshots

Sometimes a few browser screenshots may be empty or incorrect. You do not need to rerender the whole video.

To rerender selected frames:

```bash
python svg_to_desmos_img.py 0 1 7 23 41
```

You can also use ranges:

```bash
python svg_to_desmos_img.py 0-59
```

Or mix ranges and single frames:

```bash
python svg_to_desmos_img.py 0-59 80 100-120
```

Or use a quoted list:

```bash
python svg_to_desmos_img.py "[0, 1, 7, 23, 41]"
```

This overwrites only the selected files:

```text
rendered_frames/frame_00000.png
rendered_frames/frame_00001.png
rendered_frames/frame_00007.png
...
```

The selected-frame rerender uses the previous render configuration and saved Desmos viewport state.

---

## Preview One SVG Frame in Desmos

If you want to inspect how one SVG frame looks in Desmos, use `svg_to_desmos_json.py`.

First choose a frame in `constants.py`:

```python
PREVIEW_FRAME_NUMBER = 250
```

Then run:

```bash
python svg_to_desmos_json.py
```

This writes:

```text
desmos/current_frame.json
```

Now start a local server from the project root:

```bash
python -m http.server 8765
```

Open this in your browser:

```text
http://127.0.0.1:8765/desmos/desmos_viewer.html
```

The page loads `desmos/current_frame.json` and shows the selected frame in Desmos.

This preview mode is useful for testing SVG quality, Desmos expression settings, scaling, and viewport placement.

---

## Important Configuration Values

Most settings are in `constants.py`. The file has comments for more detail. These are the most important ones.

### Project and video settings

```python
FOLDER_VIDEO = "Bad_Apple"
SOURCE_VIDEO_NAME = "source.mp4"
YOUTUBE_LINK = "https://www.youtube.com/watch?v=..."
```

Each video gets its own folder. Generated SVGs, screenshots, metadata, and the final video are stored there.

---

### Frame extraction settings

```python
FPS = None
SCALE_WIDTH = None
FRAME_LIMIT = None
```

- `FPS = None` uses the original video FPS.
- `SCALE_WIDTH = None` uses the original video width.
- `FRAME_LIMIT = None` processes the whole video.

Good test settings:

```python
FPS = 5
SCALE_WIDTH = 240
FRAME_LIMIT = 50
```

Higher FPS and larger width increase quality but make everything slower.

---

### SVG processing mode

```python
VIDEO_PROCESSING_MODE = "edges"
```

Recommended:

```python
VIDEO_PROCESSING_MODE = "edges"
```

This uses Canny edge detection and writes SVG stroke paths directly.

Threshold mode is also available:

```python
VIDEO_PROCESSING_MODE = "threshold"
```

Threshold mode uses black/white bitmap processing and `potrace`.

---

### Edge detection and simplification

```python
CANNY_BLUR_SIZE = 3
CANNY_LOW_THRESHOLD = 60
CANNY_HIGH_THRESHOLD = 120

EDGE_MIN_CONTOUR_POINTS = 2
EDGE_SIMPLIFY_EPSILON = 1.5
```

These control how detailed the SVG frame is.

Lower thresholds usually produce more edges. Higher thresholds usually produce fewer edges.

Larger `EDGE_SIMPLIFY_EPSILON` means fewer segments and lower quality. Smaller values mean more detail and more Desmos expressions.

---

### Segment budget

```python
MAX_SEGMENTS = 3000
```

This is one of the most important performance settings.

Desmos becomes slow or unstable with too many expressions. Instead of cutting off expressions later, `video_to_svg.py` adaptively compresses each SVG frame so it fits under `MAX_SEGMENTS`.

This is better than plotting only the first `MAX_SEGMENTS`, because the whole frame is simplified instead of losing large parts of the image.

---

### Desmos coordinate settings

```python
DESMOS_TARGET_WIDTH = 200
FRAME_ANCHOR = "left_bottom"
ANCHOR_POINT = (0, 0)
FLIP_Y = False
```

These control where the SVG appears in Desmos coordinates.

Example:

```python
FRAME_ANCHOR = "left_bottom"
ANCHOR_POINT = (0, 0)
```

means the bottom-left corner of the frame is placed at `(0, 0)`.

---

### Desmos display settings

```python
SHOW_GRID = False
SHOW_AXES = True
SHOW_EXPRESSIONS = True
SHOW_FRAME = True
```

For cleaner screenshots:

```python
SHOW_GRID = False
SHOW_AXES = False
SHOW_EXPRESSIONS = False
```

For debugging:

```python
SHOW_EXPRESSIONS = True
```

---

### Browser screenshot settings

```python
SCREENSHOT_WIDTH = 1920
SCREENSHOT_HEIGHT = 1080
HEADLESS = False
WAIT_BEFORE_DESMOS_IMG_RENDER = True
```

- `SCREENSHOT_WIDTH` and `SCREENSHOT_HEIGHT` control the output PNG size.
- `WAIT_BEFORE_DESMOS_IMG_RENDER = True` opens the first frame and waits, so you can adjust the Desmos viewpoint before rendering.
- Press the configured start key when ready.

---

### Parallel rendering

```python
DESMOS_RENDER_WORKERS = 4
```

This controls how many browser workers render frames in parallel.

Start with:

```python
DESMOS_RENDER_WORKERS = 2
```

Then test:

```python
DESMOS_RENDER_WORKERS = 4
```

Increase only if your CPU/GPU/RAM temperatures and usage are still manageable.

---

### GPU / Chromium settings

```python
USE_NVIDIA_PRIME = False
```

For most users, leave this as `False`.

If someone uses a hybrid NVIDIA laptop and wants to try PRIME offload, they can set:

```python
USE_NVIDIA_PRIME = True
```

For a dGPU-only desktop/session, keep it `False`. Chromium should use the active GPU automatically.

---

### Final video assembly

```python
OUTPUT_FPS = FPS
ADD_AUDIO = True
SHOW_ORIGINAL_VIDEO = True
```

- `OUTPUT_FPS = FPS` usually keeps the output speed consistent with the extracted SVG frames.
- `ADD_AUDIO = True` copies audio from the source video into the final video.
- `SHOW_ORIGINAL_VIDEO = True` overlays the original video during assembly.

---

## Project Structure

Typical structure:

```text
VideoTo2DRenderer/
├── constants.py
├── inputs.py
├── getVideo.py
├── video_to_svg.py
├── svg_to_desmos_json.py
├── svg_to_desmos_img.py
├── desmos_img_to_video.py
├── main.py
├── requirements.txt
├── README.md
├── desmos/
│   ├── desmos_viewer.html
│   └── current_frame.json
└── <FOLDER_VIDEO>/
    ├── source.mp4
    ├── output_svg/
    ├── rendered_frames/
    ├── desmos_render.mp4
    ├── download_info.txt
    ├── processing_info.txt
    ├── desmos_img_info.txt
    ├── video_info.txt
    └── desmos_storage_state.json
```

Generated video folders should usually be ignored by Git.

---

## Pipeline Explanation

### 1. `getVideo.py`

Downloads the source video using `yt-dlp`.

It saves the video as:

```text
<FOLDER_VIDEO>/source.mp4
```

It does not download again if the source video already exists with matching metadata.

---

### 2. `video_to_svg.py`

Converts the video into SVG frame files.

Output:

```text
<FOLDER_VIDEO>/output_svg/frame_00000.svg
<FOLDER_VIDEO>/output_svg/frame_00001.svg
...
```

For edge mode, the algorithm is roughly:

```text
video frame
→ grayscale frame
→ Canny edge detection
→ contour extraction
→ contour simplification
→ adaptive segment-budget compression
→ SVG stroke paths
```

The adaptive compression step tries to keep every generated SVG under `MAX_SEGMENTS`.

This prevents Desmos from receiving too many expressions per frame.

The script writes metadata to:

```text
<FOLDER_VIDEO>/processing_info.txt
```

If the same video and settings were already processed, it skips the work. If settings changed, it clears old SVG frames and regenerates them.

---

### 3. `svg_to_desmos_json.py`

Converts one SVG frame into Desmos-compatible frame data.

It parses SVG paths into:

- lines
- quadratic Bézier curves
- cubic Bézier curves

Then it creates Desmos parametric expressions.

This script is mainly used for preview/debugging. It writes:

```text
desmos/current_frame.json
```

The Desmos viewer can load this file manually in the browser.

---

### 4. `desmos/desmos_viewer.html`

This is the browser page that embeds the Desmos calculator.

It supports two modes:

1. Manual preview mode:
   ```text
   loadFrame()
   → fetch desmos/current_frame.json
   ```

2. Python render mode:
   ```text
   loadFrameData(frame_data)
   → receive frame data directly from Playwright
   ```

The second mode is important for parallel rendering, because multiple workers must not overwrite the same JSON file.

---

### 5. `svg_to_desmos_img.py`

Renders SVG frames into PNG screenshots using Playwright and Chromium.

Output:

```text
<FOLDER_VIDEO>/rendered_frames/frame_00000.png
<FOLDER_VIDEO>/rendered_frames/frame_00001.png
...
```

This step can run multiple browser workers in parallel.

It does not use `current_frame.json` during production rendering. Instead, Python sends each frame directly into the browser with:

```text
window.loadFrameData(frame_data)
```

This avoids race conditions between parallel workers.

The script writes metadata to:

```text
<FOLDER_VIDEO>/desmos_img_info.txt
```

If the same SVG/render settings were already rendered and all PNG files exist, it skips rendering. If settings changed, it clears old screenshots and renders again.

---

### 6. `desmos_img_to_video.py`

Assembles the rendered PNG screenshots into the final video.

Output:

```text
<FOLDER_VIDEO>/desmos_render.mp4
```

It can optionally:

- add audio from `source.mp4`
- overlay the original video
- wait before assembly so you can adjust overlay placement

It writes metadata to:

```text
<FOLDER_VIDEO>/video_info.txt
```

If the final video already exists with matching settings, it skips assembly.

---

## Caching and Safety

Each major step stores metadata about the settings used.

The goal is:

```text
same input + same settings + expected files exist
→ skip the step

changed settings or missing files
→ clear that step's old outputs
→ regenerate
```

This avoids unnecessary work while also preventing mixed outputs from different settings.

Important metadata files:

```text
download_info.txt
processing_info.txt
desmos_img_info.txt
video_info.txt
desmos_storage_state.json
```

---

## Performance Tips

Start small:

```python
FPS = 5
SCALE_WIDTH = 240
FRAME_LIMIT = 50
MAX_SEGMENTS = 1000
DESMOS_RENDER_WORKERS = 2
```

Then increase quality gradually.

Important performance controls:

```python
FPS
SCALE_WIDTH
FRAME_LIMIT
MAX_SEGMENTS
EDGE_SIMPLIFY_EPSILON
DESMOS_RENDER_WORKERS
SCREENSHOT_WIDTH
SCREENSHOT_HEIGHT
SHOW_EXPRESSIONS
```

For faster rendering:

```python
SHOW_EXPRESSIONS = False
SHOW_GRID = False
SHOW_AXES = False
```

For less Desmos load:

```python
MAX_SEGMENTS = 1000
```

For better quality but slower rendering:

```python
MAX_SEGMENTS = 3000
SCALE_WIDTH = 480
```

Watch CPU/GPU temperatures during long renders.

---

## Troubleshooting

### `ModuleNotFoundError` even though the package is installed

Make sure you are running the Python from your virtual environment:

```bash
which python
python -c "import svgpathtools; print('OK')"
```

Do not run scripts with `/usr/bin/python` if your packages are installed in `.venv`.

---

### Playwright browser is missing

Run:

```bash
python -m playwright install chromium
```

---

### Desmos screenshots are empty

Try rerendering the bad frames:

```bash
python svg_to_desmos_img.py 0 1 7 23
```

If many early frames are empty, adjust the screenshot paint-settling settings in `constants.py`.

---

### Rendering is too slow

Reduce one or more of:

```python
FPS
SCALE_WIDTH
MAX_SEGMENTS
SCREENSHOT_WIDTH
SCREENSHOT_HEIGHT
```

Also try increasing or decreasing:

```python
DESMOS_RENDER_WORKERS
```

The best value depends on your CPU, GPU, RAM, and cooling.

---

### Laptop goes to sleep during rendering

On systemd Linux systems, run the pipeline with:

```bash
systemd-inhibit \
  --what=sleep:idle:handle-lid-switch \
  --mode=block \
  --why="VideoTo2DRenderer render running" \
  python main.py
```

---

## Development Notes

This project is experimental. Desmos was not designed as a video renderer, so performance depends heavily on keeping the expression count reasonable.

The most important design rule is:

```text
Simplify before Desmos.
```

It is better to generate a lower-quality whole-frame SVG than to send too many expressions or cut off large parts of the frame.

---

## Disclaimer

Only process videos that you have the right to download, transform, and render.

This project uses external tools and APIs such as `ffmpeg`, `yt-dlp`, `potrace`, Playwright, Chromium, and the Desmos API.
