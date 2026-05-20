# VideoTo2DRenderer

VideoTo2DRenderer is an experimental pipeline for converting video frames into vector data that can later be rendered in Desmos or another 2D mathematical graphing/rendering environment.

The project currently focuses on the early stages of the pipeline:

```text
MP4 video → extracted grayscale frames → black/white bitmap processing → SVG vector frames
```

The long-term goal is to convert each processed SVG frame into mathematical curve expressions, render those expressions in Desmos using the Desmos API, and eventually create frame-by-frame rendered output.

> This project is still a work in progress. Some parts of the final rendering and animation workflow are not finished yet.

---

## Project Goals

The main goals of this project are:

- Convert video files into frame-by-frame SVG files.
- Process frames into simplified black-and-white vector graphics.
- Preserve curves using SVG path data where possible.
- Convert SVG paths into Desmos-compatible mathematical expressions.
- Render frames one at a time instead of loading all frames into the browser at once.
- Eventually automate screenshot/export workflows for rendered frames.

---

## Current Features

The project currently supports:

- Reading an input `.mp4` video file.
- Extracting frames through `ffmpeg`.
- Optional custom FPS.
- Optional custom output width.
- Automatic use of the source video FPS when `FPS = None`.
- Automatic use of the source video width when `SCALE_WIDTH = None`.
- Grayscale frame processing.
- Edge-based frame processing.
- Threshold-based black-and-white processing.
- Conversion of processed bitmap frames to SVG using `potrace`.
- Skipping reprocessing when the same settings were already used.
- Storing processing metadata in `svg_frames/processing_info.txt`.

---

## Planned Features

Planned or experimental features include:

- Parsing SVG path data into line, quadratic Bézier, and cubic Bézier segments.
- Converting SVG curves into Desmos parametric expressions.
- Generating an HTML page that renders a single SVG frame in Desmos.
- Processing frames one by one from Python instead of storing all frame data in JavaScript.
- Automated browser control for rendering and screenshots.
- Exporting rendered frames back into a video.
- Better curve simplification and point reduction.
- More configurable preprocessing options.

---

## Project Structure

A possible project structure is:

```text
VideoTo2DRenderer/
├── video_to_svg.py              # Converts video frames into SVG files
├── svg_to_desmos_html.py        # Experimental SVG-to-Desmos HTML generator
├── requirements.txt             # Python dependencies
├── README.md                    # Project documentation
├── .gitignore                   # Files ignored by Git
├── svg_frames/                  # Generated SVG frames, ignored by Git
│   ├── frame_00000.svg
│   ├── frame_00001.svg
│   └── processing_info.txt
└── input.mp4                    # Example input video, ignored by Git
```

The exact structure may change as the project grows.

---

## Requirements

This project uses both system dependencies and Python dependencies.

### System Dependencies

The following command-line tools are required:

- `ffmpeg`
- `ffprobe`
- `potrace`

On Arch Linux, Manjaro, or EndeavourOS:

```bash
sudo pacman -S ffmpeg potrace
```

On Debian or Ubuntu-based systems:

```bash
sudo apt update
sudo apt install ffmpeg potrace
```

### Python Dependencies

The current Python dependencies are:

- `numpy`
- `svgpathtools`

These should be installed inside a virtual environment.

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
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Upgrade `pip`:

```bash
python -m pip install --upgrade pip
```

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

Check that the Python packages are installed correctly:

```bash
python -c "import numpy; import svgpathtools; print('Python packages OK')"
```

Check that the system tools are installed correctly:

```bash
ffmpeg -version
potrace --version
```

---

## Creating `requirements.txt`

If dependencies are installed manually during development, regenerate the requirements file with:

```bash
python -m pip freeze > requirements.txt
```

To install from the requirements file later:

```bash
python -m pip install -r requirements.txt
```

---

## Basic Usage

Usage is still experimental because the full pipeline is not finished yet.

At the current stage, the main workflow is:

1. Place an input video in the project folder.
2. Configure the settings in the Python script.
3. Run the video-to-SVG conversion script.
4. Inspect the generated SVG frames.

Example:

```bash
python video_to_svg.py
```

Generated SVG files are written to:

```text
svg_frames/
```

Example output:

```text
svg_frames/frame_00000.svg
svg_frames/frame_00001.svg
svg_frames/frame_00002.svg
...
```

The exact usage will be updated when the Desmos rendering pipeline is complete.

---

## Configuration

The main configuration values are currently edited directly in the Python scripts.

Important settings include:

```python
INPUT_MP4 = "input.mp4"
OUTPUT_DIR = Path("svg_frames")
FPS = None
SCALE_WIDTH = None
MODE = "edges"
THRESHOLD = 140
EDGE_THRESHOLD = 35
TURD_SIZE = 8
OPT_TOLERANCE = 0.8
FRAME_LIMIT = 10
```

### `FPS`

Controls how many frames per second are processed.

```python
FPS = 5
```

If set to `None`, the script uses the original FPS from the input video:

```python
FPS = None
```

### `SCALE_WIDTH`

Controls the output frame width.

```python
SCALE_WIDTH = 240
```

If set to `None`, the script uses the original video width:

```python
SCALE_WIDTH = None
```

### `MODE`

Controls the type of image processing.

Use edge mode for line-art style output:

```python
MODE = "edges"
```

Use threshold mode for black-and-white silhouette output:

```python
MODE = "threshold"
```

### `FRAME_LIMIT`

Controls how many frames are processed.

For testing:

```python
FRAME_LIMIT = 10
```

For more frames:

```python
FRAME_LIMIT = 1000
```

For the whole video:

```python
FRAME_LIMIT = None
```

---

## Processing Cache

The script stores processing metadata in:

```text
svg_frames/processing_info.txt
```

This file records settings such as:

- Input file path
- Input file size
- Input file modification time
- Source resolution
- Output resolution
- Source FPS
- Effective FPS
- Processing mode
- Threshold settings
- Potrace settings
- Frame limit
- Number of processed frames
- Processing status

When the script is run again, it compares the current settings with the saved metadata.

If the settings are the same and all expected SVG files exist, the script skips processing and prints a message such as:

```text
Already processed with the same settings. Skipping.
```

If the settings changed, or the previous run did not finish, the script reprocesses the frames.

---

## Desmos Rendering Plan

The intended rendering workflow is:

```text
SVG frame → parse SVG paths → generate Desmos expressions → render one frame in browser → screenshot → next frame
```

The browser should only receive one frame at a time. This avoids loading a massive JavaScript array containing all frames and all points.

This is important because video-to-vector conversion can produce a very large amount of data.

---

## Why SVG?

SVG is useful in this project because it can store vector paths, including:

- Lines
- Quadratic Bézier curves
- Cubic Bézier curves

These curves can later be translated into Desmos parametric expressions.

For example, a cubic Bézier curve can be represented mathematically as:

```text
B(t) = P0(1 - t)^3 + 3P1t(1 - t)^2 + 3P2t^2(1 - t) + P3t^3
```

where:

```text
0 ≤ t ≤ 1
```

This makes SVG a useful intermediate format between image data and Desmos expressions.

---

## Performance Notes

Video-to-SVG conversion can become very expensive quickly.

To keep processing manageable:

- Start with low FPS.
- Start with a small output width.
- Use a small frame limit while testing.
- Increase quality only after the pipeline works.
- Avoid processing full-resolution video at high FPS at the beginning.

Recommended test settings:

```python
FPS = 5
SCALE_WIDTH = 240
FRAME_LIMIT = 10
```

For Desmos rendering, simpler output is usually better than highly detailed output.

---

## Git Ignore Recommendations

Generated files, videos, and virtual environments should not be committed.

Recommended `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc

svg_frames/
frames/
processed/
test/

*.mp4
*.webm
*.mkv
*.mov

desmos_frame.html
```

---

## Development Status

This project is currently experimental and under active development.

Current stage:

```text
Video → processed SVG frames
```

Next major stage:

```text
SVG frames → Desmos expressions → browser rendering
```

---

## Contributing

This project is currently personal/experimental, but contributions, ideas, and improvements are welcome once the workflow becomes more stable.

Useful areas for improvement include:

- SVG path simplification
- Better frame preprocessing
- Faster frame processing
- Better Desmos expression generation
- Browser automation
- Screenshot/export automation
- Documentation improvements

---

## License

No license has been selected yet.

Before sharing or accepting contributions publicly, add a license file such as:

- MIT License
- Apache License 2.0
- GPLv3

Until a license is added, all rights are reserved by default.

---

## Notes

This project depends on external tools such as `ffmpeg`, `potrace`, and the Desmos API.

When using videos as input, make sure you have the right to process and transform the content.

