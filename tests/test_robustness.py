import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from tests.test_layout import suppress_watermark_logs
from watermark_tool import exif_gps
from watermark_tool.config import LayoutConfig, LayoutMetrics, PhotoItem, PhotoMetadata
from watermark_tool.drawing import draw_rotated_camera_settings, save_best_quality_image
from watermark_tool.annotations import draw_photo_item
from watermark_tool.renderer import make_canvas
from watermark_tool.layout import validate_layout_params


class ExportSafetyTests(unittest.TestCase):
    def test_output_cannot_replace_an_input_directly_or_through_a_link(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = Path(tmp_dir) / "original.jpg"
            original.write_bytes(b"original photo")
            symlink = Path(tmp_dir) / "symlink.jpg"
            symlink.symlink_to(original)
            hardlink = Path(tmp_dir) / "hardlink.jpg"
            os.link(original, hardlink)
            for output in (original, symlink, hardlink):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "保留原图"):
                    make_canvas([original], output)
                self.assertEqual(original.read_bytes(), b"original photo")

    def test_unsupported_output_suffix_is_rejected_before_reading_images(self):
        with self.assertRaisesRegex(ValueError, "后缀"):
            make_canvas(["missing.jpg"], "output.webp")

    def test_failed_save_keeps_existing_output_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "output.jpg"
            output.write_bytes(b"previous output")

            def fail_save(image, path, quality):
                Path(path).write_bytes(b"partial new output")
                raise OSError("disk full")

            with (
                patch("watermark_tool.drawing.save_best_quality_jpeg", side_effect=fail_save),
                self.assertRaisesRegex(OSError, "disk full"),
            ):
                save_best_quality_image(Image.new("RGB", (2, 2)), output)
            self.assertEqual(output.read_bytes(), b"previous output")
            self.assertEqual(list(Path(tmp_dir).iterdir()), [output])

    def test_successful_atomic_save_writes_the_requested_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for suffix, expected in ((".jpg", "JPEG"), (".jpeg", "JPEG"), (".png", "PNG")):
                with self.subTest(suffix=suffix):
                    output = Path(tmp_dir) / ("output" + suffix)
                    save_best_quality_image(Image.new("RGB", (12, 9)), output)
                    with Image.open(output) as img:
                        self.assertEqual(img.format, expected)
                        self.assertEqual(img.size, (12, 9))
            self.assertFalse(list(Path(tmp_dir).glob(".watermark-*")))


class ParameterValidationTests(unittest.TestCase):
    def test_invalid_aperture_and_iso_do_not_render_garbage(self):
        for value in (None, 0, -1, "unknown", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertEqual(exif_gps.format_aperture(value), "")
                self.assertEqual(exif_gps.format_iso(value), "")
        for value in ([], [None], {}, 49.5):
            self.assertEqual(exif_gps.format_iso(value), "")
        self.assertEqual(exif_gps.format_iso([49]), "ISO49")
        self.assertEqual(exif_gps.format_iso("100"), "ISO100")

    def test_invalid_coordinates_are_skipped_without_network_requests(self):
        base = {
            exif_gps.GPS_LATITUDE: (31, 0, 0), exif_gps.GPS_LATITUDE_REF: "N",
            exif_gps.GPS_LONGITUDE: (121, 0, 0), exif_gps.GPS_LONGITUDE_REF: "E",
        }
        cases = [
            (exif_gps.GPS_LATITUDE, 31),
            (exif_gps.GPS_LATITUDE, "invalid"),
            (exif_gps.GPS_LATITUDE, (float("nan"), 0, 0)),
            (exif_gps.GPS_LATITUDE, (91, 0, 0)),
            (exif_gps.GPS_LATITUDE, (31, 60, 0)),
            (exif_gps.GPS_LONGITUDE, (181, 0, 0)),
            (exif_gps.GPS_LONGITUDE_REF, None),
        ]
        for key, value in cases:
            with (
                self.subTest(value=value),
                patch.object(exif_gps, "reverse_geocode_location") as fetch,
            ):
                data = {exif_gps.TAG_GPS_INFO: {**base, key: value}}
                self.assertEqual(exif_gps.format_gps_location(data), "")
                fetch.assert_not_called()

    def test_nonfinite_spacing_and_invalid_timeout_fail_early(self):
        for name in ("date_tracking", "info_tracking", "location_tracking", "gps_location_timeout"):
            for value in (float("nan"), float("inf")):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, name):
                    validate_layout_params(1, LayoutConfig(**{name: value}))
        with self.assertRaisesRegex(ValueError, "gps_location_timeout"):
            validate_layout_params(1, LayoutConfig(gps_location_timeout=0))


class DrawingBoundsTests(unittest.TestCase):
    def test_vertical_text_overflow_is_reported_instead_of_silently_cropped(self):
        canvas = Image.new("RGB", (200, 200), "white")
        kwargs = dict(
            canvas=canvas, photo_x=50, photo_y=20, photo_h=100,
            settings_text="settings", location_text="location", font=None, location_font=None,
            fill="black", tracking=0, location_tracking=0, location_gap=35,
            gap_x=15, location_gap_x=15, bottom_gap=0,
        )
        with self.assertRaisesRegex(ValueError, "上下边界"):
            draw_rotated_camera_settings(
                **kwargs,
                prepared_images=(Image.new("RGBA", (10, 70)), Image.new("RGBA", (10, 70))),
            )
        self.assertEqual(canvas.getextrema(), ((255, 255),) * 3)

    def test_date_boundary_uses_actual_glyph_bottom_not_just_glyph_height(self):
        font = ImageFont.load_default(size=35)
        bbox = font.getbbox("g")
        self.assertGreater(bbox[1], 0)
        cfg = LayoutConfig(
            line_bottom_margin=bbox[3] - 1, date_gap_below_line=0,
            line_left_offset=0, line_length=40, date_font=font,
        )
        canvas = Image.new("RGB", (500, 200), "white")
        item = PhotoItem(Path("unused.jpg"), Image.new("RGB", (100, 50)),
                         PhotoMetadata("g", "", "", "", ""))
        metrics = LayoutMetrics(500, 200, 100, 10, 100, 50, (100,))
        with suppress_watermark_logs(), self.assertRaisesRegex(ValueError, "日期文字会超出"):
            draw_photo_item(canvas, ImageDraw.Draw(canvas), item, 0, 100, metrics, cfg)


if __name__ == "__main__":
    unittest.main()
