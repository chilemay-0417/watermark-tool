"""Verify that bundled logos work without the optional SVG runtime."""

import builtins
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watermark_tool.assets import open_logo_image, prepare_logo_image
from watermark_tool.config import LOGO_HEIGHT


ROOT = Path(__file__).resolve().parents[1]


class LogoDependencyTests(unittest.TestCase):
    def test_bundled_png_logos_do_not_import_svg_runtime(self):
        original_import = builtins.__import__

        def without_svg(name, *args, **kwargs):
            if name.split('.')[0] in {'cairosvg', 'cairocffi', 'cairo'}:
                raise AssertionError(f'PNG logo tried to import {name}')
            return original_import(name, *args, **kwargs)

        logos = list((ROOT / 'assets').glob('*.png'))
        self.assertTrue(logos)
        with patch('builtins.__import__', side_effect=without_svg):
            for path in logos:
                with self.subTest(logo=path.name), open_logo_image(path) as image:
                    self.assertEqual(image.mode, 'RGBA')
                    self.assertGreaterEqual(image.height, LOGO_HEIGHT * 4)
                    self.assertIsNotNone(image.getbbox())

    def test_missing_svg_package_or_native_library_has_actionable_error(self):
        original_import = builtins.__import__
        for failure in (ImportError('No module named cairosvg'),
                        OSError('no library called cairo was found')):
            def without_svg(name, *args, failure=failure, **kwargs):
                if name == 'cairosvg':
                    raise failure
                return original_import(name, *args, **kwargs)

            with (self.subTest(failure=type(failure).__name__),
                  patch('builtins.__import__', side_effect=without_svg),
                  self.assertRaises(RuntimeError) as caught):
                open_logo_image('custom.svg')
            self.assertIn('PNG', str(caught.exception))
            self.assertIn('.[svg]', str(caught.exception))
            self.assertIn('Cairo 原生库', str(caught.exception))
            self.assertIs(caught.exception.__cause__, failure)

    def test_custom_svg_renders_when_optional_runtime_is_available(self):
        try:
            import cairosvg  # noqa: F401
        except (ImportError, OSError):
            self.skipTest('Optional CairoSVG runtime is not installed')

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.svg'
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                '<rect x="25" y="25" width="50" height="50" fill="red"/></svg>'
            )
            with prepare_logo_image(path) as image:
                self.assertEqual(image.size, (LOGO_HEIGHT, LOGO_HEIGHT))
                self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
                center = LOGO_HEIGHT // 2
                self.assertEqual(image.getpixel((center, center)), (255, 0, 0, 255))


if __name__ == '__main__':
    unittest.main()
