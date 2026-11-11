import math

import pytest

from masai.core.regions import (
    MosaicPlan,
    Region,
    aspects_differ,
    block_fraction_from_pixels,
    block_pixels,
    region_from_pixels,
    region_to_pixels,
)


def test_roundtrip_within_one_pixel():
    width, height = 1920, 1080
    region = region_from_pixels(101, 57, 640, 900, width, height)
    rect = region_to_pixels(region, width, height)
    assert rect is not None
    assert rect[0] == pytest.approx(101, abs=1)
    assert rect[1] == pytest.approx(57, abs=1)
    assert rect[2] == pytest.approx(640, abs=1)
    assert rect[3] == pytest.approx(900, abs=1)


def test_normalized_values_stay_in_range():
    region = region_from_pixels(10, 10, 20, 20, 100, 100)
    assert 0 <= region.x <= 1 and 0 <= region.y <= 1
    assert region.x + region.w <= 1.0 + 1e-9


def test_out_of_bounds_is_clamped():
    region = region_from_pixels(-50, -50, 400, 500, 300, 200)
    rect = region_to_pixels(region, 300, 200)
    assert rect == (0, 0, 300, 200)


def test_reversed_drag_direction_is_normalized():
    forward = region_from_pixels(10, 20, 110, 220, 200, 400)
    backward = region_from_pixels(110, 220, 10, 20, 200, 400)
    assert forward == backward


def test_empty_region_returns_none():
    assert region_to_pixels(Region(0.5, 0.5, 0.0, 0.0), 100, 100) is None


def test_block_scales_with_width():
    fraction = block_fraction_from_pixels(16, 800)
    assert block_pixels(fraction, 800) == 16
    assert block_pixels(fraction, 1600) == 32
    assert block_pixels(fraction, 400) == 8


def test_block_has_minimum_size():
    fraction = block_fraction_from_pixels(2, 4000)
    assert block_pixels(fraction, 100) >= 2


def test_aspect_mismatch_detection():
    assert not aspects_differ((1920, 1080), (1280, 720))
    assert aspects_differ((1920, 1080), (1080, 1920))
    assert aspects_differ((1920, 1080), (1920, 900))


def test_plan_rects_and_block():
    plan = MosaicPlan([Region(0.1, 0.1, 0.2, 0.2)], block_fraction=0.05)
    rects = plan.rects_for(200, 100)
    assert rects == [(20, 10, 60, 30)]
    assert plan.block_for(200) == 10
    assert not plan.is_empty()


def test_plan_is_empty_without_regions():
    assert MosaicPlan([]).is_empty()
    assert MosaicPlan([Region(0.3, 0.3, 0.0, 0.0)]).is_empty()