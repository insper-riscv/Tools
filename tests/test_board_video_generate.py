"""Tests of the video resolved by the generator for the thin top."""

import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
import yaml
from multifpga_support import BOARDS, CHIPS, platform_file
from support import check, check_equal, check_in
from video_support import video_modes

from riscv_tools.board_clocks import ClockPlan
from riscv_tools.board_generate import GenerateRequest, generate
from riscv_tools.board_inputs import InputError
from riscv_tools.top_generator import TopSpec, video_generics

BOARD_VIDEO: dict[str, Any] = {
    "kind": "vga",
    "channel_bits": 4,
    "signals": "VGA",
    "default_mode": "640x480@60",
    "modes": ["640x480@60"],
}


def _copy(tmp_path: Path, request: dict[str, Any] | None) -> GenerateRequest:
    """Copy the DE0-CV fixtures, give the board video and ask for it."""
    boards = tmp_path / "boards"
    shutil.copytree(BOARDS, boards)
    path = boards / "de0-cv" / "board.yaml"
    board = yaml.safe_load(path.read_text())
    board["io"]["video"] = BOARD_VIDEO
    path.write_text(yaml.safe_dump(board, sort_keys=False))
    (boards / "video-modes.yaml").write_text(
        yaml.safe_dump(video_modes(), sort_keys=False)
    )
    platform = yaml.safe_load(platform_file("de0-cv").read_text())
    if request is not None:
        platform["io"]["video"] = request
    target = tmp_path / "platform.yaml"
    target.write_text(yaml.safe_dump(platform, sort_keys=False))
    return GenerateRequest(target, None, boards, CHIPS, accept_inferred=True)


def test_a_platform_without_video_resolves_none(tmp_path: Path) -> None:
    """The existing platforms generate as before, with no video."""
    result = generate(_copy(tmp_path, None))
    check_equal(result.video, None)


def test_the_resolved_video_reaches_the_generated_result(
    tmp_path: Path,
) -> None:
    """An empty request takes the default mode of the board."""
    result = generate(_copy(tmp_path, {"fb_width": 320, "fb_height": 200}))
    video = result.video
    if video is None:
        pytest.fail("the platform asked for video")
    check_equal(video.mode.name, "640x480@60")
    check_equal(video.channel_bits, 4)
    check_equal((video.fb_width, video.fb_height), (320, 200))


def test_the_video_does_not_change_the_generated_top(tmp_path: Path) -> None:
    """The peripheral is not instantiated, so the files are equal."""
    plain = generate(_copy(tmp_path / "a", None))
    with_video = generate(_copy(tmp_path / "b", {}))
    check_equal(with_video.files, plain.files)


def test_the_generics_are_available_to_the_top() -> None:
    """The top spec hands the generics of the video to the generator."""
    request = GenerateRequest(
        platform_file("de0-cv"), None, BOARDS, CHIPS, accept_inferred=True
    )
    empty = TopSpec(
        {}, ClockPlan("CLK", Fraction(50), ()), (), "pll", "top", {}
    )
    check_equal(video_generics(empty), [])
    check(generate(request).video is None)


def test_the_generics_of_a_resolved_video(tmp_path: Path) -> None:
    """The lines are the ones of the plan, one per generic."""
    video = generate(_copy(tmp_path, {})).video
    spec = TopSpec(
        {},
        ClockPlan("CLK", Fraction(50), ()),
        (),
        "pll",
        "top",
        {},
        video,
    )
    lines = video_generics(spec)
    check_in('video_kind => "vga"', lines)
    check_in("video_h_total => 800", lines)
    check_in("video_v_total => 525", lines)
    check_in("video_h_sync_positive => false", lines)
    check_in("video_fb_width => 640", lines)


@pytest.mark.parametrize(
    ("request_fields", "message"),
    [
        ({"width": 320, "height": 200}, "io.video 320x200 is not in"),
        ({"aspect": "16:9"}, "has no mode among the modes of the board"),
        ({"channel_bits": 8}, "exceeds the 4 bits per channel"),
        ({"width": 1024, "height": 768}, "outside_manual: true"),
    ],
)
def test_an_unsatisfiable_request_stops_the_generation(
    tmp_path: Path, request_fields: dict[str, Any], message: str
) -> None:
    """The generator refuses with the same message as the validator."""
    with pytest.raises(InputError) as bad:
        generate(_copy(tmp_path, request_fields))
    check_in(message, str(bad.value))
    check(str(bad.value).startswith("E io.video"))
