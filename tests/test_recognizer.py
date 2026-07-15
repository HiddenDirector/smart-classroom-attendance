"""Two-pass long-range recognition: merge, dedupe, tick scheduling.

The detection passes are stubbed out (no real faces needed) — these tests
pin down the orchestration logic: when the long-range pass runs and how its
results merge with the near pass.
"""
from __future__ import annotations
import numpy as np
import pytest

pytest.importorskip("face_recognition")

from app.face_engine.recognizer import FaceRecognizer, _center_inside

FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)
ENC = np.zeros(128)

# Full-frame boxes: (top, right, bottom, left)
NEAR_BOX = (100, 400, 300, 200)          # big face close to the camera
FAR_BOX = (150, 860, 200, 810)           # small face far away
NEAR_DUP_BOX = (110, 390, 290, 210)      # same face as NEAR_BOX, re-detected


def _stub_passes(recognizer, near: list, far: list):
    """Replace _detect: returns `near` for the fast pass, `far` otherwise."""
    def fake_detect(frame, scale, upsample):
        return list(near) if scale == recognizer.detection_scale else list(far)
    recognizer._detect = fake_detect


def test_center_inside():
    assert _center_inside(NEAR_DUP_BOX, NEAR_BOX)
    assert not _center_inside(FAR_BOX, NEAR_BOX)


def test_long_range_runs_when_near_pass_empty():
    rec = FaceRecognizer(long_range=True, long_range_interval=99)
    _stub_passes(rec, near=[], far=[(FAR_BOX, ENC)])
    results = rec.recognize(FRAME)
    assert len(results) == 1
    assert results[0].box == FAR_BOX  # far face found via fallback pass


def test_mixed_distance_merge_on_interval_tick():
    # interval=1 -> long-range pass runs every tick alongside the near pass.
    rec = FaceRecognizer(long_range=True, long_range_interval=1)
    _stub_passes(rec, near=[(NEAR_BOX, ENC)],
                 far=[(NEAR_DUP_BOX, ENC), (FAR_BOX, ENC)])
    results = rec.recognize(FRAME)
    boxes = [r.box for r in results]
    assert NEAR_BOX in boxes and FAR_BOX in boxes
    assert NEAR_DUP_BOX not in boxes      # duplicate of the near face dropped
    assert len(results) == 2              # one entry per real person


def test_long_range_respects_interval():
    # interval=2 with a near face present: pass 2 runs on ticks 2, 4, ...
    rec = FaceRecognizer(long_range=True, long_range_interval=2)
    _stub_passes(rec, near=[(NEAR_BOX, ENC)], far=[(FAR_BOX, ENC)])
    first = rec.recognize(FRAME)   # tick 1: near only
    second = rec.recognize(FRAME)  # tick 2: near + long-range merged
    assert len(first) == 1
    assert len(second) == 2


def test_long_range_disabled():
    rec = FaceRecognizer(long_range=False)
    _stub_passes(rec, near=[], far=[(FAR_BOX, ENC)])
    assert rec.recognize(FRAME) == []


def test_multiple_people_all_reported():
    boxes = [((i * 100, i * 100 + 60, i * 100 + 60, i * 100), ENC) for i in range(4)]
    rec = FaceRecognizer(long_range=False)
    _stub_passes(rec, near=boxes, far=[])
    results = rec.recognize(FRAME)
    assert len(results) == 4              # a group is processed in one frame
    assert all(not r.is_match for r in results)  # no known encodings loaded
