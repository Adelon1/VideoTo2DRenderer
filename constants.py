"""
This file contains constants used in the VideoTo2DRenderer project.
"""

FOLDER_NAME = "Bad_Apple"
FOLDER_SVG = FOLDER_NAME + "/output_svg"
SOURCE_VIDEO_NAME = "source.mp4"

FPS = None
SCALE_WIDTH = None

FRAME_LIMIT = None

# If None, use the real SVG frame width.
# If a number, scale the frame to that Desmos width.
DESMOS_TARGET_WIDTH = 200

# Where should the frame be placed?
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
# Desmos y goes upward.
# Keep this True for normal Desmos coordinates.
FLIP_Y = False
ROUND_DIGITS = 4
MAX_SEGMENTS = None
LINE_WIDTH = 1
LINE_COLOR = "#000000"

SHOW_FRAME = True
FRAME_COLOR = "#444444"
FRAME_LINE_WIDTH = 1.5

SHOW_GRID = False
SHOW_AXES = True
SHOW_EXPRESSIONS = True

# Adds first expression:
# f = current_frame_number
SHOW_FRAME_NUMBER_EXPRESSION = True
FRAME_NUMBER_VARIABLE = "f"