"""The resolved video of a platform on a board, ready for the top."""

from dataclasses import dataclass

from riscv_tools.board_schema import PlatformVideo, VideoMode, VideoRole
from riscv_tools.board_video.resolve import VideoError, resolve_mode

# Cada pixel do framebuffer guarda os três canais, sem preenchimento.
CHANNELS = 3


@dataclass(frozen=True)
class VideoPlan:
    """The video the generated top is built with.

    Parameters
    ----------
    kind : str
        `vga` or `hdmi`.
    mode : VideoMode
        The resolved mode.
    channel_bits : int
        The bits of each color channel.
    fb_width : int
        The columns of the framebuffer.
    fb_height : int
        The lines of the framebuffer.
    warnings : tuple of str
        The warnings found while resolving.
    """

    kind: str
    mode: VideoMode
    channel_bits: int
    fb_width: int
    fb_height: int
    warnings: tuple[str, ...] = ()

    @property
    def pixel_bits(self) -> int:
        """Give the bits one pixel of the framebuffer stores."""
        return CHANNELS * self.channel_bits

    @property
    def framebuffer_bits(self) -> int:
        """Give the bits of the whole framebuffer."""
        return self.fb_width * self.fb_height * self.pixel_bits

    def generics(self) -> list[str]:
        """Write the generics of the video, as VHDL associations.

        Returns
        -------
        list of str
            One `name => value` per generic: the kind, the bits of the
            channel, the size of the framebuffer, and for each axis
            (`h` and `v`) the visible area, the porches, the
            synchronism, the total and the polarity.
        """
        out = [
            f'video_kind => "{self.kind}"',
            f"video_channel_bits => {self.channel_bits}",
            f"video_fb_width => {self.fb_width}",
            f"video_fb_height => {self.fb_height}",
        ]
        for prefix, axis in (
            ("h", self.mode.horizontal),
            ("v", self.mode.vertical),
        ):
            out += [
                f"video_{prefix}_visible => {axis.visible}",
                f"video_{prefix}_front_porch => {axis.front_porch}",
                f"video_{prefix}_sync => {axis.sync}",
                f"video_{prefix}_back_porch => {axis.back_porch}",
                f"video_{prefix}_total => {axis.total}",
                f"video_{prefix}_sync_positive => "
                f"{str(axis.positive).lower()}",
            ]
        return out


def _size(plan_mode: VideoMode, request: PlatformVideo) -> tuple[int, int]:
    """Choose the size of the framebuffer.

    Parameters
    ----------
    plan_mode : VideoMode
        The resolved mode.
    request : PlatformVideo
        The request.

    Returns
    -------
    tuple of (int, int)
        The columns and lines, the visible area when not requested.

    Raises
    ------
    VideoError
        If the framebuffer is larger than the visible area.
    """
    width = request.fb_width or plan_mode.width
    height = request.fb_height or plan_mode.height
    if width > plan_mode.width or height > plan_mode.height:
        raise VideoError(
            f"io.video framebuffer {width}x{height} is larger than the "
            f"visible area {plan_mode.width}x{plan_mode.height} of mode "
            f"{plan_mode.name}"
        )
    return width, height


def plan_video(
    role: VideoRole,
    catalog: dict[str, VideoMode],
    request: PlatformVideo,
) -> VideoPlan:
    """Resolve the video of a platform on a board.

    Parameters
    ----------
    role : VideoRole
        The video output of the board.
    catalog : dict of str to VideoMode
        The catalog of modes.
    request : PlatformVideo
        The request of the platform.

    Returns
    -------
    VideoPlan
        The mode, the width of the channel and the framebuffer.

    Raises
    ------
    VideoError
        If the mode is missing from the catalog, is outside the manual
        of the board without `outside_manual`, does not match the
        proportion, or asks for more bits per channel than the board.
    """
    mode = resolve_mode(role, catalog, request)
    warnings: list[str] = []
    if mode.name not in role.modes:
        if not request.outside_manual:
            raise VideoError(
                f"io.video mode {mode.name} is not in the modes of the "
                f"board ({', '.join(role.modes)}); write "
                f"outside_manual: true to use it anyway"
            )
        warnings.append(
            f"W io.video mode {mode.name} is outside the manual of the "
            f"board; the monitor may not accept it"
        )
    bits = request.channel_bits or role.channel_bits
    if bits > role.channel_bits:
        raise VideoError(
            f"io.video channel_bits {bits} exceeds the "
            f"{role.channel_bits} bits per channel of the board"
        )
    width, height = _size(mode, request)
    return VideoPlan(role.kind, mode, bits, width, height, tuple(warnings))
