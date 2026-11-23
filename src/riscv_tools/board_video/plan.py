"""The resolved video of a platform on a board, ready for the top."""

from dataclasses import dataclass
from typing import cast

from riscv_tools.board_schema import PlatformVideo, VideoMode, VideoRole
from riscv_tools.board_video.resolve import VideoError, resolve_mode

# Uma cor tem três canais.
CHANNELS = 3
# Formato indexado: um byte por pixel e uma paleta de 256 entradas.
INDEXED = "indexed"
DIRECT = "direct"
INDEXED_BITS = 8
PALETTE_ENTRIES = 256
# A memória do framebuffer é escrita em palavras de 32 bits.
WORD_BITS = 32
HALF_WORD_BITS = 16


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
    pixel_format : str
        `indexed` (a byte that indexes the palette) or `direct` (the
        color in the pixel).
    scale : int
        The enlargement of each framebuffer pixel in x (and in y when
        `scale_y` is None).
    scale_y : tuple of (int, int) or None
        The rational vertical enlargement `NUM/DEN` (12/5 takes 200
        lines to 480); None when y uses the integer `scale`.
    """

    kind: str
    mode: VideoMode
    channel_bits: int
    fb_width: int
    fb_height: int
    warnings: tuple[str, ...] = ()
    pixel_format: str = INDEXED
    scale: int = 1
    scale_y: tuple[int, int] | None = None

    @property
    def indexed(self) -> bool:
        """Tell whether the pixel is an index of the palette."""
        return self.pixel_format == INDEXED

    @property
    def pixel_bits(self) -> int:
        """Give the bits one pixel of the framebuffer stores.

        Returns
        -------
        int
            8 when indexed; when direct, 16 if the three channels fit
            in 16 bits, else 32 (the storage of the `video` entity).
        """
        if self.indexed:
            return INDEXED_BITS
        narrow = CHANNELS * self.channel_bits <= HALF_WORD_BITS
        return HALF_WORD_BITS if narrow else WORD_BITS

    @property
    def row_words(self) -> int:
        """Give the 32-bit words one line of the framebuffer takes."""
        return -(-self.fb_width * self.pixel_bits // WORD_BITS)

    @property
    def framebuffer_words(self) -> int:
        """Give the 32-bit words of the whole framebuffer."""
        return self.row_words * self.fb_height

    @property
    def framebuffer_bits(self) -> int:
        """Give the bits of the whole framebuffer."""
        return self.framebuffer_words * WORD_BITS

    @property
    def palette_bits(self) -> int:
        """Give the bits of the palette (zero when direct)."""
        if not self.indexed:
            return 0
        return PALETTE_ENTRIES * CHANNELS * self.channel_bits

    @property
    def memory_bits(self) -> int:
        """Give the bits of memory the framebuffer and palette take."""
        return self.framebuffer_bits + self.palette_bits

    def entity_generics(self) -> list[str]:
        """Write the generics of the `video` entity of the Peripherals.

        Returns
        -------
        list of str
            One `name => value` per generic the entity has: the
            framebuffer, the channel, the format, the scale and the
            timing of each axis.
        """
        out = [
            f"fb_width => {self.fb_width}",
            f"fb_height => {self.fb_height}",
            f"channel_bits => {self.channel_bits}",
            f'pixel_format => "{self.pixel_format}"',
            f"scale => {self.scale}",
        ]
        if self.scale_y is not None:
            out += [
                f"v_scale_num => {self.scale_y[0]}",
                f"v_scale_den => {self.scale_y[1]}",
            ]
        for prefix, axis in (
            ("h", self.mode.horizontal),
            ("v", self.mode.vertical),
        ):
            out += [
                f"{prefix}_visible => {axis.visible}",
                f"{prefix}_front_porch => {axis.front_porch}",
                f"{prefix}_sync => {axis.sync}",
                f"{prefix}_back_porch => {axis.back_porch}",
                f"{prefix}_sync_positive => {str(axis.positive).lower()}",
            ]
        return out

    def generics(self) -> list[str]:
        """Write the generics of the video, as VHDL associations.

        Returns
        -------
        list of str
            One `name => value` per generic: the kind, the bits of the
            channel, the size and format of the framebuffer, the scale,
            and for each axis (`h` and `v`) the visible area, the
            porches, the synchronism, the total and the polarity.
        """
        out = [
            f'video_kind => "{self.kind}"',
            f"video_channel_bits => {self.channel_bits}",
            f"video_fb_width => {self.fb_width}",
            f"video_fb_height => {self.fb_height}",
            f'video_pixel_format => "{self.pixel_format}"',
            f"video_scale => {self.scale}",
        ]
        if self.scale_y is not None:
            out += [
                f"video_v_scale_num => {self.scale_y[0]}",
                f"video_v_scale_den => {self.scale_y[1]}",
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
    scale = _scale(mode, request, width, height)
    return VideoPlan(
        role.kind,
        mode,
        bits,
        width,
        height,
        tuple(warnings),
        request.pixel_format or INDEXED,
        scale,
        request.scale_y,
    )


def _scale(
    mode: VideoMode, request: PlatformVideo, width: int, height: int
) -> int:
    """Choose the enlargement of each framebuffer pixel.

    Parameters
    ----------
    mode : VideoMode
        The resolved mode.
    request : PlatformVideo
        The request.
    width : int
        The columns of the framebuffer.
    height : int
        The lines of the framebuffer.

    Returns
    -------
    int
        The requested scale, or the largest that fits the visible area.

    Raises
    ------
    VideoError
        If the enlarged image is larger than the visible area.
    """
    if request.scale_y is not None:
        return _scale_x(mode, request, width, height)
    fit = min(mode.width // width, mode.height // height)
    if request.scale is None:
        return max(fit, 1)
    if request.scale > fit:
        raise VideoError(
            f"io.video scale {request.scale} makes the {width}x{height} "
            f"framebuffer larger than the visible area {mode.width}x"
            f"{mode.height} of mode {mode.name}"
        )
    return request.scale


def _scale_x(
    mode: VideoMode, request: PlatformVideo, width: int, height: int
) -> int:
    """Choose the horizontal enlargement for a rational vertical one.

    Parameters
    ----------
    mode : VideoMode
        The resolved mode.
    request : PlatformVideo
        The request, with `scale_y` set.
    width : int
        The columns of the framebuffer.
    height : int
        The lines of the framebuffer.

    Returns
    -------
    int
        The requested scale, or the largest that fits the columns.

    Raises
    ------
    VideoError
        If the enlarged image is larger than the visible area.
    """
    num, den = cast("tuple[int, int]", request.scale_y)
    lines = -(-height * num // den)
    fit = mode.width // width
    scale = fit if request.scale is None else request.scale
    if scale > fit or lines > mode.height:
        raise VideoError(
            f"io.video scale {scale} and scale_y {num}/{den} make the "
            f"{width}x{height} framebuffer {width * scale}x{lines}, larger "
            f"than the visible area {mode.width}x{mode.height} of mode "
            f"{mode.name}"
        )
    return max(scale, 1)
