"""Tests for decoding the robot's run route and drawing it on the map."""

import base64
import struct

import pytest

from src.map_render import grid_frame, render_svg, trail_cells
from src.run_path import parse_run_file


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, wire: int, payload: bytes | int) -> bytes:
    key = _varint(num << 3 | wire)
    if wire == 0:
        return key + _varint(payload)  # type: ignore[arg-type]
    if wire == 5:
        return key + payload  # type: ignore[return-value]
    return key + _varint(len(payload)) + payload  # type: ignore[arg-type]


def _run_file(points: list[tuple[int, int]], scale: float = 0.002) -> bytes:
    data = b"".join(struct.pack("<hhh", x, y, 0) for x, y in points)
    path = _field(1, 5, struct.pack("<f", scale)) + _field(3, 2, data)
    summary = _field(1, 0, 1794891392) + _field(2, 0, 21)
    return _field(10, 2, path) + _field(11, 2, summary)


def _mard() -> dict:
    origin = _field(1, 5, struct.pack("<f", -11.55)) + _field(
        2, 5, struct.pack("<f", -2.55),
    )
    layer = (
        _field(1, 5, struct.pack("<f", 0.06))
        + _field(2, 2, origin)
        + _field(3, 0, 257)
    )
    return {
        "mapStatePbFloorBase64String": base64.b64encode(
            _field(5, 2, layer)
        ).decode(),
        "areas": [{
            "area_meta_data": "UserRoom:AZ_1",
            "user_room_name": "Room",
            "points": [
                {"x": 10, "y": 10}, {"x": 100, "y": 10},
                {"x": 100, "y": 100}, {"x": 10, "y": 100},
            ],
        }],
    }


def test_parse_run_file():
    run = parse_run_file(_run_file([(0, 0), (500, -250), (1000, 0)]))
    assert run is not None
    assert run.start_ts == 1794891392 and run.minutes == 21
    assert run.points[1] == pytest.approx((1.0, -0.5), abs=1e-4)


def test_parse_run_file_rejects_junk():
    assert parse_run_file(b"") is None
    assert parse_run_file(b"\x08\x01") is None
    assert parse_run_file(_run_file([(1, 1)])) is None  # too short


def test_trail_cells_mirror_x_and_keep_y():
    mard = _mard()
    res, ox, oy, width = grid_frame(mard)
    assert (round(res, 3), round(ox, 2), round(oy, 2), width) == (0.06, -11.55, -2.55, 257)
    (cx, cy), = trail_cells(mard, [(-11.55 + 0.6, -2.55 + 0.6)])
    assert round(cx) == 257 - 10  # x mirrored across the grid width
    assert round(cy) == 10  # y unchanged


def test_render_draws_trail():
    mard = _mard()
    plain = render_svg(mard)
    with_trail = render_svg(mard, trail=[(-8.0, 0.0), (-7.0, 0.5), (-6.0, 0.0)])
    assert "<polyline" not in plain
    assert with_trail.count("<polyline") == 2  # outline + coloured stroke
    assert with_trail.count("<circle") == 2  # start and end markers
