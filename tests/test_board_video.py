"""Tests of the video role: schema, resolution and rules V20-V22."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from catalog_support import fresh_board, fresh_platform, write
from support import check, check_equal, check_in
from video_support import (
    video_board,
    video_modes,
    video_platform,
    write_video_catalog,
)

from riscv_tools.board_check import check_catalog, check_platform
from riscv_tools.board_schema import (
    Catalog,
    PlatformVideo,
    SchemaError,
    VideoRole,
    parse_board,
    parse_platform_fields,
    parse_video_modes,
    read_platform_video,
)
from riscv_tools.board_video import (
    VideoError,
    VideoPlan,
    aspect_of,
    plan_video,
    resolve_mode,
)

ROLE = VideoRole(
    "vga",
    8,
    "VGA",
    "640x480@60",
    ("640x480@60", "800x600@60", "1280x720@60"),
)


def _modes() -> dict[str, Any]:
    """Read the modes of the tests with the real reader."""
    return parse_video_modes(video_modes())


def _plan(request: PlatformVideo, role: VideoRole = ROLE) -> VideoPlan:
    """Resolve a request on the role of the tests."""
    return plan_video(role, _modes(), request)


def test_a_board_reads_its_video_role() -> None:
    """The role keeps the kind, the bits, the prefix and the modes."""
    board = parse_board(video_board())
    check_equal(board.video, ROLE)
    check_in("leds", board.io)
    check("video" not in board.io)


def test_a_board_without_video_has_none() -> None:
    """The role is optional."""
    check_equal(parse_board(fresh_board()).video, None)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", "dvi", "board.io.video.kind must be one of vga, hdmi"),
        ("channel_bits", 6, "board.io.video.channel_bits must be 4 or 8"),
        (
            "default_mode",
            "800x600@60",
            "board.io.video.default_mode 800x600@60 is not in modes",
        ),
        (
            "modes",
            ["VGA"],
            "board.io.video.modes 'VGA' is not <width>x<height>@<hertz>",
        ),
        ("colour", 1, "board.io.video.colour is not a field of the schema"),
    ],
)
def test_a_wrong_video_field_is_reported(
    field: str, value: Any, message: str
) -> None:
    """Each mistake of the role has a message with its path."""
    raw = video_board(modes=("640x480@60",))
    raw["io"]["video"][field] = value
    with pytest.raises(SchemaError) as bad:
        parse_board(raw)
    check_in(message, bad.value.problems)


def test_the_catalog_of_modes_is_read() -> None:
    """The totals, the porches and the polarity are typed."""
    mode = _modes()["800x600@60"]
    check_equal((mode.width, mode.height, mode.refresh_hz), (800, 600, 60))
    check_equal(mode.pixel_clock_mhz, 40)
    check_equal(mode.horizontal.total, 1056)
    check_equal(mode.horizontal.positive, True)
    check_equal(_modes()["640x480@60"].vertical.positive, False)


def test_a_mode_total_must_add_up() -> None:
    """A total that is not visible + porches + sync is refused."""
    raw = video_modes()
    raw["modes"]["640x480@60"]["horizontal"]["total"] = 801
    with pytest.raises(SchemaError) as bad:
        parse_video_modes(raw)
    check_in(
        "video-modes.modes.640x480@60.horizontal.total is 801 but "
        "visible + front_porch + sync + back_porch is 800",
        bad.value.problems,
    )


def test_a_mode_name_must_match_its_visible_area() -> None:
    """The name and the visible area cannot disagree."""
    raw = video_modes()
    raw["modes"]["640x480@60"]["vertical"] = raw["modes"]["800x600@60"][
        "vertical"
    ]
    with pytest.raises(SchemaError) as bad:
        parse_video_modes(raw)
    check_in(
        "video-modes.modes.640x480@60: the name says 640x480 but the "
        "visible area is 640x600",
        bad.value.problems,
    )


def test_an_unknown_mode_key_is_refused() -> None:
    """A misspelled key of a mode is not ignored."""
    raw = video_modes()
    raw["modes"]["640x480@60"]["clock"] = 25
    with pytest.raises(SchemaError):
        parse_video_modes(raw)


def _platform_video(text: str) -> PlatformVideo | None:
    """Read the video request of a platform written in YAML."""
    return read_platform_video(yaml.safe_load(text))


def test_a_platform_without_video_asks_for_none() -> None:
    """Nothing is planned when the platform does not mention video."""
    check_equal(read_platform_video(fresh_platform()), None)
    check_equal(parse_platform_fields(fresh_platform()).video, None)


def test_an_empty_video_request_takes_the_board_default() -> None:
    """`io.video: {}`, a null value and the peripheral ask for it."""
    check_equal(_platform_video("io: {video: {}}"), PlatformVideo())
    check_equal(_platform_video("io: {video: null}"), PlatformVideo())
    peripheral = "peripherals: [{name: VIDEO, base: 0x1, id: 8}]"
    check_equal(_platform_video(peripheral), PlatformVideo())


def test_an_unquoted_aspect_is_understood() -> None:
    """YAML reads 16:9 as a number; the reader still gets the aspect."""
    wide = _platform_video("io: {video: {aspect: 16:9}}")
    check_equal(wide, PlatformVideo(aspect="16:9"))
    classic = _platform_video("io: {video: {aspect: '4:3'}}")
    check_equal(classic, PlatformVideo(aspect="4:3"))


def test_the_other_request_fields_are_read() -> None:
    """Every field of the request lands in the record."""
    request = _platform_video(
        "io: {video: {width: 1280, height: 720, refresh_hz: 60, "
        "channel_bits: 4, fb_width: 320, fb_height: 200, "
        "outside_manual: true}}"
    )
    check_equal(
        request,
        PlatformVideo(1280, 720, None, 60, 4, 320, 200, True),
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{width: 640}", "platform.io.video.width and height must be"),
        ("{fb_width: 640}", "platform.io.video.fb_width and fb_height"),
        ("{aspect: '5:4'}", "platform.io.video.aspect must be one of"),
        ("{channel_bits: 6}", "platform.io.video.channel_bits must be"),
        ("{depth: 1}", "platform.io.video.depth is not a field"),
    ],
)
def test_a_wrong_request_is_reported(text: str, message: str) -> None:
    """Each mistake of the request has a message with its path."""
    with pytest.raises(SchemaError) as bad:
        _platform_video(f"io: {{video: {text}}}")
    check(any(message in problem for problem in bad.value.problems))


def test_the_video_role_does_not_become_a_count_and_need() -> None:
    """`io.video` is not read as `{count, need}`."""
    fields = parse_platform_fields(video_platform(aspect="4:3"))
    check_equal(fields.video, PlatformVideo(aspect="4:3"))
    check("video" not in fields.io)


def test_the_default_mode_is_the_board_default() -> None:
    """Without a field the mode is the `default_mode`."""
    plan = _plan(PlatformVideo())
    check_equal(plan.mode.name, "640x480@60")
    check_equal((plan.fb_width, plan.fb_height), (640, 480))
    check_equal(plan.channel_bits, 8)


def test_an_aspect_picks_the_largest_mode_of_the_board() -> None:
    """The board lists 800x600 as 4:3 and 1280x720 as 16:9."""
    check_equal(_plan(PlatformVideo(aspect="4:3")).mode.name, "800x600@60")
    check_equal(_plan(PlatformVideo(aspect="16:9")).mode.name, "1280x720@60")


def test_an_aspect_ignores_the_modes_the_board_does_not_list() -> None:
    """1024x768 is 4:3 in the catalog but not in the board modes."""
    role = VideoRole("vga", 8, "VGA", "640x480@60", ("640x480@60",))
    with pytest.raises(VideoError) as bad:
        _plan(PlatformVideo(aspect="16:9"), role)
    check_in("has no mode among the modes of the board", str(bad.value))
    check_in("640x480@60 (4:3)", str(bad.value))


def test_a_size_finds_the_mode_in_the_catalog() -> None:
    """The size 800x600 gives the mode of the catalog."""
    plan = _plan(PlatformVideo(width=800, height=600))
    check_equal(plan.mode.name, "800x600@60")


def test_a_size_prefers_the_default_and_the_listed_refresh() -> None:
    """Two refresh rates of one size: the one the board lists wins."""
    check_equal(
        _plan(PlatformVideo(width=640, height=480)).mode.name, "640x480@60"
    )
    request = PlatformVideo(
        width=640, height=480, refresh_hz=85, outside_manual=True
    )
    check_equal(_plan(request).mode.name, "640x480@85")


def test_a_size_that_is_not_in_the_catalog_lists_the_known_modes() -> None:
    """The message names what the catalog has."""
    with pytest.raises(VideoError) as bad:
        _plan(PlatformVideo(width=320, height=200))
    check_in("io.video 320x200 is not in video-modes.yaml", str(bad.value))
    check_in("640x480@60", str(bad.value))


def test_the_aspect_must_match_the_size() -> None:
    """1280x720 is 16:9, so asking 4:3 for it is refused."""
    request = PlatformVideo(width=1280, height=720, aspect="4:3")
    with pytest.raises(VideoError) as bad:
        _plan(request)
    check_equal(str(bad.value), "io.video 1280x720 is 16:9, not 4:3")


def test_the_aspect_is_reduced_to_lowest_terms() -> None:
    """1280x1024 is 5:4, which neither accepted aspect covers."""
    check_equal(aspect_of(1280, 1024), "5:4")
    check_equal(aspect_of(1920, 1080), "16:9")


def test_a_mode_outside_the_manual_needs_the_mark() -> None:
    """1024x768 exists in the catalog but the board does not list it."""
    request = PlatformVideo(width=1024, height=768)
    with pytest.raises(VideoError) as bad:
        _plan(request)
    check_in("not in the modes of the board", str(bad.value))
    check_in("outside_manual: true", str(bad.value))
    marked = PlatformVideo(width=1024, height=768, outside_manual=True)
    plan = _plan(marked)
    check_equal(plan.mode.name, "1024x768@60")
    check_in("outside the manual of the board", plan.warnings[0])


def test_the_channel_bits_cannot_exceed_the_board() -> None:
    """A 4 bit board refuses 8 bits per channel."""
    role = VideoRole("vga", 4, "VGA", "640x480@60", ("640x480@60",))
    with pytest.raises(VideoError) as bad:
        _plan(PlatformVideo(channel_bits=8), role)
    check_equal(
        str(bad.value),
        "io.video channel_bits 8 exceeds the 4 bits per channel of the board",
    )
    check_equal(_plan(PlatformVideo(channel_bits=4), role).channel_bits, 4)
    check_equal(_plan(PlatformVideo(channel_bits=4)).channel_bits, 4)


def test_the_framebuffer_cannot_exceed_the_visible_area() -> None:
    """A 800x600 framebuffer does not fit a 640x480 mode."""
    with pytest.raises(VideoError) as bad:
        _plan(PlatformVideo(fb_width=800, fb_height=600))
    check_in("framebuffer 800x600 is larger", str(bad.value))


def test_the_refresh_alone_cannot_choose_a_mode() -> None:
    """The refresh rate only narrows a size or an aspect."""
    with pytest.raises(VideoError):
        resolve_mode(ROLE, _modes(), PlatformVideo(refresh_hz=60))


def test_the_generics_describe_the_timing() -> None:
    """The top gets the totals, the sync, the polarity and the frame."""
    plan = _plan(PlatformVideo(aspect="16:9", fb_width=320, fb_height=200))
    generics = dict(line.split(" => ") for line in plan.generics())
    check_equal(generics["video_kind"], '"vga"')
    check_equal(generics["video_channel_bits"], "8")
    check_equal(generics["video_fb_width"], "320")
    check_equal(generics["video_fb_height"], "200")
    check_equal(generics["video_h_total"], "1650")
    check_equal(generics["video_h_sync"], "40")
    check_equal(generics["video_h_front_porch"], "110")
    check_equal(generics["video_h_back_porch"], "220")
    check_equal(generics["video_h_visible"], "1280")
    check_equal(generics["video_h_sync_positive"], "true")
    check_equal(generics["video_v_total"], "750")
    check_equal(generics["video_v_sync"], "5")
    check_equal(len(generics), 16)
    check_equal(plan.framebuffer_bits, 320 * 200 * 24)


def _check(
    root: Path,
    platform: dict[str, Any],
    board: dict[str, Any] | None = None,
) -> list[str]:
    """Lay out the catalog and return the messages of the platform."""
    write_video_catalog(root, board)
    return [f"{f.rule} {f}" for f in check_platform(platform, root)]


def test_a_clean_video_platform_passes(tmp_path: Path) -> None:
    """The default mode at 25 MHz fits the PLL and the memory."""
    check_equal(
        _check(tmp_path, video_platform(fb_width=160, fb_height=100)), []
    )


def test_a_platform_without_video_ignores_the_catalog(tmp_path: Path) -> None:
    """A board with video and a platform that does not ask for it."""
    check_equal(_check(tmp_path, fresh_platform()), [])


def test_v20_a_board_without_video(tmp_path: Path) -> None:
    """Asking for video on a board that has none is an error."""
    board = fresh_board()
    found = _check(tmp_path, video_platform(), board)
    check_equal(found, ["V20 E io.video asked but board 'bd' has no io.video"])


def test_v20_a_catalog_without_the_mode(tmp_path: Path) -> None:
    """The mode of the board that the catalog lacks is named."""
    modes = video_modes()
    del modes["modes"]["640x480@60"]
    write_video_catalog(tmp_path, modes=modes)
    found = check_platform(video_platform(), tmp_path)
    check_equal([f.rule for f in found], ["V20"])
    check_in("names mode 640x480@60", found[0].text)


def test_v20_the_mismatched_aspect_is_an_error(tmp_path: Path) -> None:
    """The message says what the size really is."""
    request = video_platform(width=800, height=600, aspect="16:9")
    check_equal(
        _check(tmp_path, request),
        ["V20 E io.video 800x600 is 4:3, not 16:9"],
    )


def test_v20_outside_the_manual_warns_when_marked(tmp_path: Path) -> None:
    """The mark turns the error into a warning."""
    request = video_platform(
        width=1024,
        height=768,
        outside_manual=True,
        fb_width=160,
        fb_height=100,
    )
    found = _check(tmp_path, request)
    check_equal(len(found), 2)
    check(found[0].startswith("V20 W io.video mode 1024x768@60 is outside"))
    check(found[1].startswith("V21 E pixel clock 65"))


def test_v20_channel_bits_above_the_board(tmp_path: Path) -> None:
    """A 4 bit board refuses 8 bits per channel."""
    found = _check(
        tmp_path,
        video_platform(channel_bits=8, fb_width=160, fb_height=100),
        video_board(bits=4),
    )
    check_equal(len(found), 1)
    check_in("exceeds the 4 bits per channel", found[0])


def test_v21_the_pll_cannot_make_the_pixel_clock(tmp_path: Path) -> None:
    """74.25 MHz is not an integer divider of any VCO from 50 MHz."""
    found = _check(
        tmp_path, video_platform(aspect="16:9", fb_width=160, fb_height=100)
    )
    check_equal(len(found), 1)
    check(found[0].startswith("V21 E pixel clock 74.25 MHz of mode 1280x720"))
    check_in("from this reference", found[0])


def test_v21_names_the_other_clocks_when_they_are_the_cause(
    tmp_path: Path,
) -> None:
    """A pixel clock the PLL makes alone but not with the platform."""
    board = video_board()
    platform = video_platform(fb_width=160, fb_height=100)
    platform["clocks"]["core"] = {"mhz": 33, "phase_ps": 0}
    found = _check(tmp_path, platform, board)
    check_equal(len(found), 1)
    check_in("together with the other clocks of the platform", found[0])


def test_v22_the_framebuffer_does_not_fit(tmp_path: Path) -> None:
    """640x480 at 24 bits needs 800 blocks, and 100 are free."""
    board = video_board(blocks=100)
    found = _check(tmp_path, video_platform(), board)
    check_equal(len(found), 1)
    check(found[0].startswith("V22 E framebuffer 640x480 at 24 bits per"))
    check_in("needs 800 memory blocks but only 100 of 100 are free", found[0])


def test_v22_a_smaller_framebuffer_fits(tmp_path: Path) -> None:
    """The remedy of the message works."""
    board = video_board(blocks=100)
    found = _check(
        tmp_path, video_platform(fb_width=160, fb_height=100), board
    )
    check_equal(found, [])


def _video_problems(root: Path) -> list[str]:
    """List the catalog problems that concern the video."""
    problems = check_catalog(Catalog.for_root(root))
    return [problem for problem in problems if "video" in problem]


def test_the_catalog_check_wants_the_modes(tmp_path: Path) -> None:
    """A board mode missing from the catalog is a catalog problem."""
    write_video_catalog(tmp_path)
    check_equal(_video_problems(tmp_path), [])
    modes = video_modes()
    del modes["modes"]["800x600@60"]
    write(tmp_path / "boards" / "video-modes.yaml", modes)
    check_equal(
        _video_problems(tmp_path),
        [
            "board bd: io.video.modes cites 800x600@60, which is not in "
            "video-modes.yaml"
        ],
    )


def test_the_catalog_check_wants_the_video_pins(tmp_path: Path) -> None:
    """The prefix of the video signals has to exist in the pins file."""
    board = video_board()
    board["io"]["video"]["signals"] = "HDMI"
    write_video_catalog(tmp_path, board)
    check_equal(
        _video_problems(tmp_path),
        ["board bd: io.video cites HDMI_, which is not in pins"],
    )


def test_an_invalid_catalog_of_modes_is_reported(tmp_path: Path) -> None:
    """The catalog check and the V1 rule both read the file."""
    modes = video_modes()
    modes["modes"]["640x480@60"]["horizontal"]["total"] = 1
    write_video_catalog(tmp_path, modes=modes)
    check(
        any(
            "horizontal.total is 1" in problem
            for problem in check_catalog(Catalog.for_root(tmp_path))
        )
    )
    found = check_platform(video_platform(), tmp_path)
    check_equal(found[0].rule, "V1")
    check_in("video-modes.yaml is invalid", found[0].text)
