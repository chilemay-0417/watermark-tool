"""Decode native 16-bit PNG samples, including Macs without libspng wheels."""

import numpy as np


def decode_png16(path, color_type):
    try:
        import pyspng
    except (ImportError, OSError):
        import png

        with path.open('rb') as stream:
            width, height, rows, info = png.Reader(file=stream).asDirect()
            pixels = np.empty((height, width * info['planes']), dtype=np.uint16)
            for index, row in enumerate(rows):
                pixels[index] = row
        return pixels.reshape(height, width, info['planes'])
    if color_type == 4:
        # libspng cannot output GA16; RGBA16 retains both native planes.
        return pyspng.lib.c.spng_decode_image_bytes(
            path.read_bytes(), pyspng.lib.c.SPNG_FMT_RGBA16,
        )
    return pyspng.load(path.read_bytes())
