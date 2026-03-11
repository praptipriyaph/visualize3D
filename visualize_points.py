#!/usr/bin/env python3
"""Serve an interactive 3D point viewer in the browser."""

from __future__ import annotations

import argparse
import json
import socketserver
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Iterable, Sequence


Point3D = tuple[float, float, float]


def parse_inline_points(raw_points: str) -> list[Point3D]:
    """Parse points from a JSON string like [[1, 2, 3], [4, 5, 6]]."""
    try:
        data = json.loads(raw_points)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            "Inline points must be valid JSON, for example: "
            '\'[[0, 0, 0], [1.5, 2, 3]]\''
        ) from exc

    return normalize_points(data)


def parse_points_file(file_path: str) -> list[Point3D]:
    """Load points from a JSON file containing [[x, y, z], ...]."""
    path = Path(file_path)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Points file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            f"Could not parse JSON from {path}: {exc}"
        ) from exc

    return normalize_points(data)


def normalize_points(data: object) -> list[Point3D]:
    """Validate and convert an iterable of 3D coordinates."""
    if not isinstance(data, Iterable) or isinstance(data, (str, bytes)):
        raise argparse.ArgumentTypeError(
            "Points must be an iterable of [x, y, z] coordinates."
        )

    points: list[Point3D] = []
    for index, item in enumerate(data):
        if not isinstance(item, Sequence) or len(item) != 3:
            raise argparse.ArgumentTypeError(
                f"Point at index {index} must contain exactly 3 values."
            )

        try:
            x, y, z = (float(item[0]), float(item[1]), float(item[2]))
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(
                f"Point at index {index} must contain numeric values."
            ) from exc

        points.append((x, y, z))

    if not points:
        raise argparse.ArgumentTypeError("At least one 3D point is required.")

    return points


def build_html(points: Sequence[Point3D], point_size: float, color: str) -> str:
    points_json = json.dumps(points)
    point_radius = max(2.0, point_size / 10.0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>3D Point Visualizer</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #020617;
      --panel: rgba(15, 23, 42, 0.88);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      overflow: hidden;
      background:
        radial-gradient(circle at top, rgba(56, 189, 248, 0.18), transparent 30%),
        linear-gradient(180deg, #020617, #0f172a);
      color: var(--text);
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    }}

    #canvas {{
      display: block;
      width: 100vw;
      height: 100vh;
      cursor: grab;
    }}

    #canvas.dragging {{
      cursor: grabbing;
    }}

    .hud {{
      position: fixed;
      top: 18px;
      left: 18px;
      padding: 12px 14px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 14px;
      background: var(--panel);
      backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.28);
    }}

    .hud strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 14px;
    }}

    .hud span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }}
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>
  <div class="hud">
    <strong>3D Point Visualizer</strong>
    <span>Drag to rotate</span>
    <span>Mouse wheel or trackpad to zoom</span>
    <span>{len(points)} points loaded</span>
  </div>
  <script>
    const rawPoints = {points_json};
    const pointColor = {json.dumps(color)};
    const pointRadius = {point_radius};

    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");

    const state = {{
      angleX: -0.55,
      angleY: 0.75,
      zoom: 1,
      dragging: false,
      lastX: 0,
      lastY: 0,
      cameraDistance: 7,
      normalizedPoints: []
    }};

    function resizeCanvas() {{
      canvas.width = window.innerWidth * window.devicePixelRatio;
      canvas.height = window.innerHeight * window.devicePixelRatio;
      canvas.style.width = window.innerWidth + "px";
      canvas.style.height = window.innerHeight + "px";
      ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      draw();
    }}

    function normalizePoints(points) {{
      let minX = Infinity, minY = Infinity, minZ = Infinity;
      let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

      for (const [x, y, z] of points) {{
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        minZ = Math.min(minZ, z);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        maxZ = Math.max(maxZ, z);
      }}

      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const centerZ = (minZ + maxZ) / 2;
      const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1);

      return points.map(([x, y, z]) => [
        ((x - centerX) / span) * 4,
        ((y - centerY) / span) * 4,
        ((z - centerZ) / span) * 4
      ]);
    }}

    function rotatePoint([x, y, z]) {{
      const cosY = Math.cos(state.angleY);
      const sinY = Math.sin(state.angleY);
      const x1 = x * cosY + z * sinY;
      const z1 = -x * sinY + z * cosY;

      const cosX = Math.cos(state.angleX);
      const sinX = Math.sin(state.angleX);
      const y2 = y * cosX - z1 * sinX;
      const z2 = y * sinX + z1 * cosX;

      return [x1, y2, z2];
    }}

    function projectPoint(point) {{
      const [x, y, z] = rotatePoint(point);
      const depth = z + state.cameraDistance;
      const scale = 240 * state.zoom / depth;
      return {{
        x: window.innerWidth / 2 + x * scale,
        y: window.innerHeight / 2 - y * scale,
        depth,
        scale
      }};
    }}

    function drawAxis(start, end, color, label) {{
      const p1 = projectPoint(start);
      const p2 = projectPoint(end);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      ctx.fillStyle = color;
      ctx.font = "bold 13px Segoe UI";
      ctx.fillText(label, p2.x + 6, p2.y - 6);
    }}

    function draw() {{
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      drawAxis([-2.4, 0, 0], [2.4, 0, 0], "#ef4444", "X");
      drawAxis([0, -2.4, 0], [0, 2.4, 0], "#22c55e", "Y");
      drawAxis([0, 0, -2.4], [0, 0, 2.4], "#3b82f6", "Z");

      const projected = state.normalizedPoints
        .map((point) => projectPoint(point))
        .sort((a, b) => b.depth - a.depth);

      for (const point of projected) {{
        const radius = Math.max(2, pointRadius * state.zoom / point.depth);
        ctx.beginPath();
        ctx.fillStyle = pointColor;
        ctx.shadowColor = "rgba(56, 189, 248, 0.25)";
        ctx.shadowBlur = 18;
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fill();
      }}

      ctx.shadowBlur = 0;
    }}

    canvas.addEventListener("mousedown", (event) => {{
      state.dragging = true;
      state.lastX = event.clientX;
      state.lastY = event.clientY;
      canvas.classList.add("dragging");
    }});

    window.addEventListener("mouseup", () => {{
      state.dragging = false;
      canvas.classList.remove("dragging");
    }});

    window.addEventListener("mousemove", (event) => {{
      if (!state.dragging) return;
      const dx = event.clientX - state.lastX;
      const dy = event.clientY - state.lastY;
      state.lastX = event.clientX;
      state.lastY = event.clientY;
      state.angleY += dx * 0.01;
      state.angleX += dy * 0.01;
      draw();
    }});

    canvas.addEventListener("wheel", (event) => {{
      event.preventDefault();
      state.zoom *= event.deltaY < 0 ? 1.1 : 0.9;
      state.zoom = Math.max(0.3, Math.min(5, state.zoom));
      draw();
    }}, {{ passive: false }});

    state.normalizedPoints = normalizePoints(rawPoints);
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
  </script>
</body>
</html>
"""


def visualize_points(
    points: Sequence[Point3D],
    point_size: float,
    color: str,
    host: str,
    port: int,
    open_browser: bool,
    output: str | None,
) -> None:
    html_text = build_html(points, point_size=point_size, color=color)

    if output is not None:
        output_path = Path(output).resolve()
        output_path.write_text(html_text, encoding="utf-8")
        print(f"Viewer written to {output_path}")
        if open_browser:
            webbrowser.open(output_path.as_uri())
        return

    html = html_text.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, format: str, *args: object) -> None:
            return

    with socketserver.TCPServer((host, port), Handler) as server:
        actual_port = server.server_address[1]
        url = f"http://{host}:{actual_port}"
        print(f"Viewer running at {url}")
        print("Press Ctrl+C to stop the server.")

        if open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Visualize 3D points in a browser and rotate the view by dragging."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--points",
        type=parse_inline_points,
        help='Inline JSON points, e.g. \'[[0, 0, 0], [1, 2, 3]]\'',
    )
    source.add_argument(
        "--file",
        type=parse_points_file,
        help="Path to a JSON file containing points like [[x, y, z], ...]",
    )
    parser.add_argument(
        "--point-size",
        type=float,
        default=40,
        help="Rendered point size. Default: 40",
    )
    parser.add_argument(
        "--color",
        default="#f8fafc",
        help="Point color. Default: #f8fafc",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the local server to. Default: 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the local server. Use 0 for an automatic port. Default: 8000",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the browser.",
    )
    parser.add_argument(
        "--output",
        help="Write a standalone HTML viewer to this file instead of starting a server.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    points = args.points if args.points is not None else args.file
    visualize_points(
        points,
        point_size=args.point_size,
        color=args.color,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        output=args.output,
    )


if __name__ == "__main__":
    main()
