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
    summary = _field(1, 0, 1794891392) + _field(2, 0, 21) + _field(3, 0, 1520)
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
    assert run.area_m2 == 15.2
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


def test_render_coverage_swath_and_caption():
    mard = _mard()
    svg = render_svg(
        mard, trail=[(-8.0, 0.0), (-7.0, 0.5), (-6.0, 0.0)],
        coverage_swath=0.3, caption="Last clean: 21 min",
    )
    assert svg.count("<polyline") == 3  # swath, then outline + route line on top
    assert "#26c6da" in svg
    assert svg.count("<circle") == 2  # start and end markers
    assert "Last clean: 21 min" in svg


def _viewbox(svg: str) -> list[float]:
    import re

    return [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]


def test_render_coverage_crop_to_trail():
    mard = _mard()
    trail = [(-8.0, 0.0), (-7.0, 0.5), (-6.0, 0.0)]
    full = render_svg(mard, trail=trail, coverage_swath=0.3, caption="x")
    cropped = render_svg(
        mard, trail=trail, coverage_swath=0.3, caption="x", crop_to_trail=True,
    )
    fx, fy, fw, fh = _viewbox(full)
    cx, cy, cw, ch = _viewbox(cropped)
    assert (fx, fy) == (0, 0)
    assert cw < fw  # zoomed in on the route
    assert cw >= fw / 3 - 0.1  # but never more than 3x
    assert 'width="800"' in cropped  # output width unchanged
    # Without a trail, crop_to_trail is a no-op.
    assert render_svg(mard, crop_to_trail=True) == render_svg(mard)


def test_mode_label():
    from src.run_path import mode_label

    assert mode_label("dry", True, True) == "Vacuum + mop"
    assert mode_label("dry", True, False) == "Mop"
    assert mode_label("wet", False, True) == "Vacuum"
    assert mode_label("wet") == "Mop"
    assert mode_label("dry") == "Vacuum"


TRAIL = [(-8.0, 0.0), (-7.0, 0.5), (-6.0, 0.0)]


def test_wasteland_theme_draws_truck_instead_of_end_dot():
    from src.truck_icon import TRUCK_PATHS

    mard = _mard()
    svg = render_svg(mard, trail=TRAIL, theme="wasteland")
    assert svg.count("<circle") == 1  # start marker only
    assert TRUCK_PATHS[0][1] in svg  # the truck silhouette
    assert "#140f0b" in svg  # wasteland background
    default = render_svg(mard, trail=TRAIL)
    assert default.count("<circle") == 2 and TRUCK_PATHS[0][1] not in default


def test_robot_at_places_only_the_truck():
    from src.truck_icon import TRUCK_PATHS

    svg = render_svg(_mard(), robot_at=TRAIL, theme="wasteland")
    assert TRUCK_PATHS[0][1] in svg
    assert "<polyline" not in svg and "<circle" not in svg
    # Default theme has no robot marker, so robot_at changes nothing there.
    assert render_svg(_mard(), robot_at=TRAIL) == render_svg(_mard())


def test_truck_faces_the_direction_of_travel():
    import re

    svg = render_svg(_mard(), robot_at=[(-8.0, 0.0), (-6.0, 0.0)], theme="wasteland")
    back = render_svg(_mard(), robot_at=[(-6.0, 0.0), (-8.0, 0.0)], theme="wasteland")
    turn = lambda s: float(re.search(r"rotate\((-?[\d.]+)\) scale", s).group(1))
    assert abs(((turn(svg) - turn(back)) % 360) - 180) < 1  # opposite headings


def test_unknown_theme_falls_back_to_default():
    assert render_svg(_mard(), trail=TRAIL, theme="nope") == render_svg(_mard(), trail=TRAIL)
