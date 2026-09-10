"""Behavioral regressions for shared metadata reads and atomic image/cache writes."""

from collections import OrderedDict
from pathlib import Path
import tempfile
from tests import TestCase
from unittest.mock import patch

from PIL import Image, ImageFont, PngImagePlugin

from tests.test_layout import suppress_watermark_logs
from watermark_tool import asset_cache, metadata
from watermark_tool.assets import prepare_logo_image
from watermark_tool.config import LayoutConfig
from watermark_tool.exif_gps import read_exif_all, read_photo_metadata
from watermark_tool.metadata import read_source_metadata
from watermark_tool.preserved import png_chunk
from watermark_tool.renderer import load_photo_items, make_canvas


class SharedIOTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.enterContext(suppress_watermark_logs())

    def config(self, **changes):
        return LayoutConfig(**{
            'output_mode': 'original', 'include_gps_location': False,
            'show_signature': False, 'signature_text': '',
            'line_length': 12, 'line_left_offset': 0, 'date_font_size': 10,
            **changes,
        })

    def test_replace_failure_preserves_output_and_cleans_temporary_in_all_backends(self):
        source = self.root / 'source.png'
        Image.new('RGB', (16, 12)).save(source)
        for mode in ('srgb', 'preserve'):
            for suffix in ('png', 'jpg'):
                with self.subTest(mode=mode, suffix=suffix):
                    output = self.root / f'output.{suffix}'
                    output.write_bytes(b'previous output')
                    with (
                        patch(
                            'watermark_tool.utils.os.replace',
                            side_effect=OSError('replace failed'),
                        ),
                        self.assertRaisesRegex(OSError, 'replace failed'),
                    ):
                        make_canvas([source], output, self.config(color_mode=mode))
                    self.assertEqual(output.read_bytes(), b'previous output')
                    self.assertFalse(list(self.root.glob('.watermark-*')))

    def test_cache_replace_failure_still_returns_asset_without_partial_cache_files(self):
        source = self.root / 'logo.png'
        Image.new('RGB', (16, 12), 'red').save(source)
        cache = self.root / 'cache'
        with (
            patch.dict('os.environ', WATERMARK_CACHE_DIR=str(cache)),
            patch.object(asset_cache, '_MEMORY', OrderedDict()),
            patch('watermark_tool.utils.os.replace', side_effect=OSError('cache full')),
        ):
            with prepare_logo_image(source) as logo:
                self.assertEqual(logo.getpixel((20, 20)), (255, 0, 0, 255))
        self.assertEqual(list(cache.iterdir()), [])

    def test_deferred_png_reads_metadata_once_and_reuses_it_for_display(self):
        source = self.root / 'late-exif.png'
        Image.new('RGB', (16, 12)).save(source)
        encoded = source.read_bytes()
        exif = Image.Exif()
        exif[271], exif[272], exif[274] = 'Nikon', 'Z 5', 6
        exif[34665] = {36867: '2021:08:04 13:23:39', 34855: 100}
        with source.open('wb') as stream:
            stream.write(encoded[:-12])
            png_chunk(stream, b'eXIf', exif.tobytes()[6:])
            stream.write(encoded[-12:])
        cfg = self.config(info_font=ImageFont.load_default())
        with (
            patch.object(PngImagePlugin.PngImageFile, 'load', side_effect=AssertionError('pixels')),
            patch.object(metadata, 'png_metadata', wraps=metadata.png_metadata) as read,
        ):
            item, = load_photo_items([source], cfg, defer_pixels=True)
            self.assertEqual(read.call_count, 1)
            self.assertIsNone(item.image)
            self.assertEqual(item.source_size, (12, 16))
            self.assertEqual((item.metadata.make, item.metadata.model), ('Nikon', 'Z 5'))
            self.assertEqual(item.metadata.settings, 'ISO100')
            self.assertTrue(item.metadata.date)
            direct = read_photo_metadata(source, include_gps_location=False)
            self.assertEqual(item.metadata, direct)
        with patch(
            'watermark_tool.exif_gps.read_source_metadata',
            side_effect=AssertionError('reread'),
        ):
            cached = read_photo_metadata(
                source, source=item.source_metadata, include_gps_location=False,
            )
            self.assertEqual(cached, direct)

    def test_malformed_ifd_does_not_discard_healthy_camera_and_capture_metadata(self):
        source = self.root / 'exif.jpg'
        exif = Image.Exif()
        exif[271] = 'Nikon'
        exif[34665] = {34855: 100}
        exif[34853] = {1: 'N', 2: (31, 0, 0), 3: 'E', 4: (121, 0, 0)}
        Image.new('RGB', (16, 12)).save(source, exif=exif)
        original_get_ifd = Image.Exif.get_ifd
        for broken in (34665, 34853):
            def read_ifd(exif, tag, broken=broken):
                if tag == broken:
                    raise ValueError('malformed IFD')
                return original_get_ifd(exif, tag)

            with self.subTest(broken=broken), patch.object(Image.Exif, 'get_ifd', read_ifd):
                snapshot = read_source_metadata(source)
                flattened = read_exif_all(source, source=snapshot)
                self.assertEqual(flattened[271], 'Nikon')
                if broken == 34853:
                    self.assertEqual(flattened[34855], 100)
                    self.assertEqual(snapshot[2], {})
                else:
                    self.assertEqual(flattened[34853][1], 'N')
                    self.assertEqual(snapshot[1], {})

    def test_missing_or_corrupt_file_has_empty_display_exif(self):
        corrupt = self.root / 'broken.png'
        corrupt.write_bytes(b'broken')
        for source in (self.root / 'missing.png', corrupt):
            with self.subTest(source=source):
                self.assertEqual(read_exif_all(source), {})
