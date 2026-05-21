import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any
import json

from playwright.sync_api import sync_playwright


STRESS_SECONDS = 20
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080


NVIDIA_ENV = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__VK_LAYER_NV_optimus": "NVIDIA_only",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "DRI_PRIME": "1",
}


COMMON_GPU_ARGS = [
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-zero-copy",
    "--enable-webgl",
    "--enable-webgl2",
]


@dataclass
class TestConfig:
    name: str
    headless: bool
    env: dict[str, str]
    args: list[str]
    channel: str | None = None
    ignore_disable_gpu: bool = True


TEST_CONFIGS = [
    TestConfig(
        name="02_prime_env_headed",
        headless=False,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS,
    ),
    TestConfig(
        name="03_prime_desktop_gl_headed",
        headless=False,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--use-gl=desktop",
            "--disable-software-rasterizer",
        ],
    ),
    TestConfig(
        name="04_prime_egl_angle_opengl_headed",
        headless=False,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--use-gl=egl",
            "--use-angle=opengl",
            "--disable-software-rasterizer",
        ],
    ),
    TestConfig(
        name="05_prime_x11_desktop_gl_headed",
        headless=False,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--ozone-platform=x11",
            "--use-gl=desktop",
            "--disable-software-rasterizer",
        ],
    ),
    TestConfig(
        name="06_prime_wayland_egl_headed",
        headless=False,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--ozone-platform=wayland",
            "--use-gl=egl",
            "--disable-software-rasterizer",
        ],
    ),
    TestConfig(
        name="07_prime_env_headless_default",
        headless=True,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS,
    ),
    TestConfig(
        name="08_prime_desktop_gl_headless_default",
        headless=True,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--use-gl=desktop",
            "--disable-software-rasterizer",
        ],
    ),
    TestConfig(
        name="09_prime_new_headless_chromium_channel",
        headless=True,
        env=NVIDIA_ENV,
        args=COMMON_GPU_ARGS + [
            "--use-gl=desktop",
            "--disable-software-rasterizer",
        ],
        channel="chromium",
    ),
]


STRESS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Playwright NVIDIA GPU Test</title>
  <style>
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: black;
      color: white;
      font-family: monospace;
    }

    canvas {
      width: 100vw;
      height: 100vh;
      display: block;
    }

    #info {
      position: fixed;
      top: 8px;
      left: 8px;
      background: rgba(0, 0, 0, 0.65);
      padding: 8px;
      z-index: 10;
      white-space: pre;
    }
  </style>
</head>
<body>
  <div id="info">starting...</div>
  <canvas id="canvas"></canvas>

  <script>
    function getWebGLInfo() {
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

      const info = {
        ok: true,
        version: gl.getParameter(gl.VERSION),
        shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        vendor: gl.getParameter(gl.VENDOR),
        renderer: gl.getParameter(gl.RENDERER),
      };

      if (debugInfo) {
        info.unmaskedVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
        info.unmaskedRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
      }

      return info;
    }

    function compileShader(gl, type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);

      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(shader));
      }

      return shader;
    }

    function createProgram(gl, vertexSource, fragmentSource) {
      const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
      const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);

      const program = gl.createProgram();
      gl.attachShader(program, vertexShader);
      gl.attachShader(program, fragmentShader);
      gl.linkProgram(program);

      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program));
      }

      return program;
    }

    async function startGpuStress(milliseconds) {
      const infoElement = document.getElementById("info");
      const canvas = document.getElementById("canvas");

      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;

      const gl =
        canvas.getContext("webgl2", {
          antialias: false,
          powerPreference: "high-performance",
          preserveDrawingBuffer: false,
        }) ||
        canvas.getContext("webgl", {
          antialias: false,
          powerPreference: "high-performance",
          preserveDrawingBuffer: false,
        });

      if (!gl) {
        throw new Error("Could not create WebGL context.");
      }

      const vertexSource = `
        attribute vec2 position;

        void main() {
          gl_Position = vec4(position, 0.0, 1.0);
        }
      `;

      const fragmentSource = `
        precision highp float;

        uniform vec2 resolution;
        uniform float time;

        void main() {
          vec2 uv = gl_FragCoord.xy / resolution.xy;
          vec3 col = vec3(0.0);

          float x = uv.x;
          float y = uv.y;

          for (int i = 0; i < 220; i++) {
            float fi = float(i);
            float v = sin(x * 40.0 + fi * 0.17 + time * 0.003)
                    * cos(y * 35.0 + fi * 0.11 + time * 0.004);

            col += vec3(
              sin(v + fi * 0.01),
              cos(v + fi * 0.02),
              sin(v + fi * 0.03)
            ) * 0.006;
          }

          gl_FragColor = vec4(abs(col), 1.0);
        }
      `;

      const program = createProgram(gl, vertexSource, fragmentSource);
      gl.useProgram(program);

      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);

      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([
          -1, -1,
           1, -1,
          -1,  1,
          -1,  1,
           1, -1,
           1,  1,
        ]),
        gl.STATIC_DRAW
      );

      const positionLocation = gl.getAttribLocation(program, "position");
      gl.enableVertexAttribArray(positionLocation);
      gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

      const resolutionLocation = gl.getUniformLocation(program, "resolution");
      const timeLocation = gl.getUniformLocation(program, "time");

      const webglInfo = getWebGLInfo();

      const startedAt = performance.now();
      const endAt = startedAt + milliseconds;

      let frames = 0;

      return await new Promise(resolve => {
        function draw(now) {
          gl.viewport(0, 0, canvas.width, canvas.height);
          gl.uniform2f(resolutionLocation, canvas.width, canvas.height);
          gl.uniform1f(timeLocation, now);

          gl.drawArrays(gl.TRIANGLES, 0, 6);
          gl.finish();

          frames += 1;

          infoElement.textContent =
            "WebGL renderer:\\n" +
            JSON.stringify(webglInfo, null, 2) +
            "\\n\\nframes: " + frames;

          if (performance.now() < endAt) {
            requestAnimationFrame(draw);
          } else {
            resolve({
              frames,
              seconds: milliseconds / 1000,
              fps: frames / (milliseconds / 1000),
              webglInfo,
            });
          }
        }

        requestAnimationFrame(draw);
      });
    }

    window.getWebGLInfo = getWebGLInfo;
    window.startGpuStress = startGpuStress;
  </script>
</body>
</html>
"""


def main():
    print()
    print("Playwright NVIDIA GPU test")
    print("==========================")
    print("This uses Playwright-managed Chromium. You do NOT need system Chromium installed.")
    print()

    ensure_nvidia_smi_available()

    with sync_playwright() as p:
        print(f"Playwright Chromium executable:")
        print(f"  {p.chromium.executable_path}")
        print()

        for config in TEST_CONFIGS:
            run_one_config(p, config)


def run_one_config(playwright, config: TestConfig):
    print()
    print("=" * 80)
    print(f"Test: {config.name}")
    print("=" * 80)
    print(f"headless: {config.headless}")
    print(f"channel:  {config.channel}")
    print(f"env:      {config.env}")
    print(f"args:     {config.args}")
    print()

    samples = []
    stop_event = threading.Event()

    monitor_thread = threading.Thread(
        target=sample_nvidia_smi_loop,
        args=(stop_event, samples),
        daemon=True,
    )

    browser = None

    try:
        launch_env = os.environ.copy()
        launch_env.update(config.env)

        launch_options: dict[str, Any] = {
            "headless": config.headless,
            "args": config.args,
            "env": launch_env,
            "timeout": 60_000,
        }

        if config.channel is not None:
            launch_options["channel"] = config.channel

        if config.ignore_disable_gpu:
            launch_options["ignore_default_args"] = ["--disable-gpu"]

        browser = playwright.chromium.launch(**launch_options)

        print_browser_processes("after launch")

        gpu_info = get_cdp_gpu_info(browser)

        context = browser.new_context(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
        )

        page = context.new_page()
        page.set_content(STRESS_HTML, wait_until="domcontentloaded")

        webgl_info = page.evaluate("() => window.getWebGLInfo()")

        print("WebGL info before stress:")
        print_json(webgl_info)

        print("CDP GPU info:")
        print_gpu_summary(gpu_info)

        monitor_thread.start()

        print(f"Running GPU stress for {STRESS_SECONDS} seconds...")
        result = page.evaluate(
            "seconds => window.startGpuStress(seconds * 1000)",
            STRESS_SECONDS,
        )

        stop_event.set()
        monitor_thread.join(timeout=3)

        print()
        print("Stress result:")
        print_json(result)

        print()
        print("nvidia-smi samples:")
        print_nvidia_summary(samples)

        print()
        print("Verdict:")
        print(make_verdict(webgl_info, gpu_info, samples))

        context.close()

    except Exception as exc:
        stop_event.set()
        monitor_thread.join(timeout=3)

        print()
        print("FAILED:")
        print(f"{type(exc).__name__}: {exc}")

    finally:
        if browser is not None:
            browser.close()


def get_cdp_gpu_info(browser):
    try:
        session = browser.new_browser_cdp_session()
        return session.send("SystemInfo.getInfo")
    except Exception as exc:
        return {
            "error": f"{type(exc).__name__}: {exc}"
        }


def print_gpu_summary(gpu_info):
    if not gpu_info:
        print("  No GPU info returned.")
        return

    if "error" in gpu_info:
        print(f"  CDP error: {gpu_info['error']}")
        return

    gpu = gpu_info.get("gpu", {})
    devices = gpu.get("devices", [])
    feature_status = gpu.get("featureStatus", {})

    print("  Devices:")
    for device in devices:
        vendor = device.get("vendorString") or device.get("vendorId")
        device_name = device.get("deviceString") or device.get("deviceId")
        active = device.get("active")
        print(f"    vendor={vendor} device={device_name} active={active}")

    print("  Feature status:")
    for key, value in feature_status.items():
        print(f"    {key}: {value}")


def sample_nvidia_smi_loop(stop_event, samples):
    while not stop_event.is_set():
        sample = read_nvidia_smi_sample()

        if sample is not None:
            samples.append(sample)

        time.sleep(0.5)


def read_nvidia_smi_sample():
    cmd = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,power.draw",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except Exception:
        return None

    line = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in line.split(",")]

    if len(parts) < 3:
        return None

    return {
        "gpu_util_percent": parse_float(parts[0]),
        "memory_used_mb": parse_float(parts[1]),
        "power_draw_w": parse_float(parts[2]),
    }


def print_nvidia_summary(samples):
    if not samples:
        print("  No nvidia-smi samples collected.")
        return

    max_util = max(sample["gpu_util_percent"] for sample in samples)
    max_mem = max(sample["memory_used_mb"] for sample in samples)
    max_power = max(sample["power_draw_w"] for sample in samples)

    avg_util = sum(sample["gpu_util_percent"] for sample in samples) / len(samples)
    avg_power = sum(sample["power_draw_w"] for sample in samples) / len(samples)

    print(f"  samples:       {len(samples)}")
    print(f"  max util:      {max_util:.1f}%")
    print(f"  avg util:      {avg_util:.1f}%")
    print(f"  max memory:    {max_mem:.1f} MiB")
    print(f"  max power:     {max_power:.1f} W")
    print(f"  avg power:     {avg_power:.1f} W")


def make_verdict(webgl_info, gpu_info, samples):
    text_parts = []

    webgl_text = json.dumps(webgl_info).lower()
    cdp_text = json.dumps(gpu_info).lower()

    nvidia_in_webgl = "nvidia" in webgl_text or "geforce" in webgl_text or "rtx" in webgl_text
    nvidia_in_cdp = "nvidia" in cdp_text or "geforce" in cdp_text or "rtx" in cdp_text

    max_util = 0
    max_mem = 0
    max_power = 0

    if samples:
        max_util = max(sample["gpu_util_percent"] for sample in samples)
        max_mem = max(sample["memory_used_mb"] for sample in samples)
        max_power = max(sample["power_draw_w"] for sample in samples)

    if nvidia_in_webgl:
        text_parts.append("✅ WebGL renderer says NVIDIA/GeForce/RTX.")
    else:
        text_parts.append("❌ WebGL renderer does not clearly say NVIDIA.")

    if nvidia_in_cdp:
        text_parts.append("✅ Chrome CDP GPU info mentions NVIDIA/GeForce/RTX.")
    else:
        text_parts.append("❌ Chrome CDP GPU info does not clearly mention NVIDIA.")

    if max_util >= 5:
        text_parts.append(f"✅ nvidia-smi showed GPU work: max util {max_util:.1f}%.")
    else:
        text_parts.append(
            f"⚠️ nvidia-smi max util was only {max_util:.1f}%. "
            "This can still be okay if WebGL renderer says NVIDIA, "
            "but it means the stress did not visibly load the card."
        )

    if max_mem >= 100:
        text_parts.append(f"✅ NVIDIA memory usage reached {max_mem:.1f} MiB.")
    else:
        text_parts.append(f"⚠️ NVIDIA memory usage only reached {max_mem:.1f} MiB.")

    if max_power >= 30:
        text_parts.append(f"✅ NVIDIA power draw reached {max_power:.1f} W.")
    else:
        text_parts.append(f"⚠️ NVIDIA power draw only reached {max_power:.1f} W.")

    if nvidia_in_webgl or nvidia_in_cdp:
        text_parts.append("Overall: this config likely uses the NVIDIA GPU.")
    else:
        text_parts.append("Overall: this config likely does NOT use the NVIDIA GPU.")

    return "\n".join(text_parts)


def print_browser_processes(label):
    print(f"Browser process check: {label}")

    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except Exception as exc:
        print(f"  Could not run nvidia-smi: {exc}")
        return

    process_lines = []
    recording = False

    for line in result.stdout.splitlines():
        if "Processes:" in line:
            recording = True

        if recording:
            process_lines.append(line)

    if process_lines:
        for line in process_lines[-20:]:
            print("  " + line)
    else:
        print("  No process section found in nvidia-smi output.")


def ensure_nvidia_smi_available():
    try:
        subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except Exception as exc:
        raise RuntimeError(
            "nvidia-smi is not available or failed. "
            "Install/check NVIDIA driver first."
        ) from exc


def parse_float(text):
    match = re.search(r"-?\\d+(?:\\.\\d+)?", text)

    if not match:
        return 0.0

    return float(match.group(0))


def print_json(data):
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()