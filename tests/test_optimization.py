"""Regression coverage for bounded-memory rendering and reusable batch resources."""
from collections import OrderedDict
import gc
from io import BytesIO
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import weakref

import numpy as np
import png
from PIL import Image, ImageCms, JpegImagePlugin, PngImagePlugin

from tests.test_color import p3_profile
from tests.test_layout import suppress_watermark_logs
from watermark_tool import asset_cache, exif_gps
from watermark_tool.config import LayoutConfig
from watermark_tool.metadata import read_source_metadata, collect_metadata
from watermark_tool.preserved import png_chunk
from watermark_tool.raster import ColorSpec, inspect_raster, read_raster
from watermark_tool.renderer import make_canvas, prepare_logo_image

ROOT = Path(__file__).resolve().parents[1]


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cache = self.root / 'cache'
        self.enterContext(patch.dict(os.environ, WATERMARK_CACHE_DIR=str(self.cache)))
        self.enterContext(patch.object(asset_cache, '_MEMORY', OrderedDict()))
        self.enterContext(suppress_watermark_logs())

    def config(self, **changes):
        return LayoutConfig(**{
            'output_mode': 'original', 'include_gps_location': False,
            'show_signature': False, 'signature_text': '',
            'line_length': 12, 'line_left_offset': 0, 'date_font_size': 10,
            **changes,
        })

    def test_original_layout_accepts_short_final_photo_in_both_modes(self):
        large, small = self.root / 'large.jpg', self.root / 'small.jpg'
        Image.new('RGB', (1600, 1600)).save(large)
        Image.new('RGB', (100, 100)).save(small)
        for mode in ('preserve', 'srgb'):
            for paths in ([small], [large, small], [small, large]):
                with self.subTest(mode=mode, paths=paths):
                    output = self.root / 'original.jpg'
                    make_canvas(paths, output, self.config(color_mode=mode, show_signature=True))
                    self.assertTrue(output.is_file())

    def test_original_footer_fits_inside_canvas_for_narrow_photo(self):
        path = self.root / 'narrow.png'
        exif = Image.Exif()
        exif[34665] = {36867: '2021:08:04 13:23:39'}
        Image.new('RGB', (100, 100), (128, 128, 128)).save(path, exif=exif)
        output = self.root / 'footer.png'
        make_canvas([path], output, self.config(
            line_length=900, line_left_offset=80, date_font_size=55,
        ))
        with Image.open(output) as image:
            self.assertGreater(image.width, 1100)
            # The final column must remain background, not a cut-off line or glyph.
            np.testing.assert_array_equal(np.asarray(image)[:, -1], 255)

    def test_icc_descriptive_changes_do_not_trigger_mixed_gamut_or_16bit_output(self):
        first = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        second = bytearray(first)
        for i in range(struct.unpack_from('>I', first, 128)[0]):
            tag, offset, length = struct.unpack_from('>4sII', first, 132 + 12 * i)
            if tag == b'cprt':
                second[offset + length - 1] ^= 1
        ImageCms.ImageCmsProfile(BytesIO(second))
        self.assertEqual(ColorSpec(icc=first).key(), ColorSpec(icc=bytes(second)).key())
        self.assertNotEqual(ColorSpec(icc=first).key(), ColorSpec(icc=p3_profile()).key())
        paths = []
        for i, profile in enumerate((first, bytes(second))):
            path = self.root / f'icc-{i}.png'
            Image.new('RGB', (32, 32), (160, 80, 40)).save(path, icc_profile=profile)
            paths.append(path)
        output = self.root / 'same.png'
        make_canvas(paths, output, self.config())
        raster = read_raster(output)
        self.assertEqual(raster.bits, 8)
        self.assertEqual(raster.color.key(), ColorSpec(icc=first).key())

    def test_asset_cache_survives_process_cache_clear_and_returns_independent_images(self):
        path = self.root / 'logo.png'
        Image.new('RGBA', (64, 64), (200, 100, 40, 128)).save(path)
        first = prepare_logo_image(path)
        expected = np.asarray(first).copy()
        first.paste((0, 0, 0, 0), (0, 0, first.width, first.height))
        asset_cache._MEMORY.clear()
        with patch('watermark_tool.renderer.open_logo_image', side_effect=AssertionError('decode')):
            second = prepare_logo_image(path)
        np.testing.assert_array_equal(second, expected)

    def test_asset_cache_invalidates_on_content_even_if_file_timestamp_is_restored(self):
        path = self.root / 'logo.png'
        Image.new('RGB', (32, 32), 'red').save(path)
        before = path.stat()
        prepare_logo_image(path)
        Image.new('RGB', (32, 32), 'blue').save(path)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with prepare_logo_image(path) as image:
            self.assertEqual(image.getpixel((20, 20)), (0, 0, 255, 255))

    def test_corrupt_or_unwritable_asset_cache_does_not_block_rendering(self):
        path = self.root / 'logo.png'
        Image.new('RGB', (32, 32), 'red').save(path)
        prepare_logo_image(path)
        for file in self.cache.glob('*.png'):
            file.write_bytes(b'broken')
        asset_cache._MEMORY.clear()
        self.assertEqual(prepare_logo_image(path).getpixel((20, 20)), (255, 0, 0, 255))
        blocked = self.root / 'blocked'
        blocked.write_text('not a directory')
        with patch.dict(os.environ, WATERMARK_CACHE_DIR=str(blocked)):
            self.assertEqual(prepare_logo_image(path).getpixel((20, 20)), (255, 0, 0, 255))

    def test_metadata_snapshot_does_not_decode_jpeg_pixels(self):
        path = self.root / 'exif.jpg'
        exif = Image.Exif()
        exif[315] = 'Owner'
        exif[34665] = {36867: '2021:08:04 13:23:39'}
        Image.new('RGB', (100, 100)).save(path, exif=exif)
        with patch.object(
            JpegImagePlugin.JpegImageFile, 'load', side_effect=AssertionError('pixels'),
        ):
            source = read_source_metadata(path)
            self.assertEqual(source[0][315], 'Owner')
            metadata = collect_metadata([path], (200, 300), sources=[source])
            self.assertIn('exif', metadata)

    def test_png_metadata_after_pixels_is_read_without_decoding(self):
        path = self.root / 'tail.png'
        Image.new('RGB', (16, 12)).save(path)
        original = path.read_bytes()
        exif = Image.Exif()
        exif[315] = 'Tail Owner'
        exif[274] = 6
        exif[34665] = {36867: '2021:08:04 13:23:39'}
        with path.open('wb') as stream:
            stream.write(original[:-12])
            png_chunk(stream, b'eXIf', exif.tobytes()[6:])
            png_chunk(stream, b'iTXt', b'XML:com.adobe.xmp\0\0\0\0\0<xmp/>')
            stream.write(original[-12:])
        with patch.object(
            PngImagePlugin.PngImageFile, 'load', side_effect=AssertionError('pixels'),
        ):
            header = inspect_raster(path)
            self.assertEqual(header.size, (12, 16))
            self.assertEqual(header.source_metadata[0][315], 'Tail Owner')
            self.assertEqual(header.source_metadata[3]['xmp'], b'<xmp/>')

    def test_streaming_releases_previous_photo_before_decoding_next(self):
        paths = []
        for i in range(3):
            path = self.root / f'photo-{i}.png'
            Image.new('RGB', (100, 120), (i * 50, 0, 0)).save(path)
            paths.append(path)
        refs = []

        def decode(*args, **kwargs):
            gc.collect()
            self.assertTrue(all(ref() is None for ref in refs))
            result = read_raster(*args, **kwargs)
            refs.extend((weakref.ref(result), weakref.ref(result.pixels)))
            return result

        with patch('watermark_tool.preserved.read_raster', side_effect=decode) as mock:
            make_canvas(paths, self.root / 'combined.png', self.config())
        self.assertEqual(mock.call_count, 3)

    def test_native_16bit_png_preserves_channels_interlacing_and_color_key_alpha(self):
        for channels in (1, 2, 3, 4):
            values = np.random.default_rng(channels).integers(
                0, 65536, (12, 16, channels), dtype=np.uint16,
            )
            for interlace in (False, True):
                with self.subTest(channels=channels, interlace=interlace):
                    path = self.root / 'native.png'
                    with path.open('wb') as stream:
                        png.Writer(16, 12, bitdepth=16, greyscale=channels <= 2,
                                   alpha=channels in (2, 4), interlace=interlace).write(
                            stream, values.reshape(12, -1),
                        )
                    result = read_raster(path)
                    rgb = values[..., :1] if channels <= 2 else values[..., :3]
                    if channels <= 2:
                        rgb = np.repeat(rgb, 3, axis=-1)
                    np.testing.assert_array_equal(result.pixels, rgb)
                    if channels in (2, 4):
                        np.testing.assert_array_equal(result.alpha, values[..., -1])
                    else:
                        self.assertIsNone(result.alpha)
        for gray in (True, False):
            path = self.root / 'transparent.png'
            row = [1, 256, 65535] if gray else [1, 2, 3, 100, 200, 300]
            with path.open('wb') as stream:
                png.Writer(3 if gray else 2, 1, bitdepth=16, greyscale=gray,
                           transparent=256 if gray else (1, 2, 3)).write(stream, [row])
            result = read_raster(path)
            expected = [[65535, 0, 65535]] if gray else [[0, 65535]]
            np.testing.assert_array_equal(result.alpha, expected)

    def test_batch_cli_continues_after_failure_and_returns_nonzero(self):
        paths = [self.root / name for name in ('first 中文.jpg', 'broken.jpg', 'last "q".jpg')]
        for path in (paths[0], paths[2]):
            Image.new('RGB', (100, 100)).save(path)
        paths[1].write_bytes(b'broken')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'layout.py'), '--batch', '--include-gps-location', 'false',
             '--output-mode', 'original', *map(str, paths)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('成功处理 2 张照片，失败 1 张', result.stdout + result.stderr)
        for path in (paths[0], paths[2]):
            self.assertTrue(path.with_stem(path.stem + '_watermark').exists())
        self.assertFalse(paths[1].with_stem(paths[1].stem + '_watermark').exists())


class LocationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(exif_gps, 'LOCATION_CACHE', {}))
        self.enterContext(suppress_watermark_logs())
        self.result = {'address': {'city': '上海市', 'state': '上海'}, 'display_name': ''}

    def test_fallback_error_retains_location_and_caches_it(self):
        with patch.object(exif_gps, 'fetch_reverse_geocode_data',
                          side_effect=[self.result, TimeoutError('slow')]) as fetch:
            self.assertEqual(exif_gps.reverse_geocode_location(31, 121, 'en', 5), '上海市, 上海')
            self.assertEqual(exif_gps.reverse_geocode_location(31, 121, 'en', 5), '上海市, 上海')
            self.assertEqual(fetch.call_count, 2)

    def test_fallbacks_share_one_timeout_budget(self):
        with (
            patch.object(exif_gps.time, 'monotonic', side_effect=[100, 100, 102, 106]),
            patch.object(exif_gps, 'fetch_reverse_geocode_data', return_value=self.result) as fetch,
        ):
            self.assertEqual(exif_gps.reverse_geocode_location(31, 121, 'en', 5), '上海市, 上海')
        self.assertEqual([call.args[3] for call in fetch.call_args_list], [5, 3])

    def test_rate_limit_wait_is_included_in_budget(self):
        with (
            patch.object(exif_gps.time, 'monotonic', return_value=100.25),
            patch.object(exif_gps, 'LAST_LOCATION_LOOKUP_TIME', 100),
            patch.object(exif_gps.urllib.request, 'urlopen') as network,
            patch.object(exif_gps.time, 'sleep') as sleep,
            self.assertRaises(TimeoutError),
        ):
            exif_gps.fetch_reverse_geocode_data(31, 121, 'en', 0.5, 10)
        network.assert_not_called()
        sleep.assert_not_called()
