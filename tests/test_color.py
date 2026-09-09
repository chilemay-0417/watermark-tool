import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageCms, PngImagePlugin

from tests.test_layout import suppress_watermark_logs
from watermark_tool.color import SRGB_ICC, normalize_image
from watermark_tool.config import LayoutConfig, PhotoMetadata
from watermark_tool.drawing import (
    get_oriented_image_size,
    open_image_correct_orientation,
    save_best_quality_image,
)
from watermark_tool.renderer import make_canvas, open_logo_image


def p3_profile():
    """Portable test ICC: sRGB transfer curves with Display P3 D50 colorants."""
    profile = bytearray(SRGB_ICC)
    colorants = {
        b"rXYZ": (0.515102, 0.241182, -0.00104941),
        b"gXYZ": (0.291965, 0.692236, 0.0418818),
        b"bXYZ": (0.157153, 0.0665819, 0.784378),
    }
    count = struct.unpack_from(">I", profile, 128)[0]
    for i in range(count):
        tag, offset, _ = struct.unpack_from(">4sII", profile, 132 + i * 12)
        if tag in colorants:
            struct.pack_into(">3i", profile, offset + 8,
                             *(round(value * 65536) for value in colorants[tag]))
    return bytes(profile)


class ColorManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_p3_pixels_are_transformed_and_output_is_tagged_srgb(self):
        path = self.root / "p3.png"
        Image.new("RGB", (12, 8), (180, 100, 60)).save(path, icc_profile=p3_profile())
        with open_image_correct_orientation(path) as image:
            np.testing.assert_allclose(image.getpixel((0, 0)), (193, 95, 49), atol=1)
            self.assertEqual(image.info["icc_profile"], SRGB_ICC)
            # Reprocessing an already normalized image must not convert P3 twice.
            self.assertEqual(normalize_image(image).tobytes(), image.tobytes())

    def test_srgb_pixels_and_untagged_rgb_are_unchanged(self):
        pixels = np.random.default_rng(7).integers(0, 256, (12, 16, 3), dtype=np.uint8)
        for profile in (None, SRGB_ICC):
            image = Image.fromarray(pixels)
            if profile:
                image.info["icc_profile"] = profile
            result = normalize_image(image)
            np.testing.assert_array_equal(result, pixels)
            self.assertEqual(result.info, {"icc_profile": SRGB_ICC})

    def test_no_icc_adobe_rgb_exif_is_used(self):
        path = self.root / "adobe.png"
        exif = Image.Exif()
        exif[34665] = {40961: 2}
        Image.new("RGB", (8, 8), (180, 100, 60)).save(path, exif=exif)
        with open_image_correct_orientation(path) as image:
            np.testing.assert_allclose(image.getpixel((0, 0)), (204, 100, 55), atol=2)

    def test_icc_takes_priority_over_conflicting_exif_and_png_gamma(self):
        image = Image.new("RGB", (8, 8), (100, 120, 140))
        image.getexif()[40961] = 2
        image.info.update(icc_profile=SRGB_ICC, gamma=1)
        self.assertEqual(normalize_image(image).getpixel((0, 0)), (100, 120, 140))

    def test_invalid_icc_fails_without_replacing_existing_output(self):
        output = self.root / "out.png"
        output.write_bytes(b"previous result")
        image = Image.new("RGB", (8, 8))
        image.info["icc_profile"] = b"not an ICC profile"
        with self.assertRaisesRegex(ValueError, "ICC"):
            save_best_quality_image(image, output)
        self.assertEqual(output.read_bytes(), b"previous result")
        self.assertFalse(list(self.root.glob(".watermark-*")))

    def test_cmyk_without_profile_is_not_silently_reinterpreted(self):
        with self.assertRaisesRegex(ValueError, "CMYK.*ICC"):
            normalize_image(Image.new("CMYK", (8, 8)))

    def test_lab_profile_is_applied_in_original_mode(self):
        image = Image.new("LAB", (4, 4), (128, 128, 128))
        image.info["icc_profile"] = ImageCms.ImageCmsProfile(
            ImageCms.createProfile("LAB"),
        ).tobytes()
        result = normalize_image(image)
        np.testing.assert_allclose(result.getpixel((0, 0)), (119, 119, 119), atol=2)

    def test_16bit_gray_png_preserves_full_range(self):
        values = np.array([[0, 128, 255, 256, 16384, 32768, 65535]], dtype=np.uint16)
        expected = [0, 0, 1, 1, 64, 128, 255]
        path = self.root / "gray.png"
        Image.fromarray(values).save(path)
        with open_image_correct_orientation(path) as result:
            self.assertEqual(np.asarray(result)[0, :, 0].tolist(), expected)

    def test_big_endian_gray_uses_the_same_range(self):
        image = Image.fromarray(np.array([[0, 32768, 65535]], dtype=">u2"))
        self.assertEqual(np.asarray(normalize_image(image))[0, :, 0].tolist(), [0, 128, 255])

    def test_ambiguous_float_and_out_of_range_integer_are_rejected(self):
        for array in (np.array([[1.0, 2000]], dtype=np.float32),
                      np.array([[-1, 100000]], dtype=np.int32)):
            with self.assertRaises(ValueError):
                normalize_image(Image.fromarray(array))

    def test_png_gamma_and_chromaticity_are_applied(self):
        path = self.root / "linear.png"
        chunks = PngImagePlugin.PngInfo()
        chunks.add(b"gAMA", struct.pack(">I", 100000))
        Image.new("RGB", (8, 8), (128, 128, 128)).save(path, pnginfo=chunks)
        with open_image_correct_orientation(path) as result:
            self.assertEqual(result.getpixel((0, 0)), (188, 188, 188))
        # A cHRM-only P3 PNG uses the documented sRGB transfer fallback.
        chunks = PngImagePlugin.PngInfo()
        chrm = (0.3127, 0.3290, 0.680, 0.320, 0.265, 0.690, 0.150, 0.060)
        chunks.add(b"cHRM", struct.pack(">8I", *(round(x * 100000) for x in chrm)))
        Image.new("RGB", (8, 8), (180, 100, 60)).save(path, pnginfo=chunks)
        with open_image_correct_orientation(path) as result:
            np.testing.assert_allclose(result.getpixel((0, 0)), (193, 95, 49), atol=1)

    def test_alpha_is_preserved_for_marks_and_flattened_for_photos(self):
        path = self.root / "transparent.png"
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 0, 0, 0), (180, 100, 60, 128), (180, 100, 60, 255)])
        image.save(path, icc_profile=p3_profile())
        with open_image_correct_orientation(path, "RGBA") as rgba:
            self.assertEqual(np.asarray(rgba.getchannel("A")).ravel().tolist(), [0, 128, 255])
            np.testing.assert_allclose(rgba.getpixel((2, 0))[:3], (193, 95, 49), atol=1)
            expected = Image.alpha_composite(Image.new("RGBA", rgba.size, (20, 40, 60, 255)),
                                             rgba).convert("RGB")
            with open_image_correct_orientation(path, background=(20, 40, 60)) as rgb:
                self.assertEqual(rgb.tobytes(), expected.tobytes())
                self.assertEqual(rgb.getpixel((0, 0)), (20, 40, 60))
        with open_logo_image(path) as mark:
            self.assertEqual(mark.mode, "RGBA")
            self.assertEqual(mark.getpixel((0, 0))[3], 0)

    def test_palette_and_rgb_color_key_transparency(self):
        palette = Image.new("P", (2, 1))
        palette.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        palette.putdata([0, 1])
        palette.info["transparency"] = 0
        result = normalize_image(palette)
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(result.getpixel((1, 0)), (255, 0, 0))
        image = Image.new("RGB", (1, 1), (12, 34, 56))
        image.info["transparency"] = (12, 34, 56)
        self.assertEqual(normalize_image(image).getpixel((0, 0)), (255, 255, 255))

    def test_premultiplied_alpha_is_restored_before_conversion(self):
        image = Image.new("RGBa", (1, 1), (64, 32, 16, 128))
        result = normalize_image(image, "RGBA")
        np.testing.assert_allclose(result.getpixel((0, 0)), (127, 63, 31, 128), atol=1)
        gray = normalize_image(Image.new("La", (1, 1), (64, 128)), "RGBA")
        np.testing.assert_allclose(gray.getpixel((0, 0)), (127, 127, 127, 128), atol=1)

    def test_16bit_linear_gray_keeps_shadow_precision_until_gamma_encoding(self):
        image = Image.fromarray(np.array([[0, 128, 32768, 65535]], dtype=np.uint16))
        image.info["gamma"] = 1
        result = normalize_image(image)
        self.assertEqual(np.asarray(result)[0, :, 0].tolist(), [0, 6, 188, 255])

    def test_16bit_gray_transparency_uses_original_samples(self):
        image = Image.fromarray(np.array([[1000, 2000, 32768]], dtype=np.uint16))
        image.info["transparency"] = 2000
        result = normalize_image(image, "RGBA")
        self.assertEqual(np.asarray(result)[0, :, 3].tolist(), [255, 0, 255])

    def test_orientation_survives_color_conversion(self):
        path = self.root / "rotated.png"
        exif = Image.Exif()
        exif[274] = 6
        image = Image.new("RGB", (4, 8), (180, 100, 60))
        image.save(path, icc_profile=p3_profile(), exif=exif)
        with open_image_correct_orientation(path) as result:
            self.assertEqual(result.size, (8, 4))
            self.assertEqual(result.size, get_oriented_image_size(path))
            self.assertNotIn(274, result.getexif())

    def test_jpeg_and_png_export_valid_icc_without_old_metadata(self):
        image = Image.new("RGB", (12, 12), (180, 100, 60))
        exif = Image.Exif()
        exif[271] = "Test camera"
        image.info.update(icc_profile=p3_profile(), exif=exif.tobytes(), xmp=b"old metadata")
        for suffix in ("jpg", "png"):
            path = self.root / f"output.{suffix}"
            save_best_quality_image(image, path, jpeg_quality=100)
            with Image.open(path) as result:
                self.assertEqual(result.info["icc_profile"], SRGB_ICC)
                np.testing.assert_allclose(result.getpixel((4, 4)), (193, 95, 49), atol=2)
                self.assertFalse(result.getexif())
                self.assertNotIn("xmp", result.info)

    def test_mixed_profiles_and_transparency_through_full_renderer(self):
        paths = [self.root / name for name in ("p3.png", "srgb.png", "alpha.png")]
        Image.new("RGB", (80, 100), (180, 100, 60)).save(paths[0], icc_profile=p3_profile())
        Image.new("RGB", (80, 100), (40, 100, 180)).save(paths[1], icc_profile=SRGB_ICC)
        Image.new("RGBA", (80, 100), (0, 0, 0, 0)).save(paths[2])
        cfg = LayoutConfig(
            output_mode="adaptive", photo_height=100, include_gps_location=False, color_mode="srgb",
            show_signature=False, signature_text="", background_color=(12, 34, 56),
            date_font_size=12, info_font_size=12, location_font_size=12,
            line_length=30, line_left_offset=5, line_bottom_margin=60,
        )
        output = self.root / "combined.png"
        with patch("watermark_tool.renderer.read_photo_metadata",
                   return_value=PhotoMetadata("", "", "", "", "")), suppress_watermark_logs():
            make_canvas(paths, output, cfg)
        with Image.open(output) as result:
            self.assertEqual(result.info["icc_profile"], SRGB_ICC)
            counts = dict((color, count) for count, color in result.getcolors(100000))
            self.assertGreaterEqual(counts.get((193, 95, 49), 0), 8000)
            self.assertGreaterEqual(counts.get((40, 100, 180), 0), 8000)
            self.assertGreaterEqual(counts.get((12, 34, 56), 0), 8000)

    def test_preview_script_preserves_color_and_profile(self):
        source = self.root / "samples"
        source.mkdir()
        name = "p3.jpg"
        Image.new("RGB", (100, 80), (180, 100, 60)).save(source / name, icc_profile=p3_profile(),
                                                               quality=100, subsampling=0)
        spec = importlib.util.spec_from_file_location(
            "preview", Path(__file__).resolve().parents[1] / "scripts/build_readme_previews.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        with (
            patch.object(script, "ROOT", self.root),
            patch.object(script, "PREVIEWS", ((name, 50),)),
        ):
            script.main()
        with Image.open(self.root / "docs/previews" / name) as result:
            self.assertEqual(result.size, (50, 40))
            self.assertEqual(result.info["icc_profile"], SRGB_ICC)
            np.testing.assert_allclose(result.getpixel((20, 20)), (193, 95, 49), atol=3)


class HeifTests(unittest.TestCase):
    def test_real_heif_10_and_12bit_decode_nclx_and_rotation(self):
        import pillow_heif

        with tempfile.TemporaryDirectory() as directory, suppress_watermark_logs():
            for bits, transfer in ((10, 13), (12, 13)):
                path = Path(directory) / f"{bits}-{transfer}.heic"
                values = np.full((16, 32, 3), 32768, dtype=np.uint16)
                heif = pillow_heif.from_bytes("RGB;16", (32, 16), values.tobytes())
                exif = Image.Exif()
                exif[274] = 6
                heif.save(path, quality=-1, bit_depth=bits, exif=exif.tobytes(),
                          save_nclx_profile=True, color_primaries=9,
                          transfer_characteristics=transfer, matrix_coefficients=0)
                raw = pillow_heif.open_heif(path, convert_hdr_to_8bit=False, hdr_to_16bit=False)
                self.assertEqual(raw.info["nclx_profile"]["transfer_characteristics"], transfer)
                self.assertEqual(raw.info["bit_depth"], bits)
                with open_image_correct_orientation(path) as result:
                    self.assertEqual(result.size, (16, 32))
                    self.assertEqual(result.size, get_oriented_image_size(path))
                    self.assertEqual(result.info["icc_profile"], SRGB_ICC)
                    expected = 128
                    np.testing.assert_allclose(result.getpixel((0, 0)), (expected,) * 3, atol=2)

    def test_real_heif_icc_with_alpha_and_untagged_high_depth_gray(self):
        import pillow_heif

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p3.heic"
            original = Image.new("RGBA", (32, 32), (180, 100, 60, 128))
            pillow_heif.from_pillow(original).save(path, quality=-1, icc_profile=p3_profile(),
                                                   chroma=444)
            with open_image_correct_orientation(path, "RGBA") as result:
                np.testing.assert_allclose(result.getpixel((8, 8)), (193, 95, 49, 128), atol=2)
                self.assertEqual(result.info["icc_profile"], SRGB_ICC)
            gray = np.full((32, 32), 32768, dtype=np.uint16)
            pillow_heif.from_bytes("L;16", (32, 32), gray.tobytes()).save(path, quality=-1,
                                                                         bit_depth=12)
            with open_image_correct_orientation(path) as result:
                self.assertEqual(result.getpixel((8, 8)), (128, 128, 128))

    def test_unsupported_heif_color_tags_fail_clearly(self):
        import pillow_heif

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.heic"
            pillow_heif.from_pillow(Image.new("RGB", (32, 32))).save(
                path, quality=-1, save_nclx_profile=True,
                color_primaries=9, transfer_characteristics=2,
            )
            with self.assertRaisesRegex(ValueError, "传递函数"):
                open_image_correct_orientation(path)


if __name__ == "__main__":
    unittest.main()
