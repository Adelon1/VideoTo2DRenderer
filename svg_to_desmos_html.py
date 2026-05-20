from pathlib import Path
import json
import re
import constants

from svgpathtools import (
    svg2paths2,
    Line,
    CubicBezier,
    QuadraticBezier,
)


INPUT_SVG = Path(constants.FOLDER_SVG) / "frame_00067.svg"
OUTPUT_JSON = Path("desmos/current_frame.json")


DESMOS_TARGET_WIDTH = constants.DESMOS_TARGET_WIDTH
FRAME_ANCHOR = constants.FRAME_ANCHOR
ANCHOR_POINT = constants.ANCHOR_POINT


FLIP_Y = constants.FLIP_Y

ROUND_DIGITS = constants.ROUND_DIGITS
MAX_SEGMENTS = constants.MAX_SEGMENTS
LINE_WIDTH = constants.LINE_WIDTH
LINE_COLOR = constants.LINE_COLOR

SHOW_FRAME = constants.SHOW_FRAME
FRAME_COLOR = constants.FRAME_COLOR
FRAME_LINE_WIDTH = constants.FRAME_LINE_WIDTH

SHOW_GRID = constants.SHOW_GRID
SHOW_AXES = constants.SHOW_AXES
SHOW_EXPRESSIONS = constants.SHOW_EXPRESSIONS

SHOW_FRAME_NUMBER_EXPRESSION = constants.SHOW_FRAME_NUMBER_EXPRESSION
FRAME_NUMBER_VARIABLE = constants.FRAME_NUMBER_VARIABLE


def main():
    frame_data = svg_to_frame_data(INPUT_SVG)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(frame_data, indent=2), encoding="utf-8")

    print(f"Wrote {OUTPUT_JSON}")
    print(f"Expressions: {len(frame_data['expressions'])}")
    print(f"Frame size in Desmos: {frame_data['frame']['width']} x {frame_data['frame']['height']}")
    print(f"Viewport: {frame_data['viewport']}")


def svg_to_frame_data(svg_path: Path):
    paths, path_attributes, svg_attributes = svg2paths2(str(svg_path))

    segments = collect_segments(paths)

    # Important:
    # Even if there are no segments, we still try to get the frame from
    # viewBox / width / height, so we can show the rectangular frame.
    svg_frame = get_svg_frame(svg_attributes, segments)

    scale = get_scale(svg_frame)

    mapper, viewport, desmos_frame = make_frame_mapper_and_viewport(
        svg_frame=svg_frame,
        scale=scale,
    )

    if MAX_SEGMENTS is not None:
        segments = segments[:MAX_SEGMENTS]

    expressions = []

    frame_number = get_frame_number(svg_path)
    if SHOW_FRAME_NUMBER_EXPRESSION:
        expressions.append({
            "id": "current_frame",
            "latex": f"{FRAME_NUMBER_VARIABLE}={frame_number}",
            "color": "#000000",
            "hidden": True
        })

    # Always add the frame first, if enabled.
    if SHOW_FRAME:
        expressions.extend(make_frame_expressions(desmos_frame))

    # Then add the real SVG segments, if any.
    for i, (kind, segment) in enumerate(segments):
        if kind == "line":
            latex = line_to_latex(segment, mapper)
        elif kind == "quadratic":
            latex = quadratic_to_latex(segment, mapper)
        elif kind == "cubic":
            latex = cubic_to_latex(segment, mapper)
        else:
            continue

        expressions.append({
            "id": f"seg_{i}",
            "latex": latex,
            "color": LINE_COLOR,
            "lineWidth": LINE_WIDTH,
        })

    return {
        "source_svg": str(svg_path),
        "frame_number": frame_number,
        "segment_count": len(segments),
        "frame": desmos_frame,
        "viewport": viewport,
        "settings": {
            "show_grid": SHOW_GRID,
            "show_axes": SHOW_AXES,
            "show_expressions": SHOW_EXPRESSIONS
        },
        "expressions": expressions,
    }

def make_frame_expressions(desmos_frame):
    left = desmos_frame["left"]
    right = desmos_frame["right"]
    bottom = desmos_frame["bottom"]
    top = desmos_frame["top"]

    corners = [
        (left, bottom),   # A1, B1
        (right, bottom),  # A2, B2
        (right, top),     # A3, B3
        (left, top),      # A4, B4
    ]

    expressions = []

    for i in range(4):
        x0, y0 = corners[i]
        x1, y1 = corners[(i + 1) % 4]

        latex = segment_points_to_latex(x0, y0, x1, y1)

        expressions.append({
            "id": f"frame_{i}",
            "latex": latex,
            "color": FRAME_COLOR,
            "lineWidth": FRAME_LINE_WIDTH,
        })

    return expressions


def collect_segments(paths):
    segments = []

    for path in paths:
        for segment in path:
            if isinstance(segment, Line):
                segments.append(("line", segment))
            elif isinstance(segment, QuadraticBezier):
                segments.append(("quadratic", segment))
            elif isinstance(segment, CubicBezier):
                segments.append(("cubic", segment))

    return segments


def get_svg_frame(svg_attributes, segments):
    """
    Returns the real SVG frame:
    x, y, width, height

    Preferred order:
    1. viewBox
    2. width/height
    3. path bounds
    4. final fallback dummy frame
    """
    view_box = svg_attributes.get("viewBox")

    if view_box:
        nums = parse_numbers(view_box)

        if len(nums) == 4:
            x, y, width, height = nums

            return {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }

    width = parse_svg_length(svg_attributes.get("width"))
    height = parse_svg_length(svg_attributes.get("height"))

    if width is not None and height is not None:
        return {
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
        }

    if segments:
        print("Warning: Could not find SVG viewBox/width/height.")
        print("Falling back to path bounds.")
        return get_path_bounds_as_frame(segments)

    print("Warning: No SVG size metadata and no path segments found.")
    print("Using default fallback frame 1x1.")

    return {
        "x": 0,
        "y": 0,
        "width": 1,
        "height": 1,
    }


def parse_numbers(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def parse_svg_length(value):
    if value is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    return float(match.group(0))


def get_path_bounds_as_frame(segments):
    xs = []
    ys = []

    for _, segment in segments:
        for point in get_segment_points(segment):
            xs.append(point.real)
            ys.append(point.imag)

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    return {
        "x": min_x,
        "y": min_y,
        "width": max_x - min_x,
        "height": max_y - min_y,
    }


def get_segment_points(segment):
    if isinstance(segment, Line):
        return [segment.start, segment.end]

    if isinstance(segment, QuadraticBezier):
        return [segment.start, segment.control, segment.end]

    if isinstance(segment, CubicBezier):
        return [
            segment.start,
            segment.control1,
            segment.control2,
            segment.end,
        ]

    return []


def get_scale(svg_frame):
    if DESMOS_TARGET_WIDTH is None:
        return 1

    return DESMOS_TARGET_WIDTH / svg_frame["width"]


def make_frame_mapper_and_viewport(svg_frame, scale):
    svg_x = svg_frame["x"]
    svg_y = svg_frame["y"]
    svg_width = svg_frame["width"]
    svg_height = svg_frame["height"]

    desmos_width = svg_width * scale
    desmos_height = svg_height * scale

    anchor_x, anchor_y = get_anchor_position(
        width=desmos_width,
        height=desmos_height,
        anchor=FRAME_ANCHOR,
    )

    target_x, target_y = ANCHOR_POINT

    offset_x = target_x - anchor_x
    offset_y = target_y - anchor_y

    def mapper(point):
        # Convert SVG x to frame-local x.
        local_x = (point.real - svg_x) * scale

        # Convert SVG y to frame-local y.
        if FLIP_Y:
            local_y = (svg_y + svg_height - point.imag) * scale
        else:
            local_y = (point.imag - svg_y) * scale

        x = local_x + offset_x
        y = local_y + offset_y

        return clean(x), clean(y)

    viewport = {
        "left": clean(offset_x),
        "right": clean(offset_x + desmos_width),
        "bottom": clean(offset_y),
        "top": clean(offset_y + desmos_height),
    }

    desmos_frame = {
        "anchor": FRAME_ANCHOR,
        "anchor_point": {
            "x": ANCHOR_POINT[0],
            "y": ANCHOR_POINT[1],
        },
        "scale": scale,
        "width": clean(desmos_width),
        "height": clean(desmos_height),
        "left": viewport["left"],
        "right": viewport["right"],
        "bottom": viewport["bottom"],
        "top": viewport["top"],
        "center_x": clean((viewport["left"] + viewport["right"]) / 2),
        "center_y": clean((viewport["bottom"] + viewport["top"]) / 2),
    }

    return mapper, viewport, desmos_frame


def get_anchor_position(width, height, anchor):
    anchors = {
        "left_bottom": (0, 0),
        "left_top": (0, height),
        "right_bottom": (width, 0),
        "right_top": (width, height),
        "center": (width / 2, height / 2),
    }

    if anchor not in anchors:
        valid = ", ".join(anchors.keys())
        raise ValueError(f"Invalid FRAME_ANCHOR: {anchor}. Valid options: {valid}")

    return anchors[anchor]


def get_frame_number(svg_path: Path):
    """
    Extracts frame number from names like:
    frame_00000.svg
    frame_00123.svg
    """
    match = re.search(r"(\d+)", svg_path.stem)

    if not match:
        return 0

    return int(match.group(1))


def clean(value):
    if abs(value) < 10 ** (-ROUND_DIGITS):
        value = 0

    return round(value, ROUND_DIGITS)


def num(value):
    return str(clean(value))


def point_xy(point, mapper):
    x, y = mapper(point)
    return num(x), num(y)


def line_to_latex(segment, mapper):
    x0, y0 = point_xy(segment.start, mapper)
    x1, y1 = point_xy(segment.end, mapper)

    x_expr = f"({x0})(1-t)+({x1})t"
    y_expr = f"({y0})(1-t)+({y1})t"

    return rf"\left({x_expr},{y_expr}\right)\left\{{0\le t\le 1\right\}}"


def quadratic_to_latex(segment, mapper):
    x0, y0 = point_xy(segment.start, mapper)
    x1, y1 = point_xy(segment.control, mapper)
    x2, y2 = point_xy(segment.end, mapper)

    x_expr = f"({x0})(1-t)^2+2({x1})t(1-t)+({x2})t^2"
    y_expr = f"({y0})(1-t)^2+2({y1})t(1-t)+({y2})t^2"

    return rf"\left({x_expr},{y_expr}\right)\left\{{0\le t\le 1\right\}}"


def cubic_to_latex(segment, mapper):
    x0, y0 = point_xy(segment.start, mapper)
    x1, y1 = point_xy(segment.control1, mapper)
    x2, y2 = point_xy(segment.control2, mapper)
    x3, y3 = point_xy(segment.end, mapper)

    x_expr = (
        f"({x0})(1-t)^3"
        f"+3({x1})t(1-t)^2"
        f"+3({x2})t^2(1-t)"
        f"+({x3})t^3"
    )

    y_expr = (
        f"({y0})(1-t)^3"
        f"+3({y1})t(1-t)^2"
        f"+3({y2})t^2(1-t)"
        f"+({y3})t^3"
    )

    return rf"\left({x_expr},{y_expr}\right)\left\{{0\le t\le 1\right\}}"


def segment_points_to_latex(x0, y0, x1, y1):
    x0 = num(x0)
    y0 = num(y0)
    x1 = num(x1)
    y1 = num(y1)

    x_expr = f"({x0})(1-t)+({x1})t"
    y_expr = f"({y0})(1-t)+({y1})t"

    return rf"\left({x_expr},{y_expr}\right)\left\{{0\le t\le 1\right\}}"


if __name__ == "__main__":
    main()