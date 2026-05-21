# ============================================================
# Chromium / GPU settings
# ============================================================

# Always use Playwright Chromium.
#
# If your whole desktop/session is already running on NVIDIA/dGPU-only,
# keep this False. Chromium should use NVIDIA automatically.
#
# If someone else uses hybrid graphics and wants PRIME offload, they can
# set this to True.
USE_NVIDIA_PRIME = False

# Used only when USE_NVIDIA_PRIME = True.
NVIDIA_PRIME_ENV = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "__VK_LAYER_NV_optimus": "NVIDIA_only",
}

# Print WebGL GPU info once per worker.
PRINT_BROWSER_GPU_INFO = True



# ============================================================
# Project structure and constants
# ============================================================

"""
Project-wide constants for VideoTo2DRenderer.

Expected project structure:

VideoTo2DRenderer/
├── constants.py
├── inputs.py
├── getVideo.py
├── video_to_svg.py
├── svg_to_desmos_json.py
├── svg_to_desmos_img.py
├── desmos_img_to_video.py
├── main.py
├── <FOLDER_VIDEO>/
│   ├── <SOURCE_VIDEO_NAME>
│   ├── <FOLDER_SVG_NAME>/
│   ├── <FOLDER_RENDERED_FRAMES_NAME>/
│   ├── <FILE_OUTPUT_VIDEO>
│   ├── download_info.txt
│   ├── processing_info.txt
│   ├── desmos_img_info.txt
│   └── video_info.txt
└── <FOLDER_DESMOS>/
    ├── <FILE_DESMOS_VIEWER>
    └── <FILE_CURRENT_FRAME>
"""

from pathlib import Path


# ============================================================
# Project paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent


# ============================================================
# Video project folder
# ============================================================

# The link to the YouTube video to be processed.
# If this is empty, the script will not download a new video.
# Example link to Bad Apple:
YOUTUBE_LINK = "https://www.youtube.com/watch?v=AnEGaKtbs2E&list=RDAnEGaKtbs2E&start_radio=1"

# Each video gets its own folder.
#
# Example:
#
# Bad_Apple/
# ├── source.mp4
# ├── output_svg/
# ├── rendered_frames/
# └── desmos_render.mp4
FOLDER_VIDEO = "Everyone"

SOURCE_VIDEO_NAME = "source.mp4"

FOLDER_SVG_NAME = "output_svg"
FOLDER_RENDERED_FRAMES_NAME = "rendered_frames"

FILE_OUTPUT_VIDEO = "desmos_render.mp4"


# ============================================================
# Desmos folder
# ============================================================

# The Desmos folder is a sibling of the video folder.
#
# Example:
#
# desmos/
# ├── desmos_viewer.html
# └── current_frame.json
FOLDER_DESMOS = "desmos"

FILE_DESMOS_VIEWER = "desmos_viewer.html"
FILE_CURRENT_FRAME = "current_frame.json"


# ============================================================
# Derived paths
# ============================================================

PATH_VIDEO_FOLDER = PROJECT_ROOT / FOLDER_VIDEO
PATH_SOURCE_VIDEO = PATH_VIDEO_FOLDER / SOURCE_VIDEO_NAME

PATH_SVG_FOLDER = PATH_VIDEO_FOLDER / FOLDER_SVG_NAME
PATH_RENDERED_FRAMES_FOLDER = PATH_VIDEO_FOLDER / FOLDER_RENDERED_FRAMES_NAME
PATH_OUTPUT_VIDEO = PATH_VIDEO_FOLDER / FILE_OUTPUT_VIDEO

PATH_DESMOS_FOLDER = PROJECT_ROOT / FOLDER_DESMOS
PATH_DESMOS_VIEWER = PATH_DESMOS_FOLDER / FILE_DESMOS_VIEWER
PATH_CURRENT_FRAME_JSON = PATH_DESMOS_FOLDER / FILE_CURRENT_FRAME


# ============================================================
# Video download settings
# ============================================================

# Metadata file used to remember how source.mp4 was downloaded.
FILE_DOWNLOAD_INFO = "download_info.txt"
PATH_DOWNLOAD_INFO = PATH_VIDEO_FOLDER / FILE_DOWNLOAD_INFO

# yt-dlp format selection.
# This tries to download MP4 video + M4A audio when possible.
YTDLP_FORMAT = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"

# Output container for yt-dlp merging.
YTDLP_MERGE_OUTPUT_FORMAT = "mp4"

# Increase this if getVideo.py changes in a way that should invalidate
# old downloads.
DOWNLOAD_CACHE_VERSION = 1


# ============================================================
# Video-to-SVG extraction settings
# ============================================================

# If FPS = None, use the original video FPS.
FPS = 15

# If SCALE_WIDTH = None, use the original video width.
SCALE_WIDTH = 500

# If FRAME_LIMIT = None, process all frames.
FRAME_LIMIT = None


# ============================================================
# Video-to-SVG processing settings
# ============================================================

# Use "edges" for centerline edge SVGs.
# Use "threshold" for black/white silhouette SVGs using Potrace.
VIDEO_PROCESSING_MODE = "edges"

# Used only when VIDEO_PROCESSING_MODE = "threshold".
THRESHOLD = 140

# Potrace settings.
# Used only when VIDEO_PROCESSING_MODE = "threshold".
TURD_SIZE = 8
OPT_TOLERANCE = 0.8

# Important:
# 1 avoids Potrace output being scaled 10x.
POTRACE_UNIT = 1


# ============================================================
# Edge-vectorization settings
# ============================================================

# Used only when VIDEO_PROCESSING_MODE = "edges".
#
# This mode does NOT use Potrace.
# It uses OpenCV Canny edge detection and writes SVG stroke paths directly.
CANNY_BLUR_SIZE = 3
CANNY_LOW_THRESHOLD = 60
CANNY_HIGH_THRESHOLD = 120

# Remove tiny contour fragments.
EDGE_MIN_CONTOUR_POINTS = 2

# Simplify contours before writing SVG.
# Larger value = fewer points, less detail.
# Smaller value = more detail.
EDGE_SIMPLIFY_EPSILON = 1.5

# SVG stroke style for edge mode.
EDGE_STROKE_WIDTH = 1
EDGE_STROKE_COLOR = "#000000"


# ============================================================
# Edge adaptive compression settings
# ============================================================

# If MAX_SEGMENTS is not None, video_to_svg.py compresses each edge SVG
# until it fits under MAX_SEGMENTS.
#
# This is better than cutting off Desmos expressions later because the whole
# frame gets lower quality instead of missing large regions.
EDGE_ADAPTIVE_SIMPLIFY = True

# Maximum simplification attempts per frame.
EDGE_ADAPTIVE_MAX_ITERATIONS = 12

# Applied to EDGE_SIMPLIFY_EPSILON after each failed attempt.
EDGE_ADAPTIVE_EPSILON_MULTIPLIER = 1.35

# Applied to EDGE_MIN_CONTOUR_POINTS after each failed attempt.
EDGE_ADAPTIVE_MIN_POINTS_MULTIPLIER = 1.15

# If still over budget after simplification, remove the least important
# small contours until the frame fits.
EDGE_DROP_SMALLEST_CONTOURS_IF_NEEDED = True


# ============================================================
# Video-to-SVG cache / metadata
# ============================================================

# Metadata file used to remember how SVG frames were generated.
FILE_PROCESSING_INFO = "processing_info.txt"
PATH_PROCESSING_INFO = PATH_VIDEO_FOLDER / FILE_PROCESSING_INFO

# Increase this if video_to_svg.py changes in a way that should invalidate
# old SVG frames.
VIDEO_TO_SVG_CACHE_VERSION = 1


# ============================================================
# SVG-to-Desmos coordinate settings
# ============================================================

# If None, use the real SVG frame width.
# If a number, scale the frame to that Desmos width.
DESMOS_TARGET_WIDTH = 200

# Where should the frame be placed?
#
# Options:
# "center"
# "left_bottom"
# "left_top"
# "right_bottom"
# "right_top"
FRAME_ANCHOR = "left_bottom"

# The Desmos coordinate where the chosen anchor should be placed.
ANCHOR_POINT = (0, 0)

# SVG y goes downward.
# Desmos y usually goes upward.
#
# True:
#   SVG top becomes Desmos top.
#
# False:
#   SVG y direction is kept.
FLIP_Y = True

# Decimal rounding for generated Desmos expressions.
ROUND_DIGITS = 4


# ============================================================
# SVG-to-Desmos expression settings
# ============================================================

# Maximum amount of SVG segments allowed in a generated SVG frame.
#
# Important:
# This is now handled during video_to_svg.py generation/compression.
# svg_to_desmos_json.py does NOT cut off expressions anymore.
#
# If None, do not compress by segment budget.
MAX_SEGMENTS = 1500

# Desmos line style for SVG paths.
LINE_WIDTH = 1
LINE_COLOR = "#000000"

# Always draw a rectangular border around the frame.
SHOW_FRAME = True

FRAME_COLOR = "#444444"
FRAME_LINE_WIDTH = 1.5

# Adds first expression:
# f = current_frame_number
SHOW_FRAME_NUMBER_EXPRESSION = True
FRAME_NUMBER_VARIABLE = "f"


# ============================================================
# SVG-to-Desmos JSON settings
# ============================================================

# Used only when running svg_to_desmos_json.py directly.
# The full renderer passes SVG paths manually.
PREVIEW_FRAME_NUMBER = 0

# Increase this if svg_to_desmos_json.py changes in a way that should
# invalidate old current_frame.json files.
SVG_TO_DESMOS_CACHE_VERSION = 1


# ============================================================
# Desmos display settings
# ============================================================

# These are written into current_frame.json by Python.
# The HTML viewer reads them from JSON.
SHOW_GRID = False
SHOW_AXES = True
SHOW_EXPRESSIONS = True


# ============================================================
# Desmos render-ready screenshot settings
# ============================================================

# Desmos asyncScreenshot() is used as a render-ready signal.
# The returned Desmos image is ignored.
# The final saved image is taken by Playwright from the whole browser viewport.
DESMOS_SCREENSHOT_FORMAT = "png"

# "stretch" uses the chosen mathBounds exactly.
# Other Desmos modes include:
# "contain", "preserveX", and "preserveY".
DESMOS_SCREENSHOT_MODE = "stretch"

# Usually keep this at 1.
DESMOS_SCREENSHOT_TARGET_PIXEL_RATIO = 1

# False means do not render movable point halos.
DESMOS_SCREENSHOT_SHOW_MOVABLE_POINTS = False

# False means do not include point labels.
DESMOS_SCREENSHOT_SHOW_LABELS = False


# ============================================================
# Desmos viewport storage
# ============================================================

# Stores the browser localStorage after you set/save the Desmos viewpoint.
# Used when rerendering only selected bad frames later.
FILE_DESMOS_STORAGE_STATE = "desmos_storage_state.json"
PATH_DESMOS_STORAGE_STATE = PATH_VIDEO_FOLDER / FILE_DESMOS_STORAGE_STATE


# ============================================================
# Browser / screenshot size
# ============================================================

# Browser viewport size used by Playwright.
# This is the size of the final saved PNG frames.
SCREENSHOT_WIDTH = 1920
SCREENSHOT_HEIGHT = 1080

# Hide HTML buttons/toolbars while rendering.
SCREENSHOT_MODE = True

# False = visible browser.
# True = hidden browser after manual setup.
HEADLESS = True

# If True, the first frame opens in the browser and waits before rendering.
# Use this to set and save the default Desmos viewpoint.
WAIT_BEFORE_DESMOS_IMG_RENDER = True
DESMOS_IMG_START_KEY = "s"


# ============================================================
# Screenshot paint settling
# ============================================================

# After Desmos asyncScreenshot() returns, the visible Chromium viewport may
# still be one paint behind.
#
# If True, the browser measures its own requestAnimationFrame interval and
# waits at least one rounded-up frame duration before Playwright screenshots.
AUTO_SCREENSHOT_SETTLE_FROM_REFRESH_RATE = True

# Used only if refresh-rate measurement fails.
FALLBACK_REFRESH_RATE = 60

# Add extra safety frames.
# 0 = wait roughly one frame.
# 1 = wait roughly two frames.
SCREENSHOT_EXTRA_SETTLE_FRAMES = 0


# ============================================================
# SVG-to-Desmos-image render settings
# ============================================================

# First SVG frame index to render.
START_INDEX = 0

# If RENDER_FRAME_LIMIT = None, render all SVG frames.
RENDER_FRAME_LIMIT = None

# Number of parallel browser workers used for rendering Desmos images.
#
# 1 = old sequential behavior.
# 2-4 = good starting range.
# Higher values may be faster or may overload RAM/Chromium/GPU.
DESMOS_RENDER_WORKERS = 6


# ============================================================
# SVG-to-Desmos-image cache / metadata
# ============================================================

# Metadata file used to remember how rendered PNG frames were generated.
FILE_DESMOS_IMG_INFO = "desmos_img_info.txt"
PATH_DESMOS_IMG_INFO = PATH_VIDEO_FOLDER / FILE_DESMOS_IMG_INFO

# Increase this if svg_to_desmos_img.py changes in a way that should
# invalidate old rendered PNG frames.
DESMOS_IMG_CACHE_VERSION = 1


# ============================================================
# Image-to-video assembly settings
# ============================================================

# If OUTPUT_FPS = None, use the FPS from the original source video.
#
# Important:
# If SVGs were generated at 5 FPS but the source video is 30 FPS,
# then OUTPUT_FPS = None will make the final video play too fast.
# In that case, set OUTPUT_FPS = FPS.
OUTPUT_FPS = FPS

# If True, add audio from source.mp4 to the final output video.
ADD_AUDIO = True

# If True, overlay the original video image on top of the Desmos-rendered image.
SHOW_ORIGINAL_VIDEO = True

# Overlay original video on top of the Desmos image.
# These values are in output-video pixels.
ORIGINAL_VIDEO_OVERLAY_X = 20
ORIGINAL_VIDEO_OVERLAY_Y = 20
ORIGINAL_VIDEO_OVERLAY_SCALE = 0.25

# If True, open an overlay preview and wait before assembling the video.
# This is useful when SHOW_ORIGINAL_VIDEO = True and you want to move/scale
# the original video overlay manually.
WAIT_BEFORE_VIDEO_ASSEMBLY = True

# Overlay preview controls.
OVERLAY_MOVE_STEP = 10
OVERLAY_SCALE_STEP = 0.05


# ============================================================
# Image-to-video cache / metadata
# ============================================================

# Metadata file used to remember how the final video was assembled.
FILE_VIDEO_INFO = "video_info.txt"
PATH_VIDEO_INFO = PATH_VIDEO_FOLDER / FILE_VIDEO_INFO

# Temporary preview image used when positioning the original-video overlay.
FILE_OVERLAY_PREVIEW_IMAGE = "overlay_preview.png"
PATH_OVERLAY_PREVIEW_IMAGE = PATH_VIDEO_FOLDER / FILE_OVERLAY_PREVIEW_IMAGE

# Temporary preview HTML used when positioning the original-video overlay.
FILE_OVERLAY_PREVIEW_HTML = "overlay_preview.html"
PATH_OVERLAY_PREVIEW_HTML = PATH_VIDEO_FOLDER / FILE_OVERLAY_PREVIEW_HTML

# Increase this if desmos_img_to_video.py changes in a way that should
# invalidate old final videos.
VIDEO_ASSEMBLY_CACHE_VERSION = 1


# ============================================================
# Local server settings
# ============================================================

# Local server port used for the Desmos HTML viewer.
PORT = 8765

# How long Python waits for browser functions.
RENDER_TIMEOUT_MS = 120_000