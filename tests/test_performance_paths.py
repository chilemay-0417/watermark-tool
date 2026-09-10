"""Pixel equivalence and failure coverage for sparse rendering and persistent GPS."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from watermark_tool import exif_gps, location_cache, preserved, utils
from watermark_tool.annotation_tiles import AnnotationTiles
from watermark_tool.cli import build_parser, config_from_args
from watermark_tool.config import LayoutConfig
from watermark_tool.drawing import load_font
from watermark_tool.raster import ColorSpec, read_raster
from watermark_tool.renderer import make_canvas


class PerformancePathsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.dict(os.environ, WATERMARK_CACHE_DIR=str(self.root / 'cache')))
        self.enterContext(patch.object(utils.LOGGER, 'disabled', True))

    def test_tiled_drawing_matches_pillow_at_boundaries_and_fractional_positions(self):
        size, background = (790, 610), (83, 127, 212)
        expected = Image.new('RGB', size, background)
        tiled = AnnotationTiles(size, background)
        self.addCleanup(tiled.close)
        font = load_font(38)
        logo = Image.fromarray(np.random.default_rng(1).integers(
            0, 256, (330, 310, 4), dtype=np.uint8,
        ))
        for canvas, draw in ((expected, ImageDraw.Draw(expected)), (tiled, tiled)):
            canvas.paste(logo, (-20, 248), logo)
            canvas.paste(logo, (493, 431), logo)
            draw.line((-30, 256, 820, 256), fill=(255, 10, 20), width=4)
            for xy in ((245, 242), (249.5, 506.5), (-5, -10), (780, 599)):
                draw.text(xy, 'Test gy', font=font, fill=(12, 34, 56))
        actual = Image.new('RGB', size, background)
        for position, tile in tiled.tiles.items():
            actual.paste(tile, position)
        np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))

    def test_native_copy_preserves_rgb_and_alpha_at_both_depths_without_full_canvas(self):
        for bits in (8, 16):
            dtype = np.uint8 if bits == 8 else np.uint16
            pixels = np.random.default_rng(bits).integers(
                0, 1 << bits, (513, 777, 4), dtype=dtype,
            )
            source, output = self.root / 'source.png', self.root / 'output.png'
            preserved.write_png(source, pixels, bits, ColorSpec(), {})
            original_new = Image.new
            allocations = []

            def allocate(mode, size, *args, allocations=allocations,
                         original_new=original_new, **kwargs):
                allocations.append(size)
                return original_new(mode, size, *args, **kwargs)

            converted_sizes = []
            original_convert = preserved.srgb_to_color

            def convert(values, target, converted_sizes=converted_sizes,
                        original_convert=original_convert):
                converted_sizes.append(values.shape[:2])
                return original_convert(values, target)

            with (patch.object(Image, 'new', side_effect=allocate),
                  patch.object(preserved, 'srgb_to_color', side_effect=convert),
                  patch.object(preserved, 'resize_samples', side_effect=AssertionError('resize'))):
                make_canvas([source], output, LayoutConfig(
                    output_mode='original', include_gps_location=False,
                    show_signature=False, signature_text='', line_length=30,
                ))
            raster = read_raster(output)
            # Locate the unique first source sample, then compare every native channel.
            y, x = np.argwhere(np.all(raster.pixels == pixels[0, 0, :3], axis=-1))[0]
            np.testing.assert_array_equal(raster.pixels[y:y+513, x:x+777], pixels[..., :3])
            np.testing.assert_array_equal(raster.alpha[y:y+513, x:x+777], pixels[..., 3])
            self.assertNotIn((777, 513), allocations)
            self.assertNotIn(raster.size, allocations)
            self.assertTrue(all(h <= 256 and w <= 256 for h, w in converted_sizes))

    def test_png_options_roundtrip_pixels_and_metadata_in_both_backends(self):
        source = self.root / 'source.png'
        Image.new('RGB', (310, 270), (117, 39, 81)).save(source)
        for mode in ('preserve', 'srgb'):
            results = []
            for compression in ('fast', 'balanced', 'small'):
                config = config_from_args(build_parser().parse_args([
                    str(source), '--png-compression', compression,
                    '--include-gps-location', 'false', '--color-mode', mode,
                ]))
                config.output_mode = 'original'
                output = self.root / f'{mode}-{compression}.png'
                make_canvas([source], output, config)
                with Image.open(output) as image:
                    results.append((np.asarray(image), image.info))
            for pixels, metadata in results[1:]:
                np.testing.assert_array_equal(pixels, results[0][0])
                self.assertEqual(metadata, results[0][1])
        # The native encoder must retain all 16-bit RGBA samples at every setting too.
        pixels = np.random.default_rng(9).integers(0, 65536, (35, 40, 4), dtype=np.uint16)
        for compression in ('fast', 'balanced', 'small'):
            output = self.root / f'{compression}-16.png'
            preserved.write_png(output, pixels, 16, ColorSpec(), {}, compression=compression)
            raster = read_raster(output)
            np.testing.assert_array_equal(raster.pixels, pixels[..., :3])
            np.testing.assert_array_equal(raster.alpha, pixels[..., 3])


class PersistentLocationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.dict(os.environ, WATERMARK_CACHE_DIR=str(self.root),
                                    WATERMARK_GPS_CACHE_DIR=str(self.root / 'gps')))
        self.enterContext(patch.object(exif_gps, 'LOCATION_CACHE', {}))
        self.enterContext(patch.object(utils.LOGGER, 'disabled', True))

    def test_cache_survives_new_process_and_language_is_separate(self):
        key = (31, 121, 'en')
        location_cache.cached_location(key, 'Shanghai')
        code = ('from watermark_tool.location_cache import cached_location; '
                'print(cached_location((31, 121, "en"))[0])')
        result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                text=True, check=True, timeout=10)
        self.assertEqual(result.stdout.strip(), 'Shanghai')
        with patch.object(exif_gps, 'fetch_reverse_geocode_data') as fetch:
            self.assertEqual(exif_gps.reverse_geocode_location(*key, 5), 'Shanghai')
        fetch.assert_not_called()
        self.assertIsNone(location_cache.cached_location((31, 121, 'zh')))

    def test_expiry_empty_failures_and_disabled_cache(self):
        key = (31, 121, 'en')
        with patch.object(location_cache.time, 'time', return_value=1000):
            location_cache.cached_location(key, 'Shanghai')
        self.assertIsNone(location_cache.cached_location(key))
        with patch.object(exif_gps, 'fetch_reverse_geocode_data', side_effect=TimeoutError):
            self.assertEqual(exif_gps.reverse_geocode_location(*key, 5), '')
        self.assertIsNone(location_cache.cached_location(key))
        with patch.dict(os.environ, WATERMARK_GPS_CACHE_DIR='off'):
            location_cache.cached_location(key, 'Shanghai')
            self.assertIsNone(location_cache.cached_location(key))

    def test_corruption_and_unwritable_directory_fall_back_to_network(self):
        directory = self.root / 'gps'
        directory.mkdir()
        (directory / 'locations.sqlite3').write_bytes(b'not sqlite')
        self.assertIsNone(location_cache.cached_location((1, 2, 'en')))
        blocked = self.root / 'blocked'
        blocked.write_text('not a directory')
        with (patch.dict(os.environ, WATERMARK_GPS_CACHE_DIR=str(blocked)),
              patch.object(exif_gps, 'fetch_reverse_geocode_data', return_value={
                  'address': {'city': 'Shanghai', 'state': 'Shanghai'},
              })):
            self.assertEqual(exif_gps.reverse_geocode_location(31, 121, 'en', 5), 'Shanghai')

    def test_cache_is_bounded_and_memory_entries_expire(self):
        with patch.object(location_cache, 'MAX_ENTRIES', 2):
            for lat in range(3):
                location_cache.cached_location((lat, 1, 'en'), str(lat))
        self.assertIsNone(location_cache.cached_location((0, 1, 'en')))
        exif_gps.LOCATION_CACHE[(31, 121, 'en')] = ('old', 0)
        with patch.object(exif_gps, 'fetch_reverse_geocode_data', return_value={
            'address': {'city': 'New', 'state': 'Place'},
        }):
            self.assertEqual(exif_gps.reverse_geocode_location(31, 121, 'en', 5), 'New, Place')

    def test_progress_logs_and_passes_filename_as_data_with_throttled_notifications(self):
        message = '正在处理第 2/3 张：中文 "photo".jpg'
        with (patch.object(utils.LOGGER, 'disabled', False),
              patch.object(utils.sys, 'platform', 'darwin'),
              patch.dict(os.environ, WATERMARK_FINDER_PROGRESS='1'),
              patch.object(utils, '_LAST_PROGRESS_NOTIFICATION', float('-inf')),
              patch('subprocess.run') as notify,
              self.assertLogs(utils.LOGGER, level='INFO') as logs):
            utils.progress(message)
            utils.progress('正在保存')
        self.assertIn(message, logs.output[0])
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(notify.call_args.args[0][-1], message)
        self.assertNotIn(message, notify.call_args.args[0][2])
