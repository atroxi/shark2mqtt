"""Decode the route the robot drove, from its uploaded floor-map file.

After each clean the robot uploads ``Visual_Floor_1`` / ``Persistent_Floor_1``
(a protobuf: floor grid, room outlines and run data). Reverse-engineered on an
RV2820ZEUS, so everything here is best-effort and returns None on surprises:

* field 10: ``{1: float scale, 3: packed int16 triples (x, y, heading)}``;
  x/y are scale-sized steps in metres in the robot's map frame.
* field 11: run summary (1 = start epoch, 2 = minutes, 3 = cleaned area in
  0.01 m^2 -- a 0.3 m swath along the route reproduces it within ~5%).
* field 7: three floats, the final pose.
"""

from __future__ import annotations

import struct
from typing import Any, NamedTuple

from .map_render import _pb_fields


class RunPath(NamedTuple):
    points: list[tuple[float, float]]  # metres, robot map frame
    start_ts: int | None
    minutes: int | None
    area_m2: float | None = None  # summary field 3, in 0.01 m^2 (checked against the route)
    rooms: tuple[str, ...] = ()  # rooms requested for the run (not in the file)
    mode: str = ""  # "Vacuum", "Mop" or "Vacuum + mop" (not in the file)


def _float(b: Any) -> float | None:
    if isinstance(b, bytes) and len(b) == 4:
        return struct.unpack("<f", b)[0]
    return None


def parse_run_file(body: bytes) -> RunPath | None:
    """Return the driven route (in metres), or None if the file is unusable."""
    try:
        top = _pb_fields(body)
        raw = next(v for f, v in top if f == 10 and isinstance(v, bytes))
        sub = _pb_fields(raw)
        scale = _float(next(v for f, v in sub if f == 1))
        data = next(v for f, v in sub if f == 3 and isinstance(v, bytes))
        if not scale or not 0 < scale < 0.1:
            return None
        points = [
            (x * scale, y * scale)
            for x, y, _ in struct.iter_unpack("<hhh", data[: len(data) // 6 * 6])
        ]
    except (StopIteration, ValueError, IndexError, struct.error):
        return None
    if len(points) < 2:
        return None

    start_ts = minutes = area = None
    try:
        summary = next(v for f, v in top if f == 11 and isinstance(v, bytes))
        fields = {f: v for f, v in _pb_fields(summary) if isinstance(v, int)}
        start_ts, minutes = fields.get(1), fields.get(2)
        if isinstance(fields.get(3), int):
            area = fields[3] / 100
    except (StopIteration, ValueError, IndexError):
        pass
    return RunPath(points, start_ts, minutes, area)


def mode_label(clean_type: str, wet: bool | None = None, dry: bool | None = None) -> str:
    """Human label for how a run cleaned: Vacuum, Mop or Vacuum + mop.

    ``wet``/``dry`` come from the shadow's CleaningParameters when present;
    otherwise the AreasToClean ``cleantype`` ("dry"/"wet") decides.
    """
    if wet and dry:
        return "Vacuum + mop"
    if wet:
        return "Mop"
    if dry:
        return "Vacuum"
    kind = (clean_type or "").lower()
    if kind == "wet":
        return "Mop"
    if kind == "dry":
        return "Vacuum"
    return kind.capitalize()
