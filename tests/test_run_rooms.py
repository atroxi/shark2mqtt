"""Which rooms get attached to a decoded run."""

from types import SimpleNamespace

import pytest

from src import main
from src.run_path import RunPath

START = 1_795_385_600  # run start (epoch seconds)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MARD_DUMP_DIR", str(tmp_path))
    main._outings.clear()
    yield
    main._outings.clear()


def _run(minutes=15):
    return RunPath([(0.0, 0.0), (1.0, 1.0)], START, minutes)


def _outing(first_seen, rooms):
    main._outings["DSN1"] = {
        "first_seen": first_seen, "closed": True, "rooms": rooms, "mode": "Vacuum",
    }


DEVICE = SimpleNamespace(dsn="DSN1")


def test_outing_during_run_is_attached():
    _outing(START + 20, ["Kitchen"])
    run = main._attach_run_info(DEVICE, _run())
    assert run.rooms == ("Kitchen",)


def test_outing_from_a_later_clean_is_not_attached():
    # shark2mqtt restarted 50 min after this 15-min run, mid-way through a
    # different clean: those rooms must not be pinned on the old run.
    _outing(START + 50 * 60, ["Guest Bedroom", "Hallway"])
    run = main._attach_run_info(DEVICE, _run())
    assert run.rooms == ()


def test_later_outing_falls_back_to_saved_rooms():
    _outing(START + 20, ["Kitchen"])
    main._attach_run_info(DEVICE, _run())  # saves Kitchen for this start time
    _outing(START + 50 * 60, ["Guest Bedroom", "Hallway"])
    run = main._attach_run_info(DEVICE, _run())
    assert run.rooms == ("Kitchen",)
