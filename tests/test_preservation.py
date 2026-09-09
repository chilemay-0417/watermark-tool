"""Regression cases for native precision, color tags and metadata policies."""

from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import png
from PIL import Image, PngImagePlugin
import pillow_heif

from tests.test_color import p3_profile
from tests.test_layout import suppress_watermark_logs
from watermark_tool.cli import build_parser, config_from_args, make_default_output_path
from watermark_tool.color import SRGB_ICC
from watermark_tool.config import LayoutConfig
from watermark_tool.drawing import get_oriented_image_size, open_image_correct_orientation
from watermark_tool.exif_gps import read_photo_metadata
from watermark_tool.metadata import collect_metadata
from watermark_tool.preserved import make_preserved_canvas, write_png
from watermark_tool.raster import ColorSpec, read_raster, transform_icc
from watermark_tool.renderer import make_canvas


def linear_profile():
    profile = bytearray(SRGB_ICC)
    seen = set()
    for i in range(struct.unpack_from(">I", profile, 128)[0]):
        tag, offset, _ = struct.unpack_from(">4sII", profile, 132 + 12 * i)
        if tag in (b"rTRC", b"gTRC", b"bTRC") and offset not in seen:
            seen.add(offset)
            struct.pack_into(">H", profile, offset + 8, 0)
            struct.pack_into(">i", profile, offset + 12, 65536)
    return bytes(profile)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cfg = LayoutConfig(
            output_mode="original",
            show_signature=False,
            signature_text="",
            line_length=12,
            line_left_offset=0,
            date_font_size=10,
            info_font_size=10,
            location_font_size=10,
        )

    def render(self, paths, name="output.png", config=None):
        output = self.root / name
        with suppress_watermark_logs():
            make_canvas(paths, output, config or self.cfg)
        return output

    def assert_region(self, output, original):
        # original mode, no metadata/marks: 80px left and 100px top.
        raster = read_raster(output)
        actual = raster.pixels[100 : 100 + original.shape[0], 80 : 80 + original.shape[1]]
        np.testing.assert_array_equal(actual, original)
        return raster

    def test_defaults_remain_4k_jpeg100_with_gps_lookup_enabled(self):
        config = config_from_args(build_parser().parse_args(["input.jpg"]))
        self.assertEqual((config.output_mode, config.jpeg_quality), ("video", 100))
        self.assertEqual(config.color_mode, "preserve")
        self.assertEqual(config.metadata_policy, "safe")
        self.assertFalse(config.preserve_gps)
        self.assertTrue(config.include_gps_location)
        self.assertEqual(make_default_output_path([self.root / "input.png"]).suffix, ".jpg")

    def test_p3_original_png_preserves_every_decoded_sample_and_profile(self):
        values = np.random.default_rng(22).integers(0, 256, (20, 32, 3), dtype=np.uint8)
        source = self.root / "p3.png"
        Image.fromarray(values).save(source, icc_profile=p3_profile())
        output = self.render([source])
        self.assert_region(output, values)
        with Image.open(output) as image:
            self.assertEqual(image.info["icc_profile"], p3_profile())

    def test_jpeg100_uses_source_icc_and_444_without_srgb_conversion(self):
        source = self.root / "p3.png"
        Image.new("RGB", (80, 80), (180, 100, 60)).save(source, icc_profile=p3_profile())
        output = self.render([source], "output.jpg")
        with Image.open(output) as image:
            self.assertEqual(image.info["icc_profile"], p3_profile())
            np.testing.assert_allclose(image.getpixel((120, 140)), (180, 100, 60), atol=1)
            self.assertTrue(all(v == 1 for table in image.quantization.values() for v in table))
            self.assertTrue(all(component[1:3] == (1, 1) for component in image.layer))

    def test_8bit_png_decoding_preserves_samples_and_transparency(self):
        gray = np.array([[0, 127, 255]], dtype=np.uint8)
        rgb = np.repeat(gray[..., None], 3, axis=2)
        alpha = np.array([[0, 128, 255]], dtype=np.uint8)
        color_key_alpha = np.array([[255, 0, 255]], dtype=np.uint8)
        palette = Image.new("P", (3, 1))
        palette.putpalette([0, 0, 0, 127, 127, 127, 255, 255, 255] + [0] * 759)
        palette.putdata([0, 1, 2])
        cases = (
            ("rgb", Image.fromarray(rgb), {}, None),
            ("rgba", Image.fromarray(np.dstack((rgb, alpha))), {}, alpha),
            ("gray", Image.fromarray(gray), {}, None),
            ("gray_alpha", Image.fromarray(np.dstack((gray, alpha))), {}, alpha),
            ("palette", palette, {"transparency": bytes((0, 128, 255))}, alpha),
            ("rgb_key", Image.fromarray(rgb), {"transparency": (127, 127, 127)}, color_key_alpha),
            ("gray_key", Image.fromarray(gray), {"transparency": 127}, color_key_alpha),
        )
        for name, image, options, expected_alpha in cases:
            with self.subTest(name=name):
                source = self.root / (name + ".png")
                image.save(source, **options)
                result = read_raster(source)
                np.testing.assert_array_equal(result.pixels, rgb)
                self.assertEqual(result.bits, 8)
                if expected_alpha is None:
                    self.assertIsNone(result.alpha)
                else:
                    np.testing.assert_array_equal(result.alpha, expected_alpha)

    def test_subbyte_grayscale_png_expands_to_full_8bit_range(self):
        for bits in (1, 2, 4):
            with self.subTest(bits=bits):
                maximum = (1 << bits) - 1
                source = self.root / f"gray-{bits}.png"
                with source.open("wb") as stream:
                    png.Writer(3, 1, greyscale=True, bitdepth=bits).write(
                        stream, [[0, 1, maximum]],
                    )
                result = read_raster(source)
                expected = np.repeat(np.array([[[0], [255 // maximum], [255]]]), 3, axis=2)
                np.testing.assert_array_equal(result.pixels, expected)

    def test_16bit_png_keeps_low_bits_in_lossless_output(self):
        values = np.tile(
            np.array([[[1, 128, 255], [256, 257, 65534], [10001, 20002, 30003]]], dtype=np.uint16),
            (12, 1, 1),
        )
        source = self.root / "native.png"
        write_png(source, values, 16, ColorSpec(icc=SRGB_ICC), {})
        output = self.render([source])
        result = self.assert_region(output, values)
        self.assertEqual(result.bits, 16)

    def test_tiff_is_rejected_by_suffix_and_detected_format(self):
        for name in ("input.tif", "input.tiff", "input.TIFF", "renamed.png", "renamed.jpg"):
            source = self.root / name
            Image.new("RGB", (16, 12)).save(source, format="TIFF")
            for loader in (read_raster, open_image_correct_orientation, get_oriented_image_size):
                with self.subTest(name=name, loader=loader.__name__):
                    with self.assertRaisesRegex(ValueError, "不再支持 TIFF"):
                        loader(source)

    def test_tiff_rejection_keeps_files_and_skips_metadata_queries_in_both_color_modes(self):
        source = self.root / "renamed.png"
        Image.new("RGB", (16, 12)).save(source, format="TIFF")
        original = source.read_bytes()
        for color_mode in ("preserve", "srgb"):
            for suffix in ("jpg", "png"):
                with self.subTest(color_mode=color_mode, suffix=suffix):
                    output = self.root / ("existing." + suffix)
                    output.write_bytes(b"previous output")
                    with (
                        suppress_watermark_logs(),
                        patch("watermark_tool.renderer.read_photo_metadata") as metadata,
                        self.assertRaisesRegex(ValueError, "不再支持 TIFF"),
                    ):
                        make_canvas([source], output, LayoutConfig(color_mode=color_mode))
                    metadata.assert_not_called()
                    self.assertEqual(output.read_bytes(), b"previous output")
                    self.assertEqual(source.read_bytes(), original)
                    self.assertFalse(list(self.root.glob(".watermark-*")))

    def test_linear_16bit_png_is_encoded_before_8bit_quantization(self):
        source = self.root / "linear.png"
        values = np.array([[[128, 128, 128], [32768, 32768, 32768]]], dtype=np.uint16)
        with source.open("wb") as stream:
            png.Writer(2, 1, greyscale=False, bitdepth=16, gamma=1).write(
                stream, values.reshape(1, -1)
            )
        with open_image_correct_orientation(source) as result:
            self.assertEqual(np.asarray(result)[0, :, 0].tolist(), [6, 188])

    def test_heif_icc_conversion_keeps_shadows_until_final_quantization(self):
        source = self.root / "linear.heic"
        values = np.full((32, 32, 3), 64, dtype=np.uint16)
        frame = pillow_heif.from_bytes("RGB;16", (32, 32), values.tobytes())
        frame.save(
            source,
            quality=-1,
            bit_depth=12,
            chroma=444,
            icc_profile=linear_profile(),
            save_nclx_profile=True,
            color_primaries=1,
            transfer_characteristics=8,
            matrix_coefficients=0,
        )
        with open_image_correct_orientation(source) as result:
            self.assertEqual(result.getpixel((8, 8)), (3, 3, 3))

    def test_cicp_p3_is_used_and_precedes_conflicting_srgb_profile(self):
        source = self.root / "cicp.png"
        values = np.full((12, 16, 3), (180, 100, 60), dtype=np.uint8)
        spec = ColorSpec(icc=SRGB_ICC, cicp=bytes((12, 13, 0, 1)))
        write_png(source, values, 8, spec, {})
        with open_image_correct_orientation(source) as result:
            np.testing.assert_allclose(result.getpixel((0, 0)), (193, 95, 49), atol=1)
        output = self.render([source])
        result = self.assert_region(output, values)
        self.assertEqual(result.color.cicp, bytes((12, 13, 0, 1)))

    def test_hdr_png_is_rejected_in_both_modes_without_replacing_output(self):
        source = self.root / "hdr.png"
        previous = self.root / "existing.png"
        previous.write_bytes(b"previous output")
        for transfer in (16, 18):
            chunks = PngImagePlugin.PngInfo()
            chunks.add(b"cICP", bytes((9, transfer, 0, 1)))
            Image.new("RGB", (16, 12)).save(source, pnginfo=chunks)
            for mode in ("preserve", "srgb"):
                self.cfg.color_mode = mode
                with self.assertRaisesRegex(ValueError, "不再支持 HDR"):
                    self.render([source], previous.name)
                self.assertEqual(previous.read_bytes(), b"previous output")
        self.assertFalse(list(self.root.glob(".watermark-*")))

    def test_hdr_heif_is_rejected_in_both_modes(self):
        source = self.root / "hdr.heic"
        for transfer in (16, 18):
            pillow_heif.from_pillow(Image.new("RGB", (32, 32))).save(
                source,
                quality=-1,
                save_nclx_profile=True,
                color_primaries=9,
                transfer_characteristics=transfer,
            )
            for mode in ("preserve", "srgb"):
                self.cfg.color_mode = mode
                with self.assertRaisesRegex(ValueError, "不再支持 HDR"):
                    self.render([source])

    def test_jpeg_gain_map_is_not_silently_discarded_by_preserve_mode(self):
        source = self.root / "gainmap.jpg"
        Image.new("RGB", (16, 12)).save(
            source,
            xmp=b'<x xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/" />',
        )
        with self.assertRaisesRegex(ValueError, "HDR 增益图"):
            self.render([source])
        self.cfg.color_mode = "srgb"
        with self.assertRaisesRegex(ValueError, "不再支持 HDR"):
            self.render([source], "share.jpg")

    def test_rotated_transparent_png_keeps_samples_and_alpha(self):
        source = self.root / "rotated.png"
        values = np.random.default_rng(4).integers(0, 256, (12, 16, 4), dtype=np.uint8)
        exif = Image.Exif()
        exif[274] = 6
        Image.fromarray(values).save(source, exif=exif, icc_profile=p3_profile())
        result = read_raster(self.render([source]))
        expected = np.rot90(values, 3)
        np.testing.assert_array_equal(result.pixels[100:116, 80:92], expected[..., :3])
        np.testing.assert_array_equal(result.alpha[100:116, 80:92], expected[..., 3])

    def test_mixed_sdr_profiles_use_wide_gamut_and_16bit_png(self):
        paths = [self.root / "p3.png", self.root / "srgb.png"]
        for path, profile in zip(paths, (p3_profile(), SRGB_ICC), strict=True):
            Image.new("RGB", (16, 12), (180, 100, 60)).save(path, icc_profile=profile)
        result = read_raster(self.render(paths))
        self.assertEqual(result.bits, 16)
        self.assertNotEqual(result.color.icc, SRGB_ICC)
        # Independent comparison in sRGB via Pillow/LittleCMS for both source and output.
        converted = transform_icc(result.pixels.astype(np.float32) / 65535, result.color.icc)
        np.testing.assert_allclose(converted[105, 85] * 255, (193, 95, 49), atol=1)
        np.testing.assert_allclose(converted[105, 181] * 255, (180, 100, 60), atol=1)

    def test_output_failure_keeps_existing_file(self):
        source = self.root / "source.png"
        Image.new("RGB", (16, 12)).save(source)
        output = self.root / "out.png"
        output.write_bytes(b"previous")
        with patch("watermark_tool.preserved.write_png", side_effect=OSError("disk full")):
            with suppress_watermark_logs(), self.assertRaisesRegex(OSError, "disk full"):
                make_preserved_canvas([source], output, self.cfg)
        self.assertEqual(output.read_bytes(), b"previous")
        self.assertFalse(list(self.root.glob(".watermark-*")))


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.png"
        exif = Image.Exif()
        exif[271] = "Test Camera"
        exif[315] = "Photographer"
        exif[33432] = "Copyright Owner"
        exif[274] = 6
        exif[34665] = {
            36867: "2010:01:02 03:04:05",
            36881: "+08:00",
            37521: "123",
            37500: b"private maker note",
            42033: "private serial",
            40962: 999,
            40963: 999,
            40961: 1,
        }
        exif[34853] = {1: "N", 2: (31, 0, 0), 3: "E", 4: (121, 0, 0)}
        xmp = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            b'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            b'xmlns:exif="http://ns.adobe.com/exif/1.0/" '
            b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            b'<rdf:RDF><rdf:Description exif:GPSLatitude="31,0N" '
            b'dc:rights="Copyright Owner"/></rdf:RDF></x:xmpmeta>'
        )
        chunks = PngImagePlugin.PngInfo()
        chunks.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8"))
        Image.new("RGB", (16, 12)).save(self.source, exif=exif, dpi=(300, 300), pnginfo=chunks)

    def test_date_displays_capture_time_to_seconds_without_timezone_or_fraction(self):
        data = read_photo_metadata(self.source, include_gps_location=False)
        self.assertEqual(data.date, "Sat, 02 Jan 2010 03:04:05")

    def test_date_is_absent_without_valid_capture_time_even_if_other_dates_exist(self):
        Image.new("RGB", (16, 12)).save(self.source)
        self.assertEqual(read_photo_metadata(self.source, include_gps_location=False).date, "")
        for capture in (None, "", "invalid", "2021:02:30 12:00:00"):
            with self.subTest(capture=capture):
                exif = Image.Exif()
                exif[306] = "2010:01:02 03:04:05"
                exif[34665] = {36868: "2010:01:02 03:04:05"}
                if capture is not None:
                    exif[34665][36867] = capture
                Image.new("RGB", (16, 12)).save(self.source, exif=exif)
                with suppress_watermark_logs():
                    date = read_photo_metadata(self.source, include_gps_location=False).date
                self.assertEqual(date, "")

    def test_safe_policy_keeps_ownership_and_dpi_but_rebuilds_geometry_and_removes_gps(self):
        data = collect_metadata([self.source], (100, 200))
        exif = Image.Exif()
        exif.load(data["exif"])
        self.assertEqual(exif[315], "Photographer")
        self.assertEqual(exif[33432], "Copyright Owner")
        self.assertEqual(exif[274], 1)
        self.assertNotIn(34853, exif)
        nested = exif.get_ifd(34665)
        self.assertEqual((nested[40962], nested[40963], nested[40961]), (100, 200, 65535))
        # The shorter visible watermark does not discard capture precision in EXIF.
        self.assertEqual(nested[36867], "2010:01:02 03:04:05")
        self.assertEqual(nested[36881], "+08:00")
        self.assertEqual(nested[37521], "123")
        self.assertNotIn(37500, nested)
        self.assertNotIn(42033, nested)
        np.testing.assert_allclose(data["dpi"], (300, 300), atol=0.01)
        self.assertIn(b"Copyright Owner", data["xmp"])
        self.assertNotIn(b"GPSLatitude", data["xmp"])

    def test_default_gps_lookup_uses_coordinates_and_explicit_false_disables_it(self):
        with patch(
            "watermark_tool.exif_gps.reverse_geocode_location", return_value="Test City"
        ) as lookup:
            self.assertEqual(read_photo_metadata(self.source).location, "Test City")
            self.assertEqual(lookup.call_args.args[:2], (31.0, 121.0))
            lookup.reset_mock()
            self.assertEqual(
                read_photo_metadata(self.source, include_gps_location=False).location, ""
            )
            lookup.assert_not_called()

    def test_metadata_gps_opt_in_and_none_policy(self):
        data = collect_metadata([self.source], (100, 200), preserve_gps=True)
        exif = Image.Exif()
        exif.load(data["exif"])
        self.assertEqual(exif.get_ifd(34853)[1], "N")
        self.assertEqual(collect_metadata([self.source], (100, 200), policy="none"), {})

    def test_collage_omits_single_camera_date_and_location(self):
        second = self.root / "second.png"
        second.write_bytes(self.source.read_bytes())
        data = collect_metadata([self.source, second], (100, 200), preserve_gps=True)
        exif = Image.Exif()
        exif.load(data["exif"])
        self.assertEqual(exif[315], "Photographer")
        self.assertNotIn(271, exif)
        self.assertNotIn(34665, exif)
        self.assertNotIn(34853, exif)
        self.assertNotIn("dpi", data)

    def test_both_export_paths_write_safe_metadata_and_honor_explicit_offline_mode(self):
        for color_mode in ("preserve", "srgb"):
            for suffix in ("png", "jpg"):
                output = self.root / (color_mode + "." + suffix)
                cfg = LayoutConfig(
                    color_mode=color_mode,
                    include_gps_location=False,
                    output_mode="original",
                    show_signature=False,
                    signature_text="",
                    line_length=10,
                    line_left_offset=0,
                    date_font_size=10,
                    info_font_size=10,
                )
                with patch("urllib.request.urlopen") as network, suppress_watermark_logs():
                    make_canvas([self.source], output, cfg)
                network.assert_not_called()
                with Image.open(output) as image:
                    self.assertEqual(image.getexif()[315], "Photographer")
                    self.assertNotIn(34853, image.getexif())
                    np.testing.assert_allclose(image.info["dpi"], (300, 300), atol=0.01)
                    self.assertTrue(image.info["icc_profile"])
                    image.load()
                    xmp = image.info.get("xmp") or image.info.get("XML:com.adobe.xmp")
                    self.assertIn("Copyright Owner", str(xmp))
                    self.assertNotIn("GPSLatitude", str(xmp))


if __name__ == "__main__":
    unittest.main()
