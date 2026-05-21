from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import constants as C
from svg_to_desmos_json import svg_to_frame_data


def main():
    check_tools()
    ensure_folders()

    svg_files = get_svg_files()
    render_config = build_desmos_img_config(svg_files)

    print_project_info(svg_files)

    if should_skip_render(render_config):
        print("Desmos screenshots already exist with the same settings. Skipping.")
        print(f"Rendered frames folder: {C.PATH_RENDERED_FRAMES_FOLDER}")
        return

    clear_old_render_outputs()

    write_desmos_img_info(
        config=render_config,
        status="in_progress",
        rendered_frames=0,
    )

    server = start_server()

    try:
        rendered_frames = render_frames(svg_files)

        write_desmos_img_info(
            config=render_config,
            status="complete",
            rendered_frames=rendered_frames,
        )

    finally:
        server.shutdown()
        server.server_close()

    print("Done.")


# ============================================================
# Setup
# ============================================================

def check_tools():
    if not C.PATH_SVG_FOLDER.exists():
        raise RuntimeError(f"SVG folder not found: {C.PATH_SVG_FOLDER}")

    if not C.PATH_DESMOS_FOLDER.exists():
        raise RuntimeError(f"Desmos folder not found: {C.PATH_DESMOS_FOLDER}")

    if not C.PATH_DESMOS_VIEWER.exists():
        raise RuntimeError(f"Desmos viewer HTML not found: {C.PATH_DESMOS_VIEWER}")


def ensure_folders():
    C.PATH_DESMOS_FOLDER.mkdir(parents=True, exist_ok=True)
    C.PATH_RENDERED_FRAMES_FOLDER.mkdir(parents=True, exist_ok=True)
    C.PATH_VIDEO_FOLDER.mkdir(parents=True, exist_ok=True)


def clear_old_render_outputs():
    """
    Called only when the current render stats do NOT match the cache.

    At that point old PNG frames are unsafe to keep, because they may have
    different viewport, expression, SVG, screenshot, or Desmos settings.
    """
    old_files = list(C.PATH_RENDERED_FRAMES_FOLDER.glob("frame_*.png"))

    if old_files:
        print(f"Removing {len(old_files)} old screenshots...")

    for path in old_files:
        path.unlink()


def get_svg_files():
    svg_files = sorted(C.PATH_SVG_FOLDER.glob("frame_*.svg"))

    if not svg_files:
        raise RuntimeError(f"No SVG frames found in: {C.PATH_SVG_FOLDER}")

    svg_files = svg_files[C.START_INDEX:]

    if C.RENDER_FRAME_LIMIT is not None:
        svg_files = svg_files[:C.RENDER_FRAME_LIMIT]

    if not svg_files:
        raise RuntimeError("No SVG frames selected after START_INDEX / RENDER_FRAME_LIMIT.")

    return svg_files


def print_project_info(svg_files):
    print()
    print("VideoTo2DRenderer SVG-to-Desmos-image job")
    print("-----------------------------------------")
    print(f"Project root:       {C.PROJECT_ROOT}")
    print(f"Video folder:       {C.PATH_VIDEO_FOLDER}")
    print(f"SVG folder:         {C.PATH_SVG_FOLDER}")
    print(f"Rendered frames:    {C.PATH_RENDERED_FRAMES_FOLDER}")
    print(f"Desmos folder:      {C.PATH_DESMOS_FOLDER}")
    print(f"Current JSON:       {C.PATH_CURRENT_FRAME_JSON}")
    print(f"Image info:         {C.PATH_DESMOS_IMG_INFO}")
    print(f"Frames to render:   {len(svg_files)}")
    print(f"Screenshot size:    {C.SCREENSHOT_WIDTH}x{C.SCREENSHOT_HEIGHT}")
    print(f"Headless:           {C.HEADLESS}")
    print()


# ============================================================
# Local server
# ============================================================

def start_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(C.PROJECT_ROOT))

    server = ThreadingHTTPServer(("127.0.0.1", C.PORT), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"Serving project at http://127.0.0.1:{C.PORT}")

    return server


def get_viewer_url():
    relative_html = C.PATH_DESMOS_VIEWER.relative_to(C.PROJECT_ROOT)
    url_path = "/" + relative_html.as_posix()

    return f"http://127.0.0.1:{C.PORT}{url_path}"


# ============================================================
# Rendering
# ============================================================

def render_frames(svg_files):
    viewer_url = get_viewer_url()

    with sync_playwright() as p:
        # ------------------------------------------------------------
        # First browser launch
        #
        # If we need manual setup, force headed mode so the user can see
        # and interact with Desmos.
        #
        # If no manual setup is needed, respect C.HEADLESS immediately.
        # ------------------------------------------------------------

        setup_needs_visible_browser = C.WAIT_BEFORE_DESMOS_IMG_RENDER
        first_launch_headless = False if setup_needs_visible_browser else C.HEADLESS

        browser, context, page = open_browser_page(
            playwright=p,
            viewer_url=viewer_url,
            headless=first_launch_headless,
        )

        first_frame_data = svg_to_frame_data(svg_files[0])
        write_current_frame_json(first_frame_data)

        page.goto(viewer_url, wait_until="domcontentloaded")
        page.wait_for_function("typeof window.loadFrame === 'function'")
        page.wait_for_function("typeof window.captureCurrentFrameScreenshot === 'function'")

        wait_until_desmos_ready(
            page=page,
            expected_frame_number=first_frame_data.get("frame_number", 0),
        )

        # ------------------------------------------------------------
        # Manual setup phase
        # ------------------------------------------------------------

        storage_state = None

        if C.WAIT_BEFORE_DESMOS_IMG_RENDER:
            print()
            print("Browser is open with the first frame loaded.")
            print("Set your viewpoint in Desmos now.")
            print("You may click 'Save View as Default', or just leave the view where you want it.")
            print("Python will also try to save the current visible viewpoint before rendering.")
            print()

            wait_for_start_key(C.DESMOS_IMG_START_KEY)

            save_current_viewport_to_local_storage(page)

            storage_state = context.storage_state()

            # ------------------------------------------------------------
            # If user wants headless rendering, relaunch headless now.
            # Playwright cannot convert an existing headed browser to headless.
            # ------------------------------------------------------------

            if C.HEADLESS:
                context.close()
                browser.close()

                browser, context, page = open_browser_page(
                    playwright=p,
                    viewer_url=viewer_url,
                    headless=True,
                    storage_state=storage_state,
                )

                page.goto(viewer_url, wait_until="domcontentloaded")
                page.wait_for_function("typeof window.loadFrame === 'function'")
                page.wait_for_function("typeof window.captureCurrentFrameScreenshot === 'function'")

                wait_until_desmos_ready(
                    page=page,
                    expected_frame_number=first_frame_data.get("frame_number", 0),
                )

        # ------------------------------------------------------------
        # Rendering phase
        # ------------------------------------------------------------

        if C.SCREENSHOT_MODE:
            page.evaluate("window.setScreenshotMode(true)")

        for output_index, svg_path in enumerate(svg_files):
            frame_data = svg_to_frame_data(svg_path)
            frame_number = frame_data.get("frame_number", output_index)

            write_current_frame_json(frame_data)

            print(f"Rendering {svg_path.name} -> frame_{output_index:05d}.png")

            ok = page.evaluate("window.loadFrame()")

            if not ok:
                error_text = page.evaluate("window.__V2D_RENDER_ERROR")
                raise RuntimeError(
                    f"Browser failed to load frame {frame_number}: {error_text}"
                )

            wait_until_desmos_ready(
                page=page,
                expected_frame_number=frame_number,
            )

            wait_for_desmos_async_screenshot_signal(page)

            screenshot_path = C.PATH_RENDERED_FRAMES_FOLDER / f"frame_{output_index:05d}.png"

            take_browser_viewport_screenshot(
                page=page,
                output_path=screenshot_path,
            )

        rendered_count = len(svg_files)

        context.close()
        browser.close()

        return rendered_count


def write_current_frame_json(frame_data):
    C.PATH_CURRENT_FRAME_JSON.write_text(
        json.dumps(frame_data, indent=2),
        encoding="utf-8",
    )


def wait_until_desmos_ready(page, expected_frame_number):
    try:
        page.wait_for_function(
            """
            expected => {
              return window.__V2D_RENDER_DONE === true
                && window.__V2D_RENDER_FRAME === expected
                && !window.__V2D_RENDER_ERROR;
            }
            """,
            arg=expected_frame_number,
            timeout=C.RENDER_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError:
        error_text = page.evaluate("window.__V2D_RENDER_ERROR")
        done = page.evaluate("window.__V2D_RENDER_DONE")
        current_frame = page.evaluate("window.__V2D_RENDER_FRAME")
        stage = page.evaluate("window.__V2D_RENDER_STAGE")

        raise RuntimeError(
            "Timed out waiting for Desmos frame setup.\n"
            f"Expected frame: {expected_frame_number}\n"
            f"Browser frame: {current_frame}\n"
            f"Done flag: {done}\n"
            f"Stage: {stage}\n"
            f"Browser error: {error_text}"
        )


def wait_for_desmos_async_screenshot_signal(page):
    """
    Uses Desmos asyncScreenshot() only as a render-complete signal.

    We intentionally ignore the returned image because Desmos asyncScreenshot()
    captures only the graph area. After it returns, Playwright captures the
    whole browser viewport instead.
    """
    page.evaluate(
        """
        async () => {
          await window.captureCurrentFrameScreenshot();

          await new Promise(resolve => {
            requestAnimationFrame(() => {
              requestAnimationFrame(resolve);
            });
          });
        }
        """
    )


def take_browser_viewport_screenshot(page, output_path):
    """
    Captures the full browser viewport.

    This includes whatever is visible in the page:
    graph area, expression list, axes, UI state, etc.
    """
    page.screenshot(
        path=str(output_path),
        full_page=False,
    )


# ============================================================
# Manual start
# ============================================================

def wait_for_start_key(start_key):
    print(f"Press '{start_key}' in this terminal to start rendering Desmos screenshots.")
    print("Press 'q' to cancel.")

    start_key = start_key.lower()

    if not sys.stdin.isatty():
        input("Terminal does not support single-key input. Press Enter to start.")
        return

    if os.name == "nt":
        wait_for_start_key_windows(start_key)
    else:
        wait_for_start_key_unix(start_key)


def wait_for_start_key_windows(start_key):
    import msvcrt

    while True:
        char = msvcrt.getch().decode(errors="ignore").lower()

        if char == start_key:
            print("Starting screenshot render...")
            return

        if char == "q":
            raise KeyboardInterrupt("Render cancelled by user.")


def wait_for_start_key_unix(start_key):
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while True:
            char = sys.stdin.read(1).lower()

            if char == start_key:
                print("Starting screenshot render...")
                return

            if char == "q":
                raise KeyboardInterrupt("Render cancelled by user.")

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ============================================================
# Cache
# ============================================================

def build_desmos_img_config(svg_files):
    return {
        "desmos_img_cache_version": C.DESMOS_IMG_CACHE_VERSION,

        "svg_folder": str(C.PATH_SVG_FOLDER.resolve()),
        "svg_count": len(svg_files),
        "svg_fingerprint": fingerprint_svg_files(svg_files),

        "rendered_frames_folder": str(C.PATH_RENDERED_FRAMES_FOLDER.resolve()),

        "start_index": C.START_INDEX,
        "render_frame_limit": C.RENDER_FRAME_LIMIT,

        "screenshot_width": C.SCREENSHOT_WIDTH,
        "screenshot_height": C.SCREENSHOT_HEIGHT,
        "screenshot_mode": C.SCREENSHOT_MODE,

        "desmos_screenshot_format": C.DESMOS_SCREENSHOT_FORMAT,
        "desmos_screenshot_mode": C.DESMOS_SCREENSHOT_MODE,
        "desmos_screenshot_target_pixel_ratio": C.DESMOS_SCREENSHOT_TARGET_PIXEL_RATIO,
        "desmos_screenshot_show_movable_points": C.DESMOS_SCREENSHOT_SHOW_MOVABLE_POINTS,
        "desmos_screenshot_show_labels": C.DESMOS_SCREENSHOT_SHOW_LABELS,

        "final_screenshot_source": "playwright_viewport_after_desmos_async_screenshot",

        "wait_before_desmos_img_render": C.WAIT_BEFORE_DESMOS_IMG_RENDER,

        "desmos_target_width": C.DESMOS_TARGET_WIDTH,
        "frame_anchor": C.FRAME_ANCHOR,
        "anchor_point": list(C.ANCHOR_POINT),
        "flip_y": C.FLIP_Y,
        "round_digits": C.ROUND_DIGITS,
        "max_segments": C.MAX_SEGMENTS,

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
    }


def should_skip_render(current_config):
    """
    Skip only when:
    1. desmos_img_info.txt exists,
    2. previous status is complete,
    3. previous config equals current config,
    4. every expected PNG frame exists.
    """
    if not C.PATH_DESMOS_IMG_INFO.exists():
        return False

    try:
        previous = json.loads(C.PATH_DESMOS_IMG_INFO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("desmos_img_info.txt is not valid JSON. Rendering again.")
        return False

    if previous.get("status") != "complete":
        print("Previous Desmos image render was not complete. Rendering again.")
        return False

    previous_config = previous.get("config")

    if previous_config != current_config:
        print("Desmos image render settings changed. Rendering again.")
        return False

    expected_frames = previous.get("rendered_frames")

    if not isinstance(expected_frames, int) or expected_frames <= 0:
        print("Desmos image cache has invalid rendered frame count. Rendering again.")
        return False

    for index in range(expected_frames):
        path = C.PATH_RENDERED_FRAMES_FOLDER / f"frame_{index:05d}.png"

        if not path.exists():
            print(f"Missing rendered frame: {path}. Rendering again.")
            return False

    return True


def write_desmos_img_info(config, status, rendered_frames):
    data = {
        "status": status,
        "rendered_frames": rendered_frames,
        "config": config,
    }

    C.PATH_DESMOS_IMG_INFO.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def fingerprint_svg_files(svg_files):
    hasher = hashlib.sha256()

    for path in svg_files:
        stat = path.stat()
        item = f"{path.name}|{stat.st_size}|{stat.st_mtime_ns}\n"
        hasher.update(item.encode("utf-8"))

    return hasher.hexdigest()

def open_browser_page(playwright, viewer_url, headless, storage_state=None):
    browser = playwright.chromium.launch(headless=headless)

    context_options = {
        "viewport": {
            "width": C.SCREENSHOT_WIDTH,
            "height": C.SCREENSHOT_HEIGHT,
        },
        "device_scale_factor": 1,
    }

    if storage_state is not None:
        context_options["storage_state"] = storage_state

    context = browser.new_context(**context_options)

    page = context.new_page()
    page.set_default_timeout(C.RENDER_TIMEOUT_MS)

    return browser, context, page


def save_current_viewport_to_local_storage(page):
    """
    Saves the currently visible Desmos viewport as the default viewport.

    This means the user does not strictly have to click "Save View as Default".
    After pressing the start key, Python stores the current visible view.
    """
    page.evaluate(
        """
        () => {
          try {
            if (typeof calculator === "undefined" || !calculator) {
              return;
            }

            const bounds = calculator.graphpaperBounds.mathCoordinates;

            const viewport = {
              left: bounds.left,
              right: bounds.right,
              bottom: bounds.bottom,
              top: bounds.top
            };

            localStorage.setItem(
              "VideoTo2DRenderer.defaultViewport",
              JSON.stringify(viewport)
            );
          } catch (error) {
            console.warn("Could not save current viewport automatically:", error);
          }
        }
        """
    )


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    start_time = time.time()

    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")

    elapsed = time.time() - start_time
    print(f"Elapsed: {elapsed:.2f}s")