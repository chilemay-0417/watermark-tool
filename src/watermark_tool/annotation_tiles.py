"""Pillow-compatible annotation surface allocating only touched 256px tiles."""

import math

from PIL import Image, ImageDraw


class AnnotationTiles:
    """Implement the paste/text/line subset used by the shared annotation renderer."""

    tile_size = 256

    def __init__(self, size, background):
        self.width, self.height = size
        self.background = background
        self.tiles = {}
        self._measure_image = Image.new("RGB", (1, 1))
        self._measure = ImageDraw.Draw(self._measure_image)

    def _intersecting(self, bounds):
        left, top, right, bottom = bounds
        left, top = max(0, math.floor(left)), max(0, math.floor(top))
        right, bottom = min(self.width, math.ceil(right)), min(self.height, math.ceil(bottom))
        if right <= left or bottom <= top:
            return
        step = self.tile_size
        for y in range(top // step * step, bottom, step):
            for x in range(left // step * step, right, step):
                key = (x, y)
                if key not in self.tiles:
                    self.tiles[key] = Image.new(
                        "RGB", (min(step, self.width - x), min(step, self.height - y)),
                        self.background,
                    )
                yield x, y, self.tiles[key]

    def paste(self, image, position, mask=None):
        left, top = position
        for x, y, tile in self._intersecting(
            (left, top, left + image.width, top + image.height),
        ):
            tile.paste(image, (left - x, top - y), mask)

    def textbbox(self, position, text, **kwargs):
        return self._measure.textbbox(position, text, **kwargs)

    def text(self, position, text, *, font, fill):
        # Match Pillow's global integer origin and fractional glyph start exactly.
        # Translating a fractional coordinate into a negative tile-local coordinate
        # changes int() truncation and can shift antialiasing at tile boundaries.
        mask, offset = font.getmask2(
            text, "L", start=tuple(math.modf(value)[0] for value in position),
        )
        if not mask.size[0] or not mask.size[1]:
            return
        origin = tuple(int(value) + delta for value, delta in zip(position, offset, strict=True))
        with Image.frombytes("L", mask.size, bytes(mask)) as alpha:
            with Image.new("RGB", mask.size, fill) as glyph:
                self.paste(glyph, origin, alpha)

    def line(self, coordinates, *, fill, width):
        x1, y1, x2, y2 = coordinates
        bounds = (min(x1, x2) - width, min(y1, y2) - width,
                  max(x1, x2) + width + 1, max(y1, y2) + width + 1)
        for x, y, tile in self._intersecting(bounds):
            ImageDraw.Draw(tile).line((x1 - x, y1 - y, x2 - x, y2 - y), fill=fill, width=width)

    def close(self):
        for tile in self.tiles.values():
            tile.close()
        self.tiles.clear()
        self._measure_image.close()
