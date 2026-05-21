from pathlib import Path
import json
import re
import time

from svgpathtools import (
    svg2paths2,
    Line,
    CubicBezier,
    QuadraticBezier,
)

import constants as C


def main():
    start_time = time.time()

    svg_path = get_preview_svg_path()

    frame_data = svg_to_frame_data(svg_path)

    print_project_info(svg_path, frame_data)

    if current_frame_already_written(frame_data):
        print("current_frame.json already exists with the same SVG/settings. Skipping.")
        return

    write_current_frame_json(frame_data)

    elapsed = time.time() - start_time

    print(f"Wrote {C.PATH_CURRENT_FRAME_JSON}")
    print(f"Expressions: {len(frame_data['expressions'])}")
    print(f"Frame size in Desmos: {frame_data['frame']['width']} x {frame_data['frame']['height']}")
    print(f"Viewport: {frame_data['viewport']}")
    print(f"Elapsed: {elapsed:.2f}s")


# ============================================================
# Setup / direct-run helpers
# ============================================================

def get_preview_svg_path():
    """
    Used only when running this file directly.

    The renderer calls:
        svg_to_frame_data(svg_path)

    directly for each frame.
    """
    svg_path = C.PATH_SVG_FOLDER / f"frame_{C.PREVIEW_FRAME_NUMBER:05d}.svg"

    if not svg_path.exists():
        raise RuntimeError(f"Preview SVG frame not found: {svg_path}")

    return svg_path


def print_project_info(svg_path, frame_data):
    print()
    print("VideoTo2DRenderer SVG-to-Desmos JSON job")
    print("----------------------------------------")
    print(f"Project root:        {C.PROJECT_ROOT}")
    print(f"SVG input:           {svg_path}")
    print(f"Current JSON output: {C.PATH_CURRENT_FRAME_JSON}")
    print(f"Frame number:        {frame_data['frame_number']}")
    print(f"Segments:            {frame_data['segment_count']}")
    print(f"Expressions:         {len(frame_data['expressions'])}")

    if C.MAX_SEGMENTS is not None and frame_data["segment_count"] > C.MAX_SEGMENTS:
        print()
        print("Warning:")
        print(f"  This SVG has {frame_data['segment_count']} segments.")
        print(f"  MAX_SEGMENTS is {C.MAX_SEGMENTS}.")
        print("  svg_to_desmos_json.py does not cut off expressions.")
        print("  Compression should happen earlier in video_to_svg.py.")

    print()


# ============================================================
# Main conversion
# ============================================================

def svg_to_frame_data(svg_path: Path):
    """
    Converts one SVG file into a JSON-compatible dictionary that the
    Desmos HTML viewer can load.

    Important:
    This function does NOT truncate segments with C.MAX_SEGMENTS.
    Segment limiting/compression should happen earlier in video_to_svg.py.
    """
    paths, path_attributes, svg_attributes = svg2paths2(str(svg_path))

    segments = collect_segments(paths)

    svg_frame = get_svg_frame(svg_attributes, segments)

    scale = get_scale(svg_frame)

    mapper, viewport, desmos_frame = make_frame_mapper_and_viewport(
        svg_frame=svg_frame,
        scale=scale,
    )

    frame_number = get_frame_number(svg_path)

    expressions = build_expressions(
        frame_number=frame_number,
        segments=segments,
        mapper=mapper,
        desmos_frame=desmos_frame,
    )

    return {
        "cache": build_current_frame_cache(svg_path),
        "source_svg": str(svg_path.resolve()),
        "frame_number": frame_number,
        "segment_count": len(segments),
        "frame": desmos_frame,
        "viewport": viewport,
        "settings": {
            "show_grid": C.SHOW_GRID,
            "show_axes": C.SHOW_AXES,
            "show_expressions": C.SHOW_EXPRESSIONS,
        },
        "screenshot": {
            "width": C.SCREENSHOT_WIDTH,
            "height": C.SCREENSHOT_HEIGHT,
            "format": C.DESMOS_SCREENSHOT_FORMAT,
            "mode": C.DESMOS_SCREENSHOT_MODE,
            "target_pixel_ratio": C.DESMOS_SCREENSHOT_TARGET_PIXEL_RATIO,
            "show_movable_points": C.DESMOS_SCREENSHOT_SHOW_MOVABLE_POINTS,
            "show_labels": C.DESMOS_SCREENSHOT_SHOW_LABELS,
        },
        "expressions": expressions,
    }


def build_expressions(frame_number, segments, mapper, desmos_frame):
    expressions = []

    if C.SHOW_FRAME_NUMBER_EXPRESSION:
        expressions.append(make_frame_number_expression(frame_number))

    if C.SHOW_FRAME:
        expressions.extend(make_frame_expressions(desmos_frame))

    expressions.extend(make_svg_segment_expressions(segments, mapper))

    return expressions


# ============================================================
# Cache / skip repeated direct calls
# ============================================================

def current_frame_already_written(frame_data):
    if not C.PATH_CURRENT_FRAME_JSON.exists():
        return False

    try:
        previous = json.loads(C.PATH_CURRENT_FRAME_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Existing current_frame.json is not valid JSON. Rewriting.")
        return False

    return previous.get("cache") == frame_data.get("cache")


def write_current_frame_json(frame_data):
    C.PATH_DESMOS_FOLDER.mkdir(parents=True, exist_ok=True)

    C.PATH_CURRENT_FRAME_JSON.write_text(
        json.dumps(frame_data, indent=2),
        encoding="utf-8",
    )


def build_current_frame_cache(svg_path: Path):
    svg_path = svg_path.resolve()
    stat = svg_path.stat()

    return {
        "svg_to_desmos_cache_version": C.SVG_TO_DESMOS_CACHE_VERSION,

        "source_svg": str(svg_path),
        "source_svg_size_bytes": stat.st_size,
        "source_svg_modified_ns": stat.st_mtime_ns,

        "desmos_target_width": C.DESMOS_TARGET_WIDTH,
        "frame_anchor": C.FRAME_ANCHOR,
        "anchor_point": list(C.ANCHOR_POINT),
        "flip_y": C.FLIP_Y,
        "round_digits": C.ROUND_DIGITS,

        "line_width": C.LINE_WIDTH,
        "line_color": C.LINE_COLOR,

        "show_frame": C.SHOW_FRAME,
        "frame_color": C.FRAME_COLOR,
        "frame_line_width": C.FRAME_LINE_WIDTH,

        "show_grid": C.SHOW_GRID,
        "show_axes": C.SHOW_AXES,
        "show_expressions": C.SHOW_EXPRESSIONS,

        "show_frame_number_expression": C.SHOW_FRAME_NUMBER_EXPRESSION,
        "frame_number_variable": C.FRAME_NUMBER_VARIABLE,

        "screenshot_width": C.SCREENSHOT_WIDTH,
        "screenshot_height": C.SCREENSHOT_HEIGHT,
        "desmos_screenshot_format": C.DESMOS_SCREENSHOT_FORMAT,
        "desmos_screenshot_mode": C.DESMOS_SCREENSHOT_MODE,
        "desmos_screenshot_target_pixel_ratio": C.DESMOS_SCREENSHOT_TARGET_PIXEL_RATIO,
        "desmos_screenshot_show_movable_points": C.DESMOS_SCREENSHOT_SHOW_MOVABLE_POINTS,
        "desmos_screenshot_show_labels": C.DESMOS_SCREENSHOT_SHOW_LABELS,
    }


# ============================================================
# SVG parsing
# ============================================================

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
    4. fallback 1x1 frame
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


# ============================================================
# Coordinate mapping
# ============================================================

def get_scale(svg_frame):
    if C.DESMOS_TARGET_WIDTH is None:
        return 1

    return C.DESMOS_TARGET_WIDTH / svg_frame["width"]


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
        anchor=C.FRAME_ANCHOR,
    )

    target_x, target_y = C.ANCHOR_POINT

    offset_x = target_x - anchor_x
    offset_y = target_y - anchor_y

    def mapper(point):
        local_x = (point.real - svg_x) * scale

        if C.FLIP_Y:
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
        "anchor": C.FRAME_ANCHOR,
        "anchor_point": {
            "x": C.ANCHOR_POINT[0],
            "y": C.ANCHOR_POINT[1],
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


# ============================================================
# Desmos expression builders
# ============================================================

def make_frame_number_expression(frame_number):
    return {
        "id": "current_frame",
        "latex": f"{C.FRAME_NUMBER_VARIABLE}={frame_number}",
        "color": "#000000",
        "hidden": True,
    }


def make_frame_expressions(desmos_frame):
    left = desmos_frame["left"]
    right = desmos_frame["right"]
    bottom = desmos_frame["bottom"]
    top = desmos_frame["top"]

    corners = [
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
    ]

    expressions = []

    for i in range(4):
        x0, y0 = corners[i]
        x1, y1 = corners[(i + 1) % 4]

        expressions.append({
            "id": f"frame_{i}",
            "latex": segment_points_to_latex(x0, y0, x1, y1),
            "color": C.FRAME_COLOR,
            "lineWidth": C.FRAME_LINE_WIDTH,
        })

    return expressions


def make_svg_segment_expressions(segments, mapper):
    expressions = []

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
            "color": C.LINE_COLOR,
            "lineWidth": C.LINE_WIDTH,
        })

    return expressions


def line_to_latex(segment, mapper):
    x0, y0 = point_xy(segment.start, mapper)
    x1, y1 = point_xy(segment.end, mapper)

    return segment_points_to_latex(x0, y0, x1, y1)


def quadratic_to_latex(segment, mapper):
    x0, y0 = point_xy(segment.start, mapper)
    x1, y1 = point_xy(segment.control, mapper)
    x2, y2 = point_xy(segment.end, mapper)

    x_expr = f"({x0})(1-t)^2+2({x1})t(1-t)+({x2})t^2"
    y_expr = f"({y0})(1-t)^2+2({y1})t(1-t)+({y2})t^2"

    return parametric_latex(x_expr, y_expr)


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

    return parametric_latex(x_expr, y_expr)


def segment_points_to_latex(x0, y0, x1, y1):
    x0 = num(x0)
    y0 = num(y0)
    x1 = num(x1)
    y1 = num(y1)

    x_expr = f"({x0})(1-t)+({x1})t"
    y_expr = f"({y0})(1-t)+({y1})t"

    return parametric_latex(x_expr, y_expr)


def parametric_latex(x_expr, y_expr):
    return rf"\left({x_expr},{y_expr}\right)\left\{{0\le t\le 1\right\}}"


# ============================================================
# Formatting / utilities
# ============================================================

def get_frame_number(svg_path: Path):
    match = re.search(r"(\d+)", svg_path.stem)

    if not match:
        return 0

    return int(match.group(1))


def parse_numbers(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def parse_svg_length(value):
    if value is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    return float(match.group(0))


def clean(value):
    if abs(value) < 10 ** (-C.ROUND_DIGITS):
        value = 0

    return round(value, C.ROUND_DIGITS)


def num(value):
    return str(clean(float(value)))


def point_xy(point, mapper):
    x, y = mapper(point)

    return num(x), num(y)


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    main()