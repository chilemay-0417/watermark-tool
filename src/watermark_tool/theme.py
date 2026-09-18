"""Parse opaque sRGB theme colors without adding a Matplotlib dependency."""

from numbers import Integral
import re
from typing import Tuple, Union

from PIL import ImageColor


RGB = Tuple[int, int, int]
ColorInput = Union[str, RGB]


def parse_color(value, name="color") -> RGB:
    """Accept CSS4 names, #RGB/#RRGGBB, rgb(r, g, b), and integer RGB triples."""
    original = value
    if isinstance(value, str):
        value = value.strip().lower()
        match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
        if match:
            value = tuple(int(channel) for channel in match.groups())
        elif value in ImageColor.colormap or re.fullmatch(r"#(?:[0-9a-f]{3}|[0-9a-f]{6})", value):
            value = ImageColor.getrgb(value)
    if (isinstance(value, (tuple, list)) and len(value) == 3
            and all(isinstance(c, Integral) and not isinstance(c, bool) and 0 <= c <= 255
                    for c in value)):
        return tuple(int(channel) for channel in value)
    raise ValueError(
        f"{name} 颜色无效：{original!r}。请使用 CSS4 颜色名（如 midnightblue）、"
        '"rgb(40, 40, 40)"、(40, 40, 40) 或 "#282828"；RGB 必须是 0–255 的整数。'
    )
