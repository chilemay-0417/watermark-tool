"""Theme parsing, inheritance, alpha masks, cache isolation and rendered pixels."""

from collections import OrderedDict
import os
from pathlib import Path
import re
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from tests import TestCase
from tests.test_color import p3_profile
from tests.test_layout import suppress_watermark_logs
from watermark_tool import asset_cache
from watermark_tool.assets import (
    colorize_signature, load_watermark_assets, prepare_logo_image, prepare_signature_mark,
)
from watermark_tool.cli import build_parser, config_from_args
from watermark_tool.config import COLOR_PRESETS, LayoutConfig, PhotoMetadata
from watermark_tool.renderer import make_canvas
from watermark_tool.preserved import write_png
from watermark_tool.raster import ColorSpec, read_raster, srgb_to_color
from watermark_tool.theme import parse_color


class PresetConfigurationTests(TestCase):
    def config_source(self, preset):
        path = Path(__file__).resolve().parents[1] / "src/watermark_tool/config.py"
        selector = 'BACKGROUND_COLOR, WATERMARK_COLOR = COLOR_PRESETS["' + (preset or "01") + '"]'
        source, count = re.subn(
            r'^#?\s?BACKGROUND_COLOR, WATERMARK_COLOR = COLOR_PRESETS\["\d+"\]$',
            selector if preset else "# " + selector, path.read_text(), flags=re.MULTILINE,
        )
        self.assertEqual(count, 1)
        source = re.sub(r'^    BACKGROUND_COLOR = .*$',
                        '    BACKGROUND_COLOR = "rgb(23, 34, 45)"', source, flags=re.MULTILINE)
        source = re.sub(r'^    WATERMARK_COLOR = .*$',
                        '    WATERMARK_COLOR = "gold"', source, flags=re.MULTILINE)
        return source, path

    def load_config(self, preset, module=None):
        source, path = self.config_source(preset)
        module = module or ModuleType("watermark_tool._preset_test_config")
        module.__file__ = str(path)
        module.__package__ = "watermark_tool"
        with patch.dict(sys.modules, {module.__name__: module}):
            exec(compile(source, str(path), "exec"), module.__dict__)
        return module

    def test_every_preset_takes_priority_over_manual_colors(self):
        for number, (background, watermark) in COLOR_PRESETS.items():
            with self.subTest(preset=number):
                cfg = self.load_config(number).LayoutConfig()
                self.assertEqual(cfg.background_color, parse_color(background))
                self.assertEqual(cfg.watermark_color, parse_color(watermark))

    def test_commenting_preset_enables_manual_colors(self):
        cfg = self.load_config(None).LayoutConfig()
        self.assertEqual(cfg.background_color, (23, 34, 45))
        self.assertEqual(cfg.watermark_color, (255, 215, 0))

    def test_reload_does_not_reuse_previous_preset(self):
        module = self.load_config("09")
        cfg = self.load_config(None, module).LayoutConfig()
        self.assertEqual(cfg.background_color, (23, 34, 45))
        self.assertEqual(cfg.watermark_color, (255, 215, 0))


class ThemeParsingTests(TestCase):
    def test_color_syntaxes_have_identical_rgb_values(self):
        for value in ("#282828", "rgb(40, 40, 40)", " RGB(40,40,40) ", (40, 40, 40)):
            self.assertEqual(parse_color(value), (40, 40, 40))
        self.assertEqual(parse_color(" MidnightBlue "), (25, 25, 112))
        self.assertEqual(parse_color("rebeccapurple"), (102, 51, 153))
        self.assertEqual(parse_color("#abc"), (170, 187, 204))
        for name in ImageColor.colormap:
            self.assertEqual(parse_color(name), ImageColor.getrgb(name))

    def test_invalid_values_report_the_setting(self):
        for value in (None, "unknown", "rgb(256, 0, 0)", "rgb(-1, 0, 0)", "#abcd",
                      "rgba(0,0,0,1)", (0, 0), (0, 0, 0, 255), (1.5, 0, 0),
                      (True, 0, 0), (float("nan"), 0, 0), "rgb(1.5, 0, 0)"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "BACKGROUND_COLOR"):
                LayoutConfig(background_color=value)

    def test_white_and_colored_background_defaults_and_individual_overrides(self):
        white = LayoutConfig(background_color="rgb(255, 255, 255)", watermark_color="black",
                             line_color=None, date_color=None, info_color=None,
                             signature_color=None)
        dark = LayoutConfig(background_color="dimgray", watermark_color="black",
                            line_color=None, date_color=None, info_color=None, signature_color=None)
        for field in ("line_color", "date_color", "info_color", "signature_color"):
            self.assertEqual(getattr(white, field), (0, 0, 0))
            self.assertEqual(getattr(dark, field), (0, 0, 0))
        light_marks = LayoutConfig(background_color="dimgray", watermark_color="white",
                                   line_color=None, date_color=None, info_color=None,
                                   signature_color=None)
        for field in ("line_color", "date_color", "info_color", "signature_color"):
            self.assertEqual(getattr(light_marks, field), (255, 255, 255))
        custom = LayoutConfig(background_color="midnightblue", watermark_color="gold",
                              line_color="tomato", date_color="rgb(1,2,3)",
                              info_color="#abcdef", signature_color="cyan")
        self.assertEqual(custom.line_color, (255, 99, 71))
        self.assertEqual(custom.date_color, (1, 2, 3))
        self.assertEqual(custom.info_color, (171, 205, 239))
        self.assertEqual(custom.signature_color, (0, 255, 255))

    def test_cli_watermark_color_controls_only_inherited_items(self):
        defaults = LayoutConfig(background_color="white", watermark_color="black",
                                line_color=None, date_color=None, info_color="gold",
                                signature_color=None)
        parser = build_parser(defaults)
        cfg = config_from_args(parser.parse_args(["photo.jpg", "--background-color", "dimgray"]))
        self.assertEqual(cfg.line_color, (0, 0, 0))
        self.assertEqual(cfg.info_color, (255, 215, 0))
        cfg = config_from_args(parser.parse_args([
            "photo.jpg", "--background-color", "rgb(20, 30, 40)",
            "--watermark-color", "cyan", "--signature-color", "red",
        ]))
        self.assertEqual(cfg.background_color, (20, 30, 40))
        self.assertEqual(cfg.date_color, (0, 255, 255))
        self.assertEqual(cfg.signature_color, (255, 0, 0))
        self.assertEqual(cfg.line_color, (0, 255, 255))
        self.assertEqual(cfg.info_color, (255, 215, 0))

    def test_uniform_color_requires_an_explicit_color(self):
        with self.assertRaisesRegex(ValueError, "WATERMARK_COLOR"):
            LayoutConfig(watermark_color=None)


class ThemeAssetTests(TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.enterContext(patch.dict(os.environ, WATERMARK_CACHE_DIR=str(self.root / "cache")))
        self.enterContext(patch.object(asset_cache, "_MEMORY", OrderedDict()))
        self.enterContext(suppress_watermark_logs())

    def test_white_paper_is_transparent_and_antialiasing_is_retained(self):
        source = Image.new("RGBA", (3, 1))
        source.putdata([(255, 255, 255, 255), (0, 0, 0, 255), (128, 128, 128, 255)])
        with colorize_signature(source, (255, 255, 255)) as result:
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255, 0))
            self.assertEqual(result.getpixel((1, 0)), (255, 255, 255, 255))
            self.assertEqual(result.getpixel((2, 0)), (255, 255, 255, 127))

    def test_transparent_signature_uses_alpha_even_for_white_strokes(self):
        source = Image.new("RGBA", (3, 1))
        source.putdata([(255, 255, 255, 0), (255, 255, 255, 255), (30, 40, 50, 93)])
        with colorize_signature(source, (255, 215, 0)) as result:
            self.assertEqual(result.getchannel("A").tobytes(), source.getchannel("A").tobytes())
            self.assertEqual(result.getpixel((1, 0)), (255, 215, 0, 255))

    def test_switching_theme_invalidates_signature_cache_without_changing_logo(self):
        source = Image.new("RGB", (160, 55), "white")
        ImageDraw.Draw(source).rectangle((20, 10, 100, 40), fill="black")
        signature_path = self.root / "signature.png"
        source.save(signature_path)
        logo_path = self.root / "logo.png"
        Image.new("RGBA", (70, 55), (177, 20, 40, 173)).save(logo_path)
        expected_logo = prepare_logo_image(logo_path).tobytes()
        with patch("watermark_tool.assets.SIGNATURE_FILE", signature_path.name):
            for color in ("white", "gold", "cyan", "white"):
                cfg = LayoutConfig(background_color="dimgray", signature_color=color)
                marks = load_watermark_assets(self.root, cfg, logo_path=logo_path)
                self.assertEqual(marks.logo.tobytes(), expected_logo)
                pixels = np.asarray(marks.signature)
                self.assertTrue(np.any(pixels[:, :, 3] == 0))
                self.assertTrue(np.any(pixels[:, :, 3] == 255))
                np.testing.assert_array_equal(pixels[:, :, :3][pixels[:, :, 3] == 255][0],
                                              parse_color(color))
                # Also force disk-cache reload, not only the in-process cache.
                asset_cache._MEMORY.clear()

    def test_text_signature_obeys_its_own_color(self):
        cfg = LayoutConfig(show_signature=False, signature_text="CHILE",
                           signature_color="gold", info_color="cyan",
                           signature_font=ImageFont.load_default(size=30))
        image = prepare_signature_mark(self.root, cfg)
        pixels = np.asarray(image)
        np.testing.assert_array_equal(pixels[:, :, :3][pixels[:, :, 3] == 255][0], (255, 215, 0))


class ThemeRenderingTests(TestCase):
    def test_colored_frame_retains_16bit_p3_photo_samples(self):
        with tempfile.TemporaryDirectory() as directory, suppress_watermark_logs():
            root = Path(directory)
            color = ColorSpec(icc=p3_profile())
            samples = np.full((150, 200, 3), (20000, 30000, 40000), dtype=np.uint16)
            source = root / "p3-16.png"
            write_png(source, samples, 16, color, {})
            output = root / "framed.png"
            cfg = LayoutConfig(output_mode="original", background_color="midnightblue",
                               show_signature=False, signature_text="", line_length=40,
                               line_left_offset=0, date_font_size=15, include_gps_location=False)
            make_canvas([source], output, cfg)
            result = read_raster(output)
            expected = np.rint(srgb_to_color(
                np.array([[[25, 25, 112]]], dtype=np.float32) / 255, color,
            ) * 65535).astype(np.uint16)[0, 0]
            self.assertEqual(result.bits, 16)
            self.assertEqual(result.color.key(), color.key())
            np.testing.assert_array_equal(result.pixels[0, 0], expected)
            self.assertEqual(np.count_nonzero(np.all(
                result.pixels == (20000, 30000, 40000), axis=-1)), 150 * 200)

    def test_background_line_and_photo_pixels_in_all_layouts_and_both_backends(self):
        with tempfile.TemporaryDirectory() as directory, suppress_watermark_logs():
            root = Path(directory)
            source = root / "photo.png"
            Image.new("RGB", (500, 350), (123, 45, 67)).save(source)
            metadata = PhotoMetadata("2026-09-18", "", "", "", "")
            for mode in ("video", "adaptive", "original"):
                for backend in ("srgb", "preserve"):
                    with self.subTest(mode=mode, backend=backend):
                        cfg = LayoutConfig(
                            output_mode=mode, color_mode=backend, background_color="midnightblue",
                            watermark_color="white", line_color="gold",
                            photo_height=350, line_length=100,
                            line_left_offset=0, date_font_size=20, include_gps_location=False,
                            show_signature=False, signature_text="",
                        )
                        output = root / f"{mode}-{backend}.png"
                        with patch("watermark_tool.renderer.read_photo_metadata",
                                   return_value=metadata):
                            make_canvas([source], output, cfg)
                        with Image.open(output) as image:
                            pixels = np.asarray(image)
                            self.assertEqual(image.getpixel((0, 0))[:3], (25, 25, 112))
                            line = pixels[image.height - cfg.line_bottom_margin, :, :3]
                            self.assertTrue(np.any(np.all(line == (255, 215, 0), axis=-1)))
                            self.assertTrue(np.any(np.all(
                                pixels[:, :, :3] == (123, 45, 67), axis=-1)))
                            footer = pixels[image.height - cfg.line_bottom_margin + 20:, :, :3]
                            self.assertTrue(np.any(np.all(footer == (255, 255, 255), axis=-1)))
