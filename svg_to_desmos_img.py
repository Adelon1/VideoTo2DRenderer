import ast
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import constants as C
from svg_to_desmos_json import svg_to_frame_data

def main():
    start_time = time.time()

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
        storage_state = prepare_viewport_if_needed(svg_files)

        rendered_frames = render_frames_parallel(
            svg_files=svg_files,
            storage_state=storage_state,
        )

        write_desmos_img_info(
            config=render_config,
            status="complete",
            rendered_frames=rendered_frames,
        )

    finally:
        server.shutdown()
        server.server_close()

    elapsed = time.time() - start_time

    print("Done.")
    print(f"Elapsed: {elapsed:.2f}s")


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
    Called only when the cache does not match.

    At that point old PNG frames are unsafe to keep because they may have
    been produced with different SVG, Desmos, viewport, or screenshot settings.
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
    print(f"Image info:         {C.PATH_DESMOS_IMG_INFO}")
    print(f"Frames to render:   {len(svg_files)}")
    print(f"Screenshot size:    {C.SCREENSHOT_WIDTH}x{C.SCREENSHOT_HEIGHT}")
    print(f"Workers:            {C.DESMOS_RENDER_WORKERS}")
    print(f"Headless render:    {C.HEADLESS}")
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


def get_viewer_url(direct=False):
    relative_html = C.PATH_DESMOS_VIEWER.relative_to(C.PROJECT_ROOT)
    url_path = "/" + relative_html.as_posix()

    url = f"http://127.0.0.1:{C.PORT}{url_path}"

    if direct:
        url += "?direct=1"

    return url


# ============================================================
# Manual viewport setup
# ============================================================

def prepare_viewport_if_needed(svg_files):
    """
    Opens the first frame visibly so the user can set the Desmos viewport.

    Returns Playwright storage_state so worker browsers can reuse the saved
    localStorage viewport.
    """
    if not C.WAIT_BEFORE_DESMOS_IMG_RENDER:
        return None

    viewer_url = get_viewer_url(direct=True)
    first_frame_data = svg_to_frame_data(svg_files[0])

    with sync_playwright() as p:
        browser, context, page = open_browser_page(
            playwright=p,
            viewer_url=viewer_url,
            headless=False,
            storage_state=None,
        )

        try:
            load_frame_data_in_page(
                page=page,
                frame_data=first_frame_data,
            )

            print()
            print("Browser is open with the first frame loaded.")
            print("Set your viewpoint in Desmos now.")
            print("You may click 'Save View as Default', or just leave the view where you want it.")
            print("Python will save the current visible viewpoint after you press the start key.")
            print()

            wait_for_start_key(C.DESMOS_IMG_START_KEY)

            save_current_viewport_to_local_storage(page)

            storage_state = context.storage_state()
            save_storage_state(storage_state)

        finally:
            context.close()
            browser.close()

    return storage_state


def save_current_viewport_to_local_storage(page):
    """
    Saves the currently visible Desmos viewport as the default viewport.

    This means the user does not strictly have to click "Save View as Default".
    """
    page.evaluate(
        """
        () => {
          if (typeof window.saveCurrentViewportToLocalStorage === "function") {
            window.saveCurrentViewportToLocalStorage();
            return;
          }

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
        }
        """
    )


# ============================================================
# Parallel rendering
# ============================================================

def render_frames_parallel(svg_files, storage_state):
    jobs = [
        {
            "output_index": output_index,
            "svg_path": str(svg_path),
        }
        for output_index, svg_path in enumerate(svg_files)
    ]

    return render_jobs_parallel(
        jobs=jobs,
        storage_state=storage_state,
    )


def render_jobs_parallel(jobs, storage_state):
    worker_count = get_worker_count(len(jobs))

    if worker_count == 1:
        print("Rendering with 1 worker...")

        render_worker(
            worker_id=0,
            jobs=jobs,
            storage_state=storage_state,
        )

        return len(jobs)

    print(f"Rendering with {worker_count} workers...")

    job_chunks = split_jobs(jobs, worker_count)

    completed_frames = 0

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = []

        for worker_id, chunk in enumerate(job_chunks):
            if not chunk:
                continue

            future = executor.submit(
                render_worker,
                worker_id,
                chunk,
                storage_state,
            )

            futures.append(future)

        for future in as_completed(futures):
            rendered_count = future.result()
            completed_frames += rendered_count
            print(f"Worker finished. Total completed so far: {completed_frames}/{len(jobs)}")

    return len(jobs)


def get_worker_count(job_count):
    requested = int(C.DESMOS_RENDER_WORKERS)

    if requested < 1:
        requested = 1

    return min(requested, job_count)


def split_jobs(jobs, worker_count):
    """
    Round-robin split.

    This avoids one worker getting all expensive neighboring frames if some
    frame ranges are more complex than others.
    """
    chunks = [[] for _ in range(worker_count)]

    for index, job in enumerate(jobs):
        chunks[index % worker_count].append(job)

    return chunks


def render_worker(worker_id, jobs, storage_state):
    """
    Worker process entrypoint.

    Each worker owns:
    - its own Playwright instance
    - its own Chromium browser
    - its own Desmos page

    No current_frame.json is used here.
    """
    viewer_url = get_viewer_url(direct=True)

    with sync_playwright() as p:
        browser, context, page = open_browser_page(
            playwright=p,
            viewer_url=viewer_url,
            headless=C.HEADLESS,
            storage_state=storage_state,
        )

        try:
            if C.SCREENSHOT_MODE:
                page.evaluate("window.setScreenshotMode(true)")

            rendered_count = 0

            for job in jobs:
                output_index = job["output_index"]
                svg_path = job["svg_path"]

                render_single_frame(
                    page=page,
                    worker_id=worker_id,
                    output_index=output_index,
                    svg_path=svg_path,
                )

                rendered_count += 1

        finally:
            context.close()
            browser.close()

    return rendered_count


def render_single_frame(page, worker_id, output_index, svg_path):
    svg_path = Path(svg_path)

    frame_data = svg_to_frame_data(svg_path)
    frame_number = frame_data.get("frame_number", output_index)

    print(
        f"[worker {worker_id}] Rendering {svg_path.name} "
        f"-> frame_{output_index:05d}.png"
    )

    ok = load_frame_data_in_page(
        page=page,
        frame_data=frame_data,
    )

    if not ok:
        error_text = page.evaluate("window.__V2D_RENDER_ERROR")
        raise RuntimeError(
            f"Worker {worker_id} failed to load frame {frame_number}: {error_text}"
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


# ============================================================
# Browser helpers
# ============================================================

def open_browser_page(playwright, viewer_url, headless, storage_state=None):
    browser = launch_chromium(
        playwright=playwright,
        headless=headless,
    )

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

    page.goto(viewer_url, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.loadFrameData === 'function'")
    page.wait_for_function("typeof window.captureCurrentFrameScreenshot === 'function'")

    if C.PRINT_BROWSER_GPU_INFO:
        print_browser_gpu_info(page)

    return browser, context, page


def load_frame_data_in_page(page, frame_data):
    return page.evaluate(
        """
        async data => {
          return await window.loadFrameData(data);
        }
        """,
        frame_data,
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
    Uses Desmos asyncScreenshot() as the render-complete signal.

    Then waits long enough for the visible browser viewport to paint.

    Instead of hardcoding 16 ms, Chromium measures its own animation-frame
    interval using requestAnimationFrame(). We round up for safety.
    """
    page.evaluate(
        """
        async settings => {
          await window.captureCurrentFrameScreenshot();

          const finishedAt = performance.now();

          let frameMs;

          if (settings.autoSettleFromRefreshRate) {
            frameMs = await measureAnimationFrameMs();
          } else {
            frameMs = 1000 / settings.fallbackRefreshRate;
          }

          const roundedFrameMs = Math.ceil(frameMs);
          const targetWaitMs = roundedFrameMs * (1 + settings.extraSettleFrames);

          await waitUntilAfterNextPaint();

          const elapsed = performance.now() - finishedAt;
          const remaining = targetWaitMs - elapsed;

          if (remaining > 0) {
            await new Promise(resolve => setTimeout(resolve, Math.ceil(remaining)));
          }
        }

        async function measureAnimationFrameMs() {
          if (window.__V2D_REFRESH_FRAME_MS) {
            return window.__V2D_REFRESH_FRAME_MS;
          }

          const samples = [];

          let previous = await nextAnimationFrameTime();

          for (let i = 0; i < 8; i++) {
            const current = await nextAnimationFrameTime();
            samples.push(current - previous);
            previous = current;
          }

          samples.sort((a, b) => a - b);

          // Median is more stable than average.
          const median = samples[Math.floor(samples.length / 2)];

          window.__V2D_REFRESH_FRAME_MS = median;

          return median;
        }

        function nextAnimationFrameTime() {
          return new Promise(resolve => {
            requestAnimationFrame(time => resolve(time));
          });
        }

        function waitUntilAfterNextPaint() {
          return new Promise(resolve => {
            requestAnimationFrame(() => {
              setTimeout(resolve, 0);
            });
          });
        }
        """,
        {
            "autoSettleFromRefreshRate": C.AUTO_SCREENSHOT_SETTLE_FROM_REFRESH_RATE,
            "fallbackRefreshRate": C.FALLBACK_REFRESH_RATE,
            "extraSettleFrames": C.SCREENSHOT_EXTRA_SETTLE_FRAMES,
        },
    )


def take_browser_viewport_screenshot(page, output_path):
    """
    Captures the full browser viewport.
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

        "desmos_render_workers": C.DESMOS_RENDER_WORKERS,
        "use_nvidia_prime": C.USE_NVIDIA_PRIME,

        "screenshot_width": C.SCREENSHOT_WIDTH,
        "screenshot_height": C.SCREENSHOT_HEIGHT,
        "screenshot_mode": C.SCREENSHOT_MODE,

        "auto_screenshot_settle_from_refresh_rate": C.AUTO_SCREENSHOT_SETTLE_FROM_REFRESH_RATE,
        "fallback_refresh_rate": C.FALLBACK_REFRESH_RATE,
        "screenshot_extra_settle_frames": C.SCREENSHOT_EXTRA_SETTLE_FRAMES,

        "desmos_screenshot_format": C.DESMOS_SCREENSHOT_FORMAT,
        "desmos_screenshot_mode": C.DESMOS_SCREENSHOT_MODE,
        "desmos_screenshot_target_pixel_ratio": C.DESMOS_SCREENSHOT_TARGET_PIXEL_RATIO,
        "desmos_screenshot_show_movable_points": C.DESMOS_SCREENSHOT_SHOW_MOVABLE_POINTS,
        "desmos_screenshot_show_labels": C.DESMOS_SCREENSHOT_SHOW_LABELS,

        "final_screenshot_source": "playwright_viewport_after_desmos_async_screenshot",
        "frame_transport": "direct_python_to_window_loadFrameData",

        "wait_before_desmos_img_render": C.WAIT_BEFORE_DESMOS_IMG_RENDER,

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


def launch_chromium(playwright, headless):
    launch_options = {
        "headless": headless,
    }

    if C.USE_NVIDIA_PRIME:
        env = os.environ.copy()
        env.update(C.NVIDIA_PRIME_ENV)
        launch_options["env"] = env

    return playwright.chromium.launch(**launch_options)


def print_browser_gpu_info(page):
    """
    Prints WebGL GPU information from inside Chromium.

    On your fixed dGPU-only setup, this should say NVIDIA.
    """
    try:
        info = page.evaluate(
            """
            () => {
              const canvas = document.createElement("canvas");

              const gl =
                canvas.getContext("webgl2", { powerPreference: "high-performance" }) ||
                canvas.getContext("webgl", { powerPreference: "high-performance" });

              if (!gl) {
                return {
                  ok: false,
                  error: "No WebGL context"
                };
              }

              const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");

              const result = {
                ok: true,
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                version: gl.getParameter(gl.VERSION),
              };

              if (debugInfo) {
                result.unmaskedVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                result.unmaskedRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
              }

              return result;
            }
            """
        )

        print("Browser GPU info:")
        print(json.dumps(info, indent=2))

    except Exception as exc:
        print(f"Could not read browser GPU info: {exc}")


def save_storage_state(storage_state):
    C.PATH_DESMOS_STORAGE_STATE.write_text(
        json.dumps(storage_state, indent=2),
        encoding="utf-8",
    )


def load_storage_state_if_available():
    if not C.PATH_DESMOS_STORAGE_STATE.exists():
        return None

    try:
        return json.loads(C.PATH_DESMOS_STORAGE_STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Warning: saved Desmos storage state is invalid. Ignoring it.")
        return None


def read_desmos_img_info():
    if not C.PATH_DESMOS_IMG_INFO.exists():
        raise RuntimeError(
            f"No previous Desmos image render info found: {C.PATH_DESMOS_IMG_INFO}"
        )

    try:
        return json.loads(C.PATH_DESMOS_IMG_INFO.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("desmos_img_info.txt is not valid JSON.") from exc


def rerender_selected_frames(frame_indexes):
    """
    Rerenders only selected screenshot frame indexes.

    Example:
        rerender_selected_frames([0, 4, 17])

    This overwrites only:
        rendered_frames/frame_00000.png
        rendered_frames/frame_00004.png
        rendered_frames/frame_00017.png

    It refuses to run if the current constants/config do not match the last
    successful full render.
    """
    if not frame_indexes:
        print("No frame indexes given. Nothing to rerender.")
        return

    check_tools()
    ensure_folders()

    svg_files = get_svg_files()
    current_config = build_desmos_img_config(svg_files)

    previous_info = read_desmos_img_info()

    if previous_info.get("status") != "complete":
        raise RuntimeError("Previous Desmos image render was not complete.")

    previous_config = previous_info.get("config")

    if previous_config != current_config:
        raise RuntimeError(
            "Current render settings do not match the previous successful render.\n"
            "To safely rerender only selected frames, restore the same constants.py "
            "settings as the previous render, or do a full rerender."
        )

    unique_indexes = sorted(set(int(index) for index in frame_indexes))

    jobs = []

    for output_index in unique_indexes:
        if output_index < 0 or output_index >= len(svg_files):
            raise ValueError(
                f"Invalid frame index {output_index}. "
                f"Valid range is 0 to {len(svg_files) - 1}."
            )

        jobs.append({
            "output_index": output_index,
            "svg_path": str(svg_files[output_index]),
        })

    storage_state = load_storage_state_if_available()

    print()
    print("Rerendering selected frames")
    print("---------------------------")
    print(f"Frames: {unique_indexes}")
    print(f"Using saved viewport: {storage_state is not None}")
    print()

    server = start_server()

    try:
        render_jobs_parallel(
            jobs=jobs,
            storage_state=storage_state,
        )

    finally:
        server.shutdown()
        server.server_close()

    print("Selected frame rerender complete.")


# ============================================================
# Command-line interface
# ============================================================

def run_from_command_line():
    """
    Command-line behavior:

    Full render:
        python svg_to_desmos_img.py

    Rerender selected frames:
        python svg_to_desmos_img.py 0 1 7 23 41

    Or:
        python svg_to_desmos_img.py "[0, 1, 7, 23, 41]"
    """
    args = sys.argv[1:]

    if not args:
        main()
        return

    if args[0] in {"-h", "--help"}:
        print_cli_help()
        return

    frame_indexes = parse_frame_indexes(args)

    rerender_selected_frames(frame_indexes)


def parse_frame_indexes(args):
    """
    Supports:

        python svg_to_desmos_img.py 0 1 7
        python svg_to_desmos_img.py 0-59
        python svg_to_desmos_img.py 0-59 80 100-120
        python svg_to_desmos_img.py "0-59, 80, 100-120"
        python svg_to_desmos_img.py "[0, 1, 7, 23, 41]"

    Recommended range syntax:
        0-59

    Do not use spaces inside the range.
    """
    if len(args) == 1:
        text = args[0].strip()

        # Python-style list: "[0, 1, 7]"
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"Invalid frame list: {text}") from exc

            if not isinstance(parsed, list):
                raise ValueError(
                    "Frame list must be a Python-style list, e.g. [0, 1, 7]."
                )

            return sorted(set(int(value) for value in parsed))

        # Comma-separated string: "0-59, 80, 100-120"
        if "," in text:
            parts = [part.strip() for part in text.split(",") if part.strip()]
            return expand_frame_tokens(parts)

    # Space-separated tokens: 0-59 80 100-120
    return expand_frame_tokens(args)


def expand_frame_tokens(tokens):
    frame_indexes = []

    for token in tokens:
        token = token.strip()

        # Single number
        if re.fullmatch(r"\d+", token):
            frame_indexes.append(int(token))
            continue

        # Range like 0-59
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)

        if match:
            start = int(match.group(1))
            end = int(match.group(2))

            if end < start:
                raise ValueError(
                    f"Invalid range '{token}'. End must be >= start."
                )

            frame_indexes.extend(range(start, end + 1))
            continue

        raise ValueError(
            f"Invalid frame token: '{token}'. "
            "Use numbers like 7 or ranges like 0-59."
        )

    return sorted(set(frame_indexes))


def print_cli_help():
    print()
    print("Usage:")
    print("  python svg_to_desmos_img.py")
    print("      Full Desmos image render.")
    print()
    print("  python svg_to_desmos_img.py 0 1 7 23 41")
    print("      Rerender only selected frame indexes.")
    print()
    print("  python svg_to_desmos_img.py 0-59")
    print("      Rerender a frame range.")
    print()
    print("  python svg_to_desmos_img.py 0-59 80 100-120")
    print("      Rerender a mix of ranges and single frames.")
    print()
    print('  python svg_to_desmos_img.py "0-59, 80, 100-120"')
    print("      Same thing as one quoted string.")
    print()
    print('  python svg_to_desmos_img.py "[0, 1, 7, 23, 41]"')
    print("      Same thing, using a Python-style list.")
    print()

# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    start_time = time.time()

    try:
        run_from_command_line()
    except KeyboardInterrupt:
        print("\nCancelled.")

    elapsed = time.time() - start_time
    print(f"Elapsed: {elapsed:.2f}s")
