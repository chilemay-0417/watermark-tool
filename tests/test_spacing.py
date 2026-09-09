import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageFont

from tests.test_layout import suppress_watermark_logs
from watermark_tool.cli import make_default_output_path
from watermark_tool.config import (
    CANVAS_H,
    CANVAS_W,
    RIGHT_GAP,
    LayoutConfig,
    PhotoMetadata,
    PhotoWatermark,
    WatermarkAssets,
)
from watermark_tool.renderer import (
    calculate_layout_metrics,
    get_annotation_extents,
    load_photo_items,
    make_canvas,
    draw_photo_item,
    validate_layout_params,
)


def make_items(sizes, text_widths=None, location_widths=None):
    text_widths = text_widths or [0] * len(sizes)
    location_widths = location_widths or [0] * len(sizes)
    return [
        SimpleNamespace(
            image=SimpleNamespace(size=size),
            settings_image=Image.new("RGBA", (text_width, 50)) if text_width else None,
            location_image=Image.new("RGBA", (location_width, 50)) if location_width else None,
        )
        for size, text_width, location_width in zip(
            sizes, text_widths, location_widths, strict=True,
        )
    ]


def make_assets(widths):
    marks = [
        PhotoWatermark(Image.new("RGBA", (width, 50)), "test", False)
        if width else PhotoWatermark(None, None, False)
        for width in widths
    ]
    return WatermarkAssets(
        signature=None, logo=None, logo_name=None, max_width=max(widths),
        reserved_right_width=RIGHT_GAP + widths[-1] if widths[-1] else 0,
        photo_marks=marks,
    )


def photo_positions(metrics):
    x = metrics.side_margin
    positions = []
    for width in metrics.photo_widths:
        positions.append((x, x + width))
        x += width + metrics.photo_gap
    return positions


class SpacingTests(unittest.TestCase):
    def assert_spacing(self, metrics, mode):
        positions = photo_positions(metrics)
        left = positions[0][0]
        right = metrics.canvas_w - positions[-1][1]
        self.assertEqual(left, right)
        for first, second in zip(positions, positions[1:], strict=False):
            self.assertEqual(second[0] - first[1], left)

    def assert_annotations_fit(self, items, cfg, assets, metrics):
        left, right = get_annotation_extents(items, cfg, assets)
        self.assertGreaterEqual(metrics.side_margin, left[0])
        self.assertGreaterEqual(metrics.side_margin, right[-1])
        if len(items) > 1:
            self.assertGreater(metrics.photo_gap, right[-1] + left[-1])
        positions = photo_positions(metrics)
        for i in range(len(items) - 1):
            self.assertLess(positions[i][1] + right[i], positions[i + 1][0] - left[i + 1])

    def test_video_equal_margins_for_one_two_three_and_mixed_aspect_ratios(self):
        cases = [
            [(2771, 1850)], [(1233, 1850), (1233, 1850)],
            [(1233, 1850)] * 3, [(2771, 1850), (1233, 1850), (1850, 1850)],
            [(2771, 1850)] * 3, [(15000, 1000)],
        ]
        cfg = LayoutConfig(output_mode="video")
        for sizes in cases:
            with self.subTest(sizes=sizes):
                items = make_items(sizes, [30] * len(sizes))
                assets = make_assets([55] * len(sizes))
                metrics = calculate_layout_metrics(items, cfg, assets)
                self.assertEqual(metrics.canvas_w, CANVAS_W)
                self.assertEqual(metrics.canvas_h, CANVAS_H)
                self.assertLessEqual(metrics.photo_height, cfg.photo_height)
                self.assert_spacing(metrics, "video")
                self.assert_annotations_fit(items, cfg, assets, metrics)
                for (w, h), actual in zip(sizes, metrics.photo_widths, strict=True):
                    self.assertLessEqual(abs(actual - round(w * metrics.photo_height / h)), 1)

    def test_video_collision_shrinks_until_gap_reaches_one_and_a_half_a(self):
        cfg = LayoutConfig(output_mode="video")
        for text_width in (30, 31):
            with self.subTest(text_width=text_width):
                # 初始间距 117px，a 分别为 120 / 121，目标分别为 180 / 182px。
                items = make_items([(1124, 1850)] * 3, [text_width] * 3)
                assets = make_assets([55] * 3)
                metrics = calculate_layout_metrics(items, cfg, assets)
                target = (3 * (20 + 55 + 15 + text_width) + 1) // 2
                self.assertLess(metrics.photo_height, 1850)
                self.assertGreaterEqual(metrics.photo_gap, target)
                next_width = round(1124 * (metrics.photo_height + 1) / 1850)
                self.assertLess((CANVAS_W - 3 * next_width) // 4, target)
                self.assert_annotations_fit(items, cfg, assets, metrics)
                self.assert_spacing(metrics, "video")

    def test_video_does_not_shrink_when_gap_is_a_or_between_a_and_one_and_a_half_a(self):
        cfg = LayoutConfig(output_mode="video")
        for width, gap in ((1120, 120), (1100, 135), (1040, 180)):
            with self.subTest(gap=gap):
                items = make_items([(width, 1850)] * 3, [30] * 3)
                metrics = calculate_layout_metrics(items, cfg, make_assets([55] * 3))
                self.assertEqual(metrics.photo_height, 1850)
                self.assertEqual(metrics.photo_gap, gap)
                self.assert_spacing(metrics, "video")

    def test_video_accounts_for_wider_internal_logo_and_location(self):
        cfg = LayoutConfig(output_mode="video", location_gap_x=50)
        items = make_items([(1160, 1850)] * 3, [30] * 3, [0, 90, 0])
        assets = make_assets([110, 0, 55])
        metrics = calculate_layout_metrics(items, cfg, assets)
        self.assertGreaterEqual(metrics.photo_gap, 405)
        self.assert_annotations_fit(items, cfg, assets, metrics)

    def test_video_keeps_height_when_space_is_sufficient(self):
        cfg = LayoutConfig(output_mode="video")
        items = make_items([(1000, 1850)] * 2, [30] * 2)
        metrics = calculate_layout_metrics(items, cfg, make_assets([55, 55]))
        self.assertEqual(metrics.photo_height, cfg.photo_height)
        self.assert_spacing(metrics, "video")

    def test_video_fits_single_photo_mark_inside_equal_margins(self):
        cfg = LayoutConfig(output_mode="video")
        items = make_items([(3830, 1850)], [30])
        assets = make_assets([55])
        metrics = calculate_layout_metrics(items, cfg, assets)
        self.assertLess(metrics.photo_height, cfg.photo_height)
        self.assert_annotations_fit(items, cfg, assets, metrics)
        self.assert_spacing(metrics, "video")

    def test_video_fits_vertically_without_mutating_requested_height(self):
        cfg = LayoutConfig(output_mode="video", photo_height=2100)
        metrics = calculate_layout_metrics(make_items([(100, 2100)]), cfg, make_assets([0]))
        self.assertEqual(cfg.photo_height, 2100)
        self.assertGreaterEqual(metrics.photo_top, 0)
        self.assertLessEqual(metrics.photo_height, CANVAS_H - cfg.line_bottom_margin)

    def test_video_reports_impossible_annotation_sizes(self):
        cfg = LayoutConfig(output_mode="video", info_gap_x=2000)
        items = make_items([(1200, 1850)] * 3, [30] * 3)
        with self.assertRaisesRegex(ValueError, "水印和参数占用过宽"):
            calculate_layout_metrics(items, cfg, make_assets([55] * 3))

    def test_missing_metadata_or_marks_does_not_reserve_phantom_space(self):
        cfg = LayoutConfig(output_mode="video")
        items = make_items([(1200, 1850)] * 3)
        assets = make_assets([0] * 3)
        self.assertEqual(get_annotation_extents(items, cfg, assets), ([0] * 3, [0] * 3))
        metrics = calculate_layout_metrics(items, cfg, assets)
        self.assertEqual(metrics.photo_height, cfg.photo_height)
        self.assert_spacing(metrics, "video")

    def test_adaptive_spacing_is_one_point_eight_top_margin_with_unlimited_width_and_count(self):
        cfg = LayoutConfig(output_mode="adaptive")
        for count in (1, 2, 3, 4, 50):
            with self.subTest(count=count):
                validate_layout_params(count, cfg)
                items = make_items([(2771, 1850)] * count, [30] * count)
                assets = make_assets([55] * count)
                metrics = calculate_layout_metrics(items, cfg, assets)
                self.assertEqual(metrics.photo_height, 1850)
                margin = 100 if count == 1 else 180
                self.assertEqual(metrics.side_margin, margin)
                self.assertEqual(metrics.photo_gap, margin)
                self.assertEqual(metrics.canvas_w, count * 2771 + (count + 1) * margin)
                self.assert_spacing(metrics, "adaptive")
                self.assert_annotations_fit(items, cfg, assets, metrics)

    def test_adaptive_multi_photo_spacing_rounds_one_point_eight_top_margin(self):
        for height, top, margin in ((1850, 100, 180), (1848, 101, 182), (1846, 102, 184)):
            with self.subTest(height=height):
                cfg = LayoutConfig(output_mode="adaptive", photo_height=height)
                items = make_items([(1200, 1850)] * 2, [30] * 2)
                metrics = calculate_layout_metrics(items, cfg, make_assets([55, 55]))
                self.assertEqual(metrics.photo_top, top)
                self.assertEqual(metrics.side_margin, margin)
                self.assertEqual(metrics.photo_gap, margin)
                self.assertEqual(metrics.photo_height, height)
                self.assert_spacing(metrics, "adaptive")

    def test_adaptive_reports_insufficient_space_without_breaking_requested_ratio(self):
        cfg = LayoutConfig(output_mode="adaptive", photo_height=2000)
        items = make_items([(1200, 1850)] * 2, [50, 80])
        with self.assertRaisesRegex(ValueError, "1.8 倍不足"):
            calculate_layout_metrics(items, cfg, make_assets([110, 100]))

    def test_only_video_has_three_photo_limit(self):
        with self.assertRaisesRegex(ValueError, "最多支持 3 张"):
            validate_layout_params(4, LayoutConfig(output_mode="video"))
        with self.assertRaisesRegex(ValueError, "至少需要"):
            validate_layout_params(0, LayoutConfig())

    def test_long_unicode_output_names_are_shortened_and_unique(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = [Path(tmp_dir) / ("照片" * 30 + f"_{i}.jpg") for i in range(20)]
            output = make_default_output_path(paths)
            self.assertLess(len(output.name.encode("utf-8")), 255)
            self.assertIn("and_19_photos", output.name)
            output.touch()
            self.assertNotEqual(make_default_output_path(paths), output)


class SpacingRenderingTests(unittest.TestCase):
    @staticmethod
    def prepare_fonts(cfg):
        cfg.date_font = cfg.info_font = cfg.location_font = ImageFont.load_default(size=35)

    def test_measured_text_extents_use_actual_rendered_glyph_widths(self):
        cfg = LayoutConfig(include_gps_location=False, location_gap_x=50)
        self.prepare_fonts(cfg)
        metadata = PhotoMetadata("test", "", "", "24mm f/1.8 ISO100", "Shanghai")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "photo.png"
            Image.new("RGB", (80, 100)).save(path)
            with patch("watermark_tool.renderer.read_photo_metadata", return_value=metadata):
                items = load_photo_items([path], cfg)
            self.assertEqual(items[0].image.size, (80, 100))
            left, _ = get_annotation_extents(items, cfg, make_assets([0]))
            self.assertEqual(left[0], max(
                cfg.info_gap_x + items[0].settings_image.width,
                cfg.location_gap_x + items[0].location_image.width,
            ))

    def test_deferred_loading_matches_exif_rotation_without_retaining_pixels(self):
        cfg = LayoutConfig(include_gps_location=False)
        self.prepare_fonts(cfg)
        metadata = PhotoMetadata("test", "", "", "", "")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rotated.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (80, 100)).save(path, exif=exif)
            with patch("watermark_tool.renderer.read_photo_metadata", return_value=metadata):
                eager = load_photo_items([path], cfg)
                deferred = load_photo_items([path], cfg, defer_pixels=True)
            self.assertEqual(deferred[0].source_size, (100, 80))
            self.assertIsNone(deferred[0].image)
            assets = make_assets([0])
            self.assertEqual(
                calculate_layout_metrics(eager, cfg, assets),
                calculate_layout_metrics(deferred, cfg, assets),
            )

    def test_very_wide_jpeg_explains_png_alternative_before_rendering(self):
        cfg = LayoutConfig(
            output_mode="adaptive", include_gps_location=False,
            show_signature=False, signature_text="",
        )
        metadata = PhotoMetadata("test", "", "", "", "")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "wide.png"
            output = Path(tmp_dir) / "out.jpg"
            Image.new("RGB", (3600, 100)).save(path)
            with (
                patch("watermark_tool.renderer.read_photo_metadata", return_value=metadata),
                patch("watermark_tool.renderer.prepare_fonts", side_effect=self.prepare_fonts),
                suppress_watermark_logs(),
                self.assertRaisesRegex(ValueError, "65500.*png"),
            ):
                make_canvas([path], output, cfg)
            self.assertFalse(output.exists())

    def test_auto_shrink_preserves_original_footer_settings(self):
        metadata = PhotoMetadata("Tue, 17 Jun 2025 15:57:55", "", "", "", "")
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = []
            for i, size in enumerate(((2, 3), (4, 3), (4, 3))):
                path = Path(tmp_dir) / f"{i}.png"
                Image.new("RGB", size, (80, 140, 200)).save(path)
                paths.append(path)
            output = Path(tmp_dir) / "out.png"
            cfg = LayoutConfig(
                output_mode="video", include_gps_location=False,
                show_signature=False, signature_text="",
            )
            with (
                patch("watermark_tool.renderer.read_photo_metadata", return_value=metadata),
                patch(
                    "watermark_tool.renderer.draw_photo_item", wraps=draw_photo_item,
                ) as draw_photo,
                suppress_watermark_logs(),
            ):
                make_canvas(paths, output, cfg)
            metrics = draw_photo.call_args.kwargs["metrics"]
            self.assertLess(metrics.photo_height, cfg.photo_height)
            for call in draw_photo.call_args_list:
                actual = call.kwargs["config"]
                for field in (
                    "line_left_offset", "line_length", "line_width", "line_bottom_margin",
                    "date_font_size", "date_tracking", "date_gap_below_line",
                ):
                    self.assertEqual(getattr(actual, field), getattr(cfg, field))
                self.assertEqual(actual.date_font.size, cfg.date_font_size)

    def test_exported_photo_pixels_have_exact_equal_spacing_in_both_modes(self):
        colors = [(220, 40, 40), (40, 170, 70), (40, 80, 220), (190, 60, 200)]
        metadata = PhotoMetadata("2026-09-09", "", "", "24mm f/1.8 ISO100", "Shanghai")
        for mode, count in (("video", 1), ("video", 2), ("video", 3), ("adaptive", 4)):
            with self.subTest(mode=mode, count=count), tempfile.TemporaryDirectory() as tmp_dir:
                paths = []
                for i in range(count):
                    path = Path(tmp_dir) / f"photo{i}.png"
                    Image.new("RGB", (80, 100), colors[i]).save(path)
                    paths.append(path)
                cfg = LayoutConfig(
                    output_mode=mode, include_gps_location=False,
                    show_signature=False, signature_text="", line_length=40, line_left_offset=5,
                )
                output = Path(tmp_dir) / "out.png"
                with (
                    patch("watermark_tool.renderer.read_photo_metadata", return_value=metadata),
                    patch("watermark_tool.renderer.prepare_fonts", side_effect=self.prepare_fonts),
                    suppress_watermark_logs(),
                ):
                    make_canvas(paths, output, cfg)
                # 配置可反复使用：渲染不回写高度或字体缓存。
                self.assertEqual(cfg, replace(LayoutConfig(), **{
                    "output_mode": mode, "include_gps_location": False,
                    "show_signature": False, "signature_text": "",
                    "line_length": 40, "line_left_offset": 5,
                }))
                with Image.open(output) as result:
                    row = [result.getpixel((x, 1025)) for x in range(result.width)]
                    intervals = []
                    for color in colors[:count]:
                        xs = [x for x, pixel in enumerate(row) if pixel == color]
                        self.assertTrue(xs)
                        intervals.append((xs[0], xs[-1] + 1))
                    margin = intervals[0][0]
                    self.assertEqual(result.width - intervals[-1][1], margin)
                    for left, right in zip(intervals, intervals[1:], strict=False):
                        self.assertEqual(
                            right[0] - left[1], margin,
                        )
                    self.assertEqual(result.height, CANVAS_H)
                    if mode == "video":
                        self.assertEqual(result.width, CANVAS_W)
                    else:
                        self.assertGreater(result.width, CANVAS_W)
                        self.assertEqual(margin, 180)


if __name__ == "__main__":
    unittest.main()
