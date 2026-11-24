"""Tests of the porches `io.video` writes over the resolved mode."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from catalog_support import fresh_platform
from support import check, check_equal, check_in
from video_support import (
    ROLE,
    video_modes,
    video_platform,
    write_video_catalog,
)

from riscv_tools.board_check import check_platform
from riscv_tools.board_schema import (
    PlatformVideo,
    SchemaError,
    parse_video_modes,
    read_platform_video,
)
from riscv_tools.board_video import VideoError, VideoPlan, plan_video


def _plan(**fields: Any) -> VideoPlan:
    """Resolve a request on the 640x480 role of the tests."""
    modes = parse_video_modes(video_modes())
    return plan_video(ROLE, modes, PlatformVideo(**fields))


def _generics(plan: VideoPlan) -> dict[str, str]:
    """Give the generics of the `video` entity, by name."""
    return dict(line.split(" => ") for line in plan.entity_generics())


def test_the_porches_are_read_from_the_platform() -> None:
    """Each porch lands in its field of the request."""
    request = read_platform_video(
        yaml.safe_load("io: {video: {h_front_porch: 0, h_back_porch: 64}}")
    )
    check_equal(request.h_front_porch if request else None, 0)
    check_equal(request.h_back_porch if request else None, 64)
    check_equal(request.v_front_porch if request else None, None)


def test_a_negative_porch_is_a_schema_error() -> None:
    """The porches are not negative."""
    with pytest.raises(SchemaError):
        read_platform_video(yaml.safe_load("io: {video: {h_back_porch: -1}}"))


def test_without_porches_the_mode_is_kept() -> None:
    """The 640x480@60 mode keeps its 16 and 48."""
    generics = _generics(_plan())
    check_equal(generics["h_front_porch"], "16")
    check_equal(generics["h_back_porch"], "48")


def test_the_doom_porches_reach_the_generics() -> None:
    """0 and 64 keep the horizontal total of 800."""
    plan = _plan(h_front_porch=0, h_back_porch=64)
    generics = _generics(plan)
    check_equal(generics["h_front_porch"], "0")
    check_equal(generics["h_back_porch"], "64")
    check_equal(generics["h_sync"], "96")
    check_equal(plan.mode.horizontal.total, 800)
    top = dict(line.split(" => ") for line in plan.generics())
    check_equal(top["video_h_front_porch"], "0")
    check_equal(top["video_h_back_porch"], "64")
    check_equal(top["video_h_total"], "800")


def test_one_porch_makes_the_other_keep_the_total() -> None:
    """The porch not written takes what is left of the total."""
    front = _generics(_plan(h_front_porch=0))
    check_equal(front["h_back_porch"], "64")
    back = _generics(_plan(h_back_porch=64))
    check_equal(back["h_front_porch"], "0")
    vertical = _generics(_plan(v_front_porch=1))
    check_equal(vertical["v_back_porch"], "42")


def test_porches_that_do_not_add_up_are_refused() -> None:
    """A sum that changes the total, or a porch past it, is an error."""
    with pytest.raises(VideoError) as bad:
        _plan(h_front_porch=0, h_back_porch=60)
    check_in("must add up to 64", str(bad.value))
    with pytest.raises(VideoError) as over:
        _plan(h_front_porch=70)
    check_in("h_back_porch -6", str(over.value))


def test_the_check_reports_wrong_porches(tmp_path: Path) -> None:
    """`board check` takes 0/64 and refuses a different sum."""
    write_video_catalog(tmp_path)
    ok = video_platform(fb_width=320, fb_height=200)
    ok["io"]["video"].update({"h_front_porch": 0, "h_back_porch": 64})
    check_equal([f"{f.rule} {f}" for f in check_platform(ok, tmp_path)], [])
    bad = video_platform(fb_width=320, fb_height=200)
    bad["io"]["video"].update({"h_front_porch": 0, "h_back_porch": 10})
    found = [f"{f.rule} {f}" for f in check_platform(bad, tmp_path)]
    check(any("porch" in line for line in found), str(found))


def test_a_platform_without_video_has_no_porches() -> None:
    """The plain platform asks for no video at all."""
    check_equal(read_platform_video(fresh_platform()), None)
