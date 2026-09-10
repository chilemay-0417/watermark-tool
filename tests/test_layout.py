import contextlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from watermark_tool.config import LayoutConfig, PhotoMetadata, WatermarkAssets
from watermark_tool.drawing import (
    load_signature_font,
    make_centered_text_mark_image,
    open_image_correct_orientation,
    should_prefer_cjk_font,
)
from watermark_tool.exif_gps import (
    LOCATION_CACHE,
    format_aperture,
    format_camera_settings,
    format_exposure_time,
    format_focal_length,
    format_gps_location,
    format_location_from_address,
    format_iso,
    gps_coord_to_decimal,
    reverse_geocode_location,
)
from watermark_tool import exif_gps
from watermark_tool import config
from watermark_tool.cli import parse_bool
from watermark_tool.cli import make_default_output_path, make_output_path_from_original
from watermark_tool.layout import (
    calculate_layout_metrics,
    validate_layout_params,
)
from watermark_tool.brands import (
    choose_logo_by_camera,
    resolve_logo_path,
    select_logo_paths_for_items,
)
from watermark_tool.assets import (
    load_watermark_assets,
    prepare_logo_image,
)
from watermark_tool.renderer import make_canvas
from watermark_tool.utils import LOGGER


@contextlib.contextmanager
def suppress_watermark_logs():
    previous_disabled = LOGGER.disabled
    LOGGER.disabled = True

    try:
        yield
    finally:
        LOGGER.disabled = previous_disabled


def write_test_brand_rules(base_dir):
    base_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Nikon.png")
    Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Apple.png")
    (base_dir / "brands.json").write_text(
        json.dumps(
            {
                "brands": [
                    {
                        "display_name": "Nikon",
                        "logo": "Nikon.png",
                        "keywords": ["nikon", "nikkor", "z 5", "z 8"],
                    },
                    {
                        "display_name": "Apple",
                        "logo": "Apple.png",
                        "keywords": ["apple", "iphone", "ipad"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


class LayoutFormattingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, WATERMARK_GPS_CACHE_DIR="off"))

    def test_default_output_path_uses_unified_watermark_suffix(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)

            self.assertEqual(
                make_output_path_from_original(base_dir / "input.heic"),
                base_dir / "input_watermark.jpg",
            )
            self.assertEqual(
                make_default_output_path(
                    [
                        base_dir / "left.jpg",
                        base_dir / "right.jpg",
                    ]
                ),
                base_dir / "left_right_watermark.jpg",
            )

    def test_default_output_path_avoids_overwriting_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            (base_dir / "input_watermark.jpg").write_text("", encoding="utf-8")

            self.assertEqual(
                make_default_output_path([base_dir / "input.jpg"]),
                base_dir / "input_watermark_2.jpg",
            )

    def test_defaults_do_not_force_font_path(self):
        cfg = LayoutConfig()

        self.assertIsNone(cfg.font_path)
        self.assertIsNone(cfg.location_font_path)

    def test_missing_gps_formats_as_empty_location(self):
        self.assertEqual(format_gps_location({}), "")

    def test_invalid_gps_container_has_empty_location(self):
        exif_data = {
            exif_gps.TAG_GPS_INFO: {
                exif_gps.GPS_LATITUDE_REF: "N",
                exif_gps.GPS_LONGITUDE_REF: "E",
            }
        }

        self.assertEqual(format_gps_location(exif_data), "")

    def test_english_reverse_geocode_prefers_ascii_fallback(self):
        calls = []
        original_fetch = exif_gps.fetch_reverse_geocode_data
        LOCATION_CACHE.clear()

        def fake_fetch(lat, lon, language, timeout, zoom):
            calls.append(zoom)

            if zoom == 10:
                return {
                    "address": {"town": "佘山镇"},
                    "display_name": "佘山镇, China",
                }

            return {
                "address": {
                    "town": "Sheshan",
                    "city": "Songjiang District",
                },
                "display_name": "Sheshan, Songjiang District, Shanghai, China",
            }

        try:
            exif_gps.fetch_reverse_geocode_data = fake_fetch
            location = reverse_geocode_location(31.1, 121.1, "en", 5)
        finally:
            exif_gps.fetch_reverse_geocode_data = original_fetch
            LOCATION_CACHE.clear()

        self.assertEqual(location, "Sheshan, Songjiang")
        self.assertEqual(calls, [10, 16])

    def test_location_suffixes_are_removed(self):
        location = format_location_from_address(
            {
                "town": "Sheshan Town",
                "city": "Songjiang District",
            },
            "Sheshan Town, Songjiang District, Shanghai, China",
        )

        self.assertEqual(location, "Sheshan, Songjiang")

    def test_parse_bool_accepts_common_values(self):
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("yes"))
        self.assertTrue(parse_bool("1"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("no"))
        self.assertFalse(parse_bool("0"))

    def test_format_camera_values(self):
        self.assertEqual(format_exposure_time((1, 400)), "1/400s")
        self.assertEqual(format_exposure_time((8, 7435)), "1/929s")
        self.assertEqual(format_exposure_time((4, 3565)), "1/891s")
        self.assertEqual(format_exposure_time(2), "2s")
        self.assertEqual(format_aperture((28, 10)), "f/2.8")
        self.assertEqual(format_iso([100]), "ISO100")
        self.assertEqual(format_focal_length((50, 1)), "50mm")

    def test_shutter_preserves_fractional_seconds(self):
        for value, expected in (
            (0.8, "0.8s"), ((4, 5), "0.8s"), (0.6, "0.6s"),
            (0.4, "0.4s"), (0.3, "0.3s"), ((5, 4), "1.25s"),
            (1.6, "1.6s"), (2.5, "2.5s"), (30, "30s"),
        ):
            with self.subTest(value=value):
                self.assertEqual(format_exposure_time(value), expected)

    def test_shutter_keeps_accurate_reciprocals_and_bounds_rounding_error(self):
        for denominator in (2, 3, 4, 8, 15, 30, 125, 180, 400, 1000, 8000):
            self.assertEqual(format_exposure_time((1, denominator)), f"1/{denominator}s")
        for value in (0.001059, 0.00098, 0.009, 0.07, 0.13, 0.4, 0.6, 0.8, 1.25):
            text = format_exposure_time(value).removesuffix("s")
            rendered = 1 / int(text[2:]) if text.startswith("1/") else float(text)
            self.assertLessEqual(abs(rendered - value) / value, 0.001)

    def test_invalid_shutter_values_are_omitted(self):
        for value in (None, "", "invalid", 0, -1, (1, 0), float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertEqual(format_exposure_time(value), "")

    def test_camera_settings_prefers_35mm_equivalent_focal_length(self):
        exif = {
            exif_gps.TAG_FOCAL_LENGTH: 2.71484375,
            exif_gps.TAG_FOCAL_LENGTH_35MM: 30,
            exif_gps.TAG_F_NUMBER: 1.9,
            exif_gps.TAG_EXPOSURE_TIME: (1, 180),
            exif_gps.TAG_ISO: 20,
        }
        self.assertEqual(format_camera_settings(exif), "30mm f/1.9 1/180s ISO20")
        exif[exif_gps.TAG_FOCAL_LENGTH] = 4.75
        exif[exif_gps.TAG_FOCAL_LENGTH_35MM] = 26
        self.assertTrue(format_camera_settings(exif).startswith("26mm "))

    def test_missing_or_invalid_equivalent_focal_length_falls_back_to_actual_focal_length(self):
        for value in (None, 0, "0", "", "unknown", -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                exif = {
                    exif_gps.TAG_FOCAL_LENGTH: 6.83,
                    exif_gps.TAG_FOCAL_LENGTH_35MM: value,
                    exif_gps.TAG_F_NUMBER: 1.85,
                    exif_gps.TAG_ISO: 49,
                }
                self.assertEqual(format_camera_settings(exif), "6.8mm f/1.9 ISO49")
        self.assertEqual(format_camera_settings({exif_gps.TAG_FOCAL_LENGTH: 6.83}), "6.8mm")

    def test_camera_settings_omits_focal_length_when_both_values_are_invalid(self):
        for value in (None, 0, -1, "invalid", float("nan"), float("inf")):
            with self.subTest(value=value):
                exif = {
                    exif_gps.TAG_FOCAL_LENGTH_35MM: value,
                    exif_gps.TAG_FOCAL_LENGTH: value,
                    exif_gps.TAG_ISO: 49,
                }
                self.assertEqual(format_camera_settings(exif), "ISO49")

    def test_gps_coordinate_conversion(self):
        coord = gps_coord_to_decimal(((31, 1), (13, 1), (30, 1)), "N")
        self.assertAlmostEqual(coord, 31.225, places=6)

        coord = gps_coord_to_decimal(((121, 1), (28, 1), (0, 1)), "W")
        self.assertAlmostEqual(coord, -121.466666, places=5)

    def test_choose_logo_by_camera(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            write_test_brand_rules(base_dir)

            with patch.dict(
                "os.environ",
                {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
            ):
                self.assertEqual(
                    choose_logo_by_camera("NIKON CORPORATION", "NIKON Z 5", base_dir),
                    base_dir / "Nikon.png",
                )
                self.assertEqual(
                    choose_logo_by_camera("Apple", "iPhone 15 Pro", base_dir),
                    base_dir / "Apple.png",
                )
                with suppress_watermark_logs():
                    self.assertIsNone(choose_logo_by_camera("", "", base_dir))

    def test_choose_logo_by_camera_skips_rule_when_logo_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            (base_dir / "brands.json").write_text(
                json.dumps(
                    {
                        "brands": [
                            {
                                "display_name": "Canon",
                                "logo": "Canon_400.jpg",
                                "keywords": ["canon"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                self.assertIsNone(choose_logo_by_camera("Canon", "EOS R5", base_dir))

    def test_model_specific_rule_can_override_huawei_make_for_honor(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Honor.png")
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Huawei.png")
            (base_dir / "brands.json").write_text(
                json.dumps(
                    {
                        "brands": [
                            {
                                "display_name": "Honor",
                                "logo": "Honor.png",
                                "keywords": ["honor", "yal-", "knt-"],
                            },
                            {
                                "display_name": "Huawei",
                                "logo": "Huawei.png",
                                "keywords": ["huawei"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
            ):
                self.assertEqual(
                    choose_logo_by_camera("HUAWEI", "YAL-AL00", base_dir),
                    base_dir / "Honor.png",
                )
                self.assertEqual(
                    choose_logo_by_camera("HUAWEI", "KNT-AL10", base_dir),
                    base_dir / "Honor.png",
                )

    def test_specific_dji_l2d_rule_beats_generic_hasselblad_keyword(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "DJI.png")
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Hasselblad.png")
            (base_dir / "brands.json").write_text(
                json.dumps(
                    {
                        "brands": [
                            {
                                "display_name": "Hasselblad",
                                "logo": "Hasselblad.png",
                                "keywords": ["hasselblad"],
                            },
                            {
                                "display_name": "DJI",
                                "logo": "DJI.png",
                                "keywords": ["dji", "hasselblad l2d"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
            ):
                self.assertEqual(
                    choose_logo_by_camera("DJI", "Hasselblad L2D-20c", base_dir),
                    base_dir / "DJI.png",
                )

    def test_make_brand_beats_other_brand_model_series_keyword(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Fujifilm.png")
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Vivo.png")
            (base_dir / "brands.json").write_text(
                json.dumps(
                    {
                        "brands": [
                            {
                                "display_name": "Fujifilm",
                                "logo": "Fujifilm.png",
                                "keywords": ["fujifilm", "x100"],
                            },
                            {
                                "display_name": "vivo",
                                "logo": "Vivo.png",
                                "keywords": ["vivo"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
            ):
                self.assertEqual(
                    choose_logo_by_camera("vivo", "vivo X100 Pro", base_dir),
                    base_dir / "Vivo.png",
                )

    def test_short_model_keyword_requires_word_boundary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Nikon.png")
            (base_dir / "brands.json").write_text(
                json.dumps(
                    {
                        "brands": [
                            {
                                "display_name": "Nikon",
                                "logo": "Nikon.png",
                                "keywords": ["nikon", "z9"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                self.assertIsNone(choose_logo_by_camera("", "AZ9Camera", base_dir))
                self.assertEqual(
                    choose_logo_by_camera("", "Nikon Z9", base_dir),
                    base_dir / "Nikon.png",
                )

    def test_old_400_logo_rule_falls_back_to_new_png_filename(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            Image.new("RGB", (10, 10), (255, 255, 255)).save(base_dir / "Canon.png")

            self.assertEqual(
                resolve_logo_path(base_dir, "Canon_400.jpg"),
                base_dir / "Canon.png",
            )

    def test_logo_is_scaled_to_fixed_height_before_rotation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            logo_path = Path(tmp_dir) / "Wide.png"
            Image.new("RGBA", (200, 40), (255, 255, 255, 255)).save(logo_path)

            logo = prepare_logo_image(logo_path)

        self.assertEqual(logo.size[0], config.LOGO_HEIGHT)

    def test_signature_font_prefers_cjk_for_chinese_text(self):
        self.assertFalse(should_prefer_cjk_font("Shot by Chile"))
        self.assertTrue(should_prefer_cjk_font("智利拍摄"))

    def test_signature_font_defaults_to_expected_macos_faces(self):
        english_font = load_signature_font(24, text="Shot by Chile")
        chinese_font = load_signature_font(24, text="智利拍摄")

        self.assertIn("Courier", english_font.getname()[0])
        self.assertEqual(chinese_font.getname()[0], "Heiti SC")

    def test_signature_text_mark_uses_fixed_transparent_height_before_rotation(self):
        font = ImageFont.load_default()
        mark = make_centered_text_mark_image(
            "CHILE",
            font,
            (0, 0, 0),
            tracking=1,
            mark_height=config.LOGO_HEIGHT,
        )

        self.assertIsNotNone(mark)
        self.assertEqual(mark.size[0], config.LOGO_HEIGHT)

    def test_invalid_signature_font_size_is_rejected(self):
        cfg = LayoutConfig(signature_font_size=0)

        with self.assertRaisesRegex(ValueError, "signature_font_size"):
            validate_layout_params(1, cfg)

    def test_raw_input_is_rejected_before_decoding(self):
        with self.assertRaisesRegex(ValueError, "不再支持 RAW"):
            open_image_correct_orientation("input.dng")

    def test_signature_text_replaces_signature_image_when_signature_is_hidden(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            cfg = LayoutConfig(show_signature=False, signature_text="CHILE")
            cfg.signature_font = ImageFont.load_default()

            with suppress_watermark_logs():
                assets = load_watermark_assets(
                    base_dir=base_dir,
                    config=cfg,
                    logo_plan=[(None, True)],
                )

        self.assertIsNotNone(assets.signature)
        self.assertEqual(assets.signature.size[0], config.LOGO_HEIGHT)
        self.assertTrue(assets.photo_marks[0].include_signature)

    def test_signature_can_be_fully_hidden(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            cfg = LayoutConfig(show_signature=False, signature_text="")

            with suppress_watermark_logs():
                assets = load_watermark_assets(
                    base_dir=base_dir,
                    config=cfg,
                    logo_plan=[(None, True)],
                )

        self.assertIsNone(assets.signature)
        self.assertFalse(assets.photo_marks[0].include_signature)

    def test_multi_photo_logo_keeps_signature_on_rightmost_when_any_photo_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            write_test_brand_rules(base_dir)
            items = [
                SimpleNamespace(metadata=SimpleNamespace(make="", model="")),
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 5")
                ),
            ]

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                logo_plan = select_logo_paths_for_items(items, base_dir)

            self.assertEqual(
                logo_plan,
                [
                    (None, False),
                    (base_dir / "Nikon.png", True),
                ],
            )

    def test_multi_photo_same_device_uses_logo_only_on_rightmost(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            write_test_brand_rules(base_dir)
            items = [
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 5")
                ),
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 5")
                ),
            ]

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                logo_plan = select_logo_paths_for_items(items, base_dir)

            self.assertEqual(
                logo_plan,
                [
                    (None, False),
                    (base_dir / "Nikon.png", True),
                ],
            )

    def test_multi_photo_different_devices_adds_each_logo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            write_test_brand_rules(base_dir)
            items = [
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 5")
                ),
                SimpleNamespace(metadata=SimpleNamespace(make="Apple", model="iPhone 15 Pro")),
            ]

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                logo_plan = select_logo_paths_for_items(items, base_dir)

            self.assertEqual(
                logo_plan,
                [
                    (base_dir / "Nikon.png", False),
                    (base_dir / "Apple.png", True),
                ],
            )

    def test_multi_photo_same_brand_different_models_adds_each_logo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            write_test_brand_rules(base_dir)
            items = [
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 5")
                ),
                SimpleNamespace(
                    metadata=SimpleNamespace(make="NIKON CORPORATION", model="NIKON Z 8")
                ),
            ]

            with (
                patch.dict(
                    "os.environ",
                    {"WATERMARK_BRANDS_FILE": str(base_dir / "brands.json")},
                ),
                suppress_watermark_logs(),
            ):
                logo_plan = select_logo_paths_for_items(items, base_dir)

            self.assertEqual(
                logo_plan,
                [
                    (base_dir / "Nikon.png", False),
                    (base_dir / "Nikon.png", True),
                ],
            )


class LayoutCalculationTests(unittest.TestCase):
    def test_equal_margin_layout_uses_top_margin_as_photo_gap(self):
        cfg = LayoutConfig(
            photo_height=1850,
            line_bottom_margin=110,
            output_mode="adaptive",
        )
        items = [
            SimpleNamespace(image=SimpleNamespace(size=(2771, 1850))),
        ]
        assets = WatermarkAssets(
            signature=SimpleNamespace(size=(55, 120)),
            logo=None,
            logo_name=None,
        )

        metrics = calculate_layout_metrics(items, cfg, assets)

        self.assertEqual(metrics.photo_top, 100)
        self.assertEqual(metrics.photo_gap, 100)
        self.assertEqual(metrics.canvas_w, 2971)

    def test_video_canvas_layout_uses_equal_margins_without_extra_right_reserve(self):
        cfg = LayoutConfig(
            photo_height=1850,
            line_bottom_margin=110,
            output_mode="video",
        )
        items = [
            SimpleNamespace(image=SimpleNamespace(size=(1200, 1850))),
            SimpleNamespace(image=SimpleNamespace(size=(1200, 1850))),
        ]
        assets = WatermarkAssets(
            signature=SimpleNamespace(size=(55, 120)),
            logo=None,
            logo_name=None,
        )

        metrics = calculate_layout_metrics(items, cfg, assets)

        self.assertEqual(metrics.canvas_w, config.CANVAS_W)
        self.assertEqual(metrics.photo_gap, 480)
        self.assertEqual(metrics.side_margin, 480)

    def test_invalid_jpeg_quality_is_rejected(self):
        cfg = LayoutConfig(jpeg_quality=101)

        with self.assertRaisesRegex(ValueError, "jpeg_quality"):
            validate_layout_params(1, cfg)


class RenderingIntegrationTests(unittest.TestCase):
    def test_make_canvas_writes_image_with_expected_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.jpg"
            output_path = tmp_path / "output.jpg"
            Image.new("RGB", (80, 100), (60, 120, 180)).save(input_path)

            fixed_metadata = PhotoMetadata(
                date="Fri, 08 May 2026 12:00:00",
                make="Apple",
                model="iPhone 15 Pro",
                settings="24mm f/1.8 1/120 ISO100",
                location="Shanghai",
            )

            def fake_prepare_fonts(cfg):
                font = ImageFont.load_default()
                cfg.date_font = font
                cfg.info_font = font
                cfg.location_font = font

            cfg = LayoutConfig(
                photo_height=100,
                line_bottom_margin=60,
                line_left_offset=5,
                line_length=40,
                date_font_size=12,
                info_font_size=12,
                location_font_size=12,
                jpeg_quality=92,
                include_gps_location=False,
                output_mode="adaptive",
            )

            with (
                patch("watermark_tool.renderer.read_photo_metadata", return_value=fixed_metadata),
                patch("watermark_tool.renderer.prepare_fonts", side_effect=fake_prepare_fonts),
            ):
                with suppress_watermark_logs():
                    make_canvas([input_path], output_path, config=cfg)

            with Image.open(output_path) as result:
                self.assertEqual(result.size, (2080, config.CANVAS_H))
                self.assertEqual(result.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
