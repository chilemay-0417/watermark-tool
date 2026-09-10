"""The compiler-free fallback must retain all sample bits and transparency."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import png

from watermark_tool.raster import read_raster


class FallbackDecoderTests(unittest.TestCase):
    def test_fallback_matches_native_samples_for_all_16bit_color_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            for planes in (1, 2, 3, 4):
                for transparent in (False, True):
                    if transparent and planes in (2, 4):
                        continue
                    with self.subTest(planes=planes, transparent=transparent):
                        values = np.arange(2 * 3 * planes, dtype=np.uint16).reshape(2, -1)
                        values[0, 0] = 65535
                        options = {'greyscale': planes < 3, 'alpha': planes in (2, 4)}
                        if transparent:
                            options['transparent'] = (65535 if planes == 1
                                                      else tuple(map(int, values[0, :3])))
                        source = Path(temporary) / 'native.png'
                        with source.open('wb') as stream:
                            png.Writer(3, 2, bitdepth=16, **options).write(stream, values)
                        expected = read_raster(source)
                        with patch.dict('sys.modules', {'pyspng': None}):
                            actual = read_raster(source)
                        self.assertEqual(actual.bits, expected.bits)
                        np.testing.assert_array_equal(actual.pixels, expected.pixels)
                        np.testing.assert_array_equal(actual.alpha, expected.alpha)
