"""Render a Shark MARD / Mobile_App_Room_Definition file as an SVG floor plan.

Dependency-free on purpose (the image already carries enough). Usage:

    python -m src.map_render room_definition.json map.svg [--rotate DEG]

The input is the JSON body of Mobile_App_Room_Definition (or the MARD): a dict
with an "areas" list whose entries carry "area_meta_data" ("UserRoom:..." or
"UserNoGo:..."), "user_room_name" and a "points" outline of {"x", "y"} vertices.
"""

from __future__ import annotations

import base64
import html
import json
import math
import struct
import sys
import zlib
from typing import Any

# Colour-blind-friendly, muted fills so labels stay readable.
_PALETTE = [
    "#8ecae6", "#ffb703", "#a8dadc", "#e9c46a", "#b7e4c7",
    "#f4a261", "#cdb4db", "#ffafcc", "#bde0fe", "#d4e09b",
    "#fcd5ce", "#c7b9ff",
]


# --- Occupancy grid (mapStatePbFloorBase64String) ---------------------------
# The MARD embeds a protobuf with a one-byte-per-cell occupancy grid. Field
# numbers below were worked out from an RV2820ZEUS map, so everything here is
# best-effort and returns None on any surprise. Room "points" are in the same
# cell coordinates, so the grid can sit directly under the room outlines.


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        c = buf[i]
        i += 1
        result |= (c & 0x7F) << shift
        shift += 7
        if c < 0x80:
            return result, i


def _pb_fields(buf: bytes) -> list[tuple[int, bytes | int]]:
    out: list[tuple[int, bytes | int]] = []
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(buf, i)
            out.append((field, val))
        elif wire == 2:
            ln, i = _varint(buf, i)
            out.append((field, buf[i:i + ln]))
            i += ln
        elif wire == 5:
            out.append((field, buf[i:i + 4]))
            i += 4
        elif wire == 1:
            out.append((field, buf[i:i + 8]))
            i += 8
        else:
            break
    return out


def parse_grid(data: dict[str, Any]) -> tuple[int, int, bytes] | None:
    """Return (width, height, cells) from the embedded occupancy grid, or None."""
    b64 = data.get("mapStatePbFloorBase64String")
    if not isinstance(b64, str) or not b64:
        return None
    try:
        top = _pb_fields(base64.b64decode(b64))
        layer = next(v for f, v in top if f == 5 and isinstance(v, bytes))
        sub = _pb_fields(layer)
        width = next(v for f, v in sub if f == 3 and isinstance(v, int))
        height = next(v for f, v in sub if f == 4 and isinstance(v, int))
        cells = next(v for f, v in sub if f == 6 and isinstance(v, bytes))
    except (StopIteration, ValueError, IndexError):
        return None
    if width <= 0 or height <= 0 or len(cells) != width * height:
        return None
    return width, height, cells


def _png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(tag + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", crc)

    raw = b"".join(
        b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def grid_png(width: int, height: int, cells: bytes) -> bytes:
    """Colour the grid: 75 unknown (transparent), <=15 free floor, >=80 wall."""
    free = bytes((0x2E, 0x34, 0x45, 0xFF))
    wall = bytes((0xA7, 0xB0, 0xC4, 0xFF))
    none = bytes((0, 0, 0, 0))
    lut = {}
    for v in range(256):
        lut[v] = free if v <= 20 else (wall if v >= 80 and v != 75 else none)
    return _png_rgba(width, height, b"".join(lut[c] for c in cells))


def _outline(area: dict[str, Any]) -> list[tuple[float, float]]:
    pts = area.get("points") or []
    out: list[tuple[float, float]] = []
    for p in pts:
        try:
            out.append((float(p["x"]), float(p["y"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _centroid(poly: list[tuple[float, float]]) -> tuple[float, float]:
    """Area centroid of a polygon; falls back to the bbox centre if degenerate."""
    a = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    if abs(a) < 1e-9:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return cx / (3 * a), cy / (3 * a)


def _rotate(
    pt: tuple[float, float], deg: float,
) -> tuple[float, float]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c


def render_svg(
    data: dict[str, Any],
    *,
    width: int = 800,
    rotate: float | None = None,
    flip_x: bool = True,
    with_grid: bool = False,
    iso: bool = True,
    yaw: float = 28.0,
    pitch: float = 0.6,
    margin: int = 20,
    highlight: set[str] | None = None,
) -> str:
    """Return an SVG string for the map.

    iso: draw angled, extruded 3D rooms (default); False gives the flat plan.
    yaw/pitch: iso view rotation in degrees and vertical squash (0-1).
    with_grid: also draw the occupancy grid (walls/obstacles) under the rooms.
    flip_x: mirror left-right (on by default; pass --no-flip-x on the CLI to disable).
    rotate: degrees; defaults to data["map_rotation"] when present and numeric.
    highlight: user room names to draw in a stronger colour (e.g. active rooms).
    """
    if rotate is None:
        mr = data.get("map_rotation")
        rotate = float(mr) if isinstance(mr, (int, float)) else 0.0
    highlight = highlight or set()
    if iso:
        return _render_iso(
            data, width=width, rotate=rotate, flip_x=flip_x, yaw=yaw,
            pitch=pitch, margin=margin, highlight=highlight,
        )

    shapes: list[tuple[str, str, list[tuple[float, float]]]] = []
    for area in data.get("areas", []):
        if not isinstance(area, dict):
            continue
        meta = str(area.get("area_meta_data", ""))
        poly = _outline(area)
        if len(poly) < 3:
            continue
        # Shark map coordinates are y-up; SVG is y-down, so mirror vertically.
        # flip_x matches the Shark app's orientation on the RV2820 maps seen so far.
        poly = [(-x if flip_x else x, -y) for x, y in poly]
        if rotate:
            poly = [_rotate(p, rotate) for p in poly]
        kind = meta.split(":", 1)[0]
        name = str(area.get("user_room_name") or area.get("robot_room_name") or "")
        shapes.append((kind, name, poly))

    if not shapes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
            '<text x="10" y="35" font-size="14">No map data</text></svg>'
        )

    xs = [p[0] for _, _, poly in shapes for p in poly]
    ys = [p[1] for _, _, poly in shapes for p in poly]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)
    scale = (width - 2 * margin) / span_x
    height = int(span_y * scale + 2 * margin)

    def tx(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] - minx) * scale + margin, (p[1] - miny) * scale + margin

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><pattern id="nogo" width="8" height="8" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="8" height="8" fill="#ffffff" fill-opacity="0.0"/>'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#d62828" stroke-width="3"/>'
        "</pattern></defs>",
        f'<rect width="{width}" height="{height}" fill="#1f2430"/>',
    ]

    grid = parse_grid(data) if (with_grid and not rotate) else None
    if grid is not None:
        gw, gh, cells = grid
        uri = "data:image/png;base64," + base64.b64encode(grid_png(gw, gh, cells)).decode()
        # Cell (x, y) maps exactly like a polygon vertex (x, y), so one affine
        # transform places the whole grid: X = sx*x + ex, Y = -scale*y + fy.
        sx = -scale if flip_x else scale
        ex = margin - minx * scale
        fy = margin - miny * scale
        out.append(f'<g transform="matrix({sx:.5f} 0 0 {-scale:.5f} {ex:.2f} {fy:.2f})">')
        out.append(
            f'<image href="{uri}" x="0" y="0" width="{gw}" height="{gh}" '
            'image-rendering="pixelated" opacity="0.9"/></g>'
        )

    room_i = 0
    labels: list[tuple[float, float, str]] = []
    for kind, name, poly in shapes:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(tx, poly))
        if kind == "UserNoGo":
            out.append(
                f'<polygon points="{pts}" fill="url(#nogo)" stroke="#d62828" '
                'stroke-width="2" fill-opacity="0.9"/>'
            )
            continue
        fill = _PALETTE[room_i % len(_PALETTE)]
        room_i += 1
        active = name in highlight
        stroke = "#ff9800" if active else "#2b2d42"
        sw = 4 if active else 2
        out.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round"/>'
        )
        cx, cy = tx(_centroid(poly))
        labels.append((cx, cy, name))

    font = max(11, min(18, int(width / 45)))
    for cx, cy, name in labels:
        out.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="sans-serif" '
            f'font-size="{font}" font-weight="600" fill="#1f2430" '
            f'text-anchor="middle" dominant-baseline="middle" stroke="#ffffff" '
            f'stroke-width="3" stroke-opacity="0.85" paint-order="stroke">'
            f"{html.escape(name)}</text>"
        )
    out.append("</svg>")
    return "\n".join(out)


# --- Angled, extruded ("subtle 3D") renderer --------------------------------


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    """Blend hex_a toward hex_b by t (0..1)."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _render_iso(
    data: dict[str, Any],
    *,
    width: int,
    rotate: float,
    flip_x: bool,
    yaw: float,
    pitch: float,
    margin: int,
    highlight: set[str],
) -> str:
    rooms: list[tuple[str, list[tuple[float, float]]]] = []
    nogos: list[list[tuple[float, float]]] = []
    for area in data.get("areas", []):
        if not isinstance(area, dict):
            continue
        poly = _outline(area)
        if len(poly) < 3:
            continue
        # Same orientation fixes as the flat plan: y-up data, app-style mirror.
        poly = [(-x if flip_x else x, -y) for x, y in poly]
        if rotate:
            poly = [_rotate(p, rotate) for p in poly]
        # Camera: spin the plan by yaw, then squash vertically for tilt.
        poly = [_rotate(p, yaw) for p in poly]
        poly = [(x, y * pitch) for x, y in poly]
        meta = str(area.get("area_meta_data", ""))
        if meta.startswith("UserNoGo"):
            nogos.append(poly)
        else:
            name = str(area.get("user_room_name") or area.get("robot_room_name") or "")
            rooms.append((name, poly))

    if not rooms:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
            '<text x="10" y="35" font-size="14">No map data</text></svg>'
        )

    allpts = [p for _, poly in rooms for p in poly] + [p for poly in nogos for p in poly]
    minx = min(p[0] for p in allpts)
    maxx = max(p[0] for p in allpts)
    miny = min(p[1] for p in allpts)
    maxy = max(p[1] for p in allpts)
    scale = (width - 2 * margin) / max(maxx - minx, 1e-6)

    h_low = width * 0.026
    h_high = width * 0.062
    any_active = any(name in highlight for name, _ in rooms)
    top_room = h_high if any_active else h_low
    # Headroom for the tallest extrusion on top, a little for shadows below.
    top_pad = margin + top_room
    height = int((maxy - miny) * scale + top_pad + margin + h_low)

    def tx(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] - minx) * scale + margin, (p[1] - miny) * scale + top_pad

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<defs>'
        '<filter id="glow" x="-30%" y="-30%" width="160%" height="160%">'
        '<feGaussianBlur stdDeviation="7"/></filter>'
        '<pattern id="nogo" width="8" height="8" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" '
        'stroke="#d62828" stroke-width="3"/></pattern></defs>',
        f'<rect width="{width}" height="{height}" fill="#1f2430"/>',
    ]

    for poly in nogos:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(tx, poly))
        out.append(
            f'<polygon points="{pts}" fill="url(#nogo)" stroke="#d62828" stroke-width="2"/>'
        )

    # Back-to-front by the room's ground-plane centroid.
    placed = []
    for i, (name, poly) in enumerate(rooms):
        screen = [tx(p) for p in poly]
        cx, cy = _centroid(screen)
        placed.append((cy, i, name, screen, (cx, cy)))
    placed.sort()

    labels: list[tuple[float, float, str, bool]] = []
    for _, i, name, screen, (cx, cy) in placed:
        active = name in highlight
        base = _PALETTE[i % len(_PALETTE)]
        if any_active and not active:
            base = _mix(base, "#5c6370", 0.55)  # recede
        h = h_high if active else h_low
        top = _mix(base, "#ffffff", 0.0)
        if active:
            top = _mix("#ff9800", "#ffffff", 0.18)
        side = _mix(top, "#10131a", 0.42)
        stroke = "#ffd9a0" if active else _mix(top, "#10131a", 0.35)

        # Soft ground shadow, offset away from the "light".
        sh = " ".join(f"{x + h * 0.45:.1f},{y + h * 0.3:.1f}" for x, y in screen)
        out.append(f'<polygon points="{sh}" fill="#000" fill-opacity="0.28"/>')

        area_sign = 0.0
        n = len(screen)
        for k in range(n):
            x0, y0 = screen[k]
            x1, y1 = screen[(k + 1) % n]
            area_sign += x0 * y1 - x1 * y0

        edges = []
        for k in range(n):
            x0, y0 = screen[k]
            x1, y1 = screen[(k + 1) % n]
            dx, dy = x1 - x0, y1 - y0
            ny = -dx if area_sign > 0 else dx  # outward normal's y component
            if ny > 1e-9:  # faces the viewer
                edges.append(((y0 + y1) / 2, (x0, y0, x1, y1)))
        edges.sort()
        for _, (x0, y0, x1, y1) in edges:
            quad = (
                f"{x0:.1f},{y0:.1f} {x1:.1f},{y1:.1f} "
                f"{x1:.1f},{y1 - h:.1f} {x0:.1f},{y0 - h:.1f}"
            )
            out.append(
                f'<polygon points="{quad}" fill="{side}" stroke="{side}" '
                'stroke-width="0.8" stroke-linejoin="round"/>'
            )

        up = " ".join(f"{x:.1f},{y - h:.1f}" for x, y in screen)
        if active:
            out.append(
                f'<polygon points="{up}" fill="none" stroke="#ff9800" '
                'stroke-width="10" stroke-opacity="0.85" filter="url(#glow)"/>'
            )
        out.append(
            f'<polygon points="{up}" fill="{top}" stroke="{stroke}" '
            f'stroke-width="{2.5 if active else 1.5}" stroke-linejoin="round"/>'
        )
        labels.append((cx, cy - h, name, active))

    font = max(11, min(18, int(width / 45)))
    for cx, cy, name, active in labels:
        out.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="sans-serif" '
            f'font-size="{font}" font-weight="700" fill="#1f2430" '
            'text-anchor="middle" dominant-baseline="middle" stroke="#ffffff" '
            f'stroke-width="3" stroke-opacity="0.85" paint-order="stroke">'
            f"{html.escape(name)}</text>"
        )
    out.append("</svg>")
    return "\n".join(out)


def render_bytes(body: bytes, **kw: Any) -> str:
    return render_svg(json.loads(body.decode("utf-8")), **kw)


def main(argv: list[str]) -> int:
    flip_x = "--no-flip-x" not in argv
    with_grid = "--grid" in argv
    flat = "--flat" in argv
    active: set[str] = set()
    for i, a in enumerate(argv):
        if a == "--highlight" and i + 1 < len(argv):
            active = {n for n in argv[i + 1].split(",") if n}
    args = [a for a in argv if not a.startswith("--")]
    rotate = None
    for i, a in enumerate(argv):
        if a == "--rotate" and i + 1 < len(argv):
            rotate = float(argv[i + 1])
            args = [x for x in args if x != argv[i + 1]]
        if a == "--highlight" and i + 1 < len(argv):
            args = [x for x in args if x != argv[i + 1]]
    if len(args) != 2:
        print("usage: python -m src.map_render in.json out.svg [--rotate DEG] [--no-flip-x] [--grid] [--flat] [--highlight 'Kitchen,Office']")
        return 2
    with open(args[0], "rb") as fh:
        svg = render_bytes(fh.read(), rotate=rotate, flip_x=flip_x, with_grid=with_grid,
            iso=not flat, highlight=active)
    with open(args[1], "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
