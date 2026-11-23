"""Tests of the rational vertical enlargement `scale_y` of video."""

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


def _check(root: Path, platform: dict[str, Any]) -> list[str]:
    """Lay out the catalog and return the messages of the platform."""
    write_video_catalog(root)
    return [f"{f.rule} {f}" for f in check_platform(platform, root)]


def _request(text: str) -> PlatformVideo | None:
    """Read the video request of a platform written in YAML."""
    return read_platform_video(yaml.safe_load(text))


def _plan(**fields: Any) -> VideoPlan:
    """Resolve a request on the 640x480 role of the tests."""
    modes = parse_video_modes(video_modes())
    return plan_video(ROLE, modes, PlatformVideo(**fields))


def test_scale_y_is_read_as_a_ratio() -> None:
    """`scale_y: 12/5` lands as the pair (12, 5)."""
    request = _request(
        "io: {video: {fb_width: 320, fb_height: 200, scale_y: 12/5}}"
    )
    check_equal(request.scale_y if request else None, (12, 5))


def test_without_scale_y_nothing_changes() -> None:
    """Without a ratio the generics stay as they were."""
    check_equal(PlatformVideo().scale_y, None)
    plan = _plan(fb_width=320, fb_height=200)
    check_equal(plan.scale_y, None)
    check_equal(len(plan.entity_generics()), 15)
    check(not any("v_scale" in line for line in plan.generics()))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("12", "scale_y must be written NUM/DEN"),
        ("a/b", "scale_y must be written NUM/DEN"),
        ("5/12", "scale_y must have 1 <= DEN <= NUM"),
        ("0/1", "scale_y must have 1 <= DEN <= NUM"),
        ("24/10", "scale_y must have 1 <= DEN <= NUM"),
        ("16/5", "scale_y must have 1 <= DEN <= NUM"),
        ("16/3", "scale_y must have 1 <= DEN <= NUM"),
        ("14/6", "scale_y must be in lowest terms"),
    ],
)
def test_a_wrong_scale_y_is_reported(text: str, message: str) -> None:
    """Each malformed ratio has a message with its path."""
    with pytest.raises(SchemaError) as bad:
        _request(f"io: {{video: {{scale_y: '{text}'}}}}")
    check(
        any(message in problem for problem in bad.value.problems),
        str(bad.value.problems),
    )


def test_the_doom_ratio_fills_the_visible_area() -> None:
    """320x200 at 2 in x and 12/5 in y is 640x480, the whole mode."""
    plan = _plan(fb_width=320, fb_height=200, scale_y=(12, 5))
    check_equal(plan.scale, 2)
    check_equal(plan.scale_y, (12, 5))
    generics = dict(line.split(" => ") for line in plan.entity_generics())
    check_equal(generics["v_scale_num"], "12")
    check_equal(generics["v_scale_den"], "5")
    check_equal(generics["scale"], "2")
    check_equal(len(generics), 17)
    top = dict(line.split(" => ") for line in plan.generics())
    check_equal(top["video_v_scale_num"], "12")
    check_equal(top["video_v_scale_den"], "5")


def test_a_ratio_that_does_not_fit_is_refused() -> None:
    """The image must fit the visible lines."""
    with pytest.raises(VideoError) as bad:
        _plan(fb_width=320, fb_height=201, scale_y=(12, 5))
    check_in("larger than the visible area", str(bad.value))
    with pytest.raises(VideoError) as wide:
        _plan(fb_width=320, fb_height=200, scale=3, scale_y=(12, 5))
    check_in("larger than the visible area", str(wide.value))


def test_the_check_accepts_and_refuses_scale_y(tmp_path: Path) -> None:
    """`board check` takes the doom ratio and refuses an overflow."""
    ok = video_platform(fb_width=320, fb_height=200)
    ok["io"]["video"]["scale_y"] = "12/5"
    check_equal(_check(tmp_path, ok), [])
    bad = video_platform(fb_width=320, fb_height=240)
    bad["io"]["video"]["scale_y"] = "12/5"
    found = _check(tmp_path, bad)
    check(any("scale_y" in line for line in found), str(found))


def test_a_platform_without_video_has_no_scale_y() -> None:
    """The plain platform asks for no video at all."""
    check_equal(read_platform_video(fresh_platform()), None)
