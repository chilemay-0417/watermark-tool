"""Convert decoded pixels to the common, explicitly tagged sRGB/SDR working space.

ICC transforms use LittleCMS; RGB matrices and SDR transfer functions follow CSS Color 4.
"""

from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageCms



SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
SRGB_ICC = SRGB_PROFILE.tobytes()
RGB_TO_XYZ = {
    "srgb": np.array([
        [0.4123907993, 0.3575843394, 0.1804807884],
        [0.2126390059, 0.7151686788, 0.0721923154],
        [0.0193308187, 0.1191947798, 0.9505321522],
    ]),
    "display-p3": np.array([
        [0.4865709486, 0.2656676932, 0.1982172852],
        [0.2289745641, 0.6917385218, 0.0792869141],
        [0.0, 0.0451133819, 1.0439443689],
    ]),
    "rec2020": np.array([
        [0.6369580483, 0.1446169036, 0.1688809752],
        [0.2627002120, 0.6779980715, 0.0593017165],
        [0.0, 0.0280726930, 1.0609850577],
    ]),
    "adobe-rgb": np.array([
        [0.5766690429, 0.1855582379, 0.1882286462],
        [0.2973449753, 0.6273635663, 0.0752914585],
        [0.0270313614, 0.0706888525, 0.9913375368],
    ]),
}
XYZ_TO_SRGB = np.linalg.inv(RGB_TO_XYZ["srgb"])
GRAY16_TO_8 = np.rint(np.arange(65536) / 257).astype(np.uint8)


def require_sdr_transfer(transfer):
    if transfer in (16, 18):
        raise ValueError("不再支持 HDR 图片；请先在照片编辑软件中导出 SDR 图片。")


def reject_hdr_metadata(metadata):
    """Reject recognizable unsupported input; no HDR decoding or fallback is performed."""
    nclx = metadata.get("nclx_profile") or {}
    require_sdr_transfer(int(nclx.get("transfer_characteristics", 2)))
    xmp = metadata.get("xmp") or metadata.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8")
    if any(marker in xmp.lower() for marker in (b"hdr-gain-map", b"hdrgainmap")) or any(
        "gain" in str(key).lower() for key in metadata.get("aux", {})
    ):
        raise ValueError("不再支持 HDR 增益图图片；请先导出 SDR 图片。")


def tag_srgb(image):
    """Keep the working-space tag, without carrying stale source metadata forward."""
    image.info.clear()
    image.info["icc_profile"] = SRGB_ICC
    return image


def encode_srgb(linear):
    linear = np.clip(linear, 0, 1)
    return np.where(linear <= 0.0031308, 12.92 * linear,
                    1.055 * linear ** (1 / 2.4) - 0.055)


def decode_transfer(rgb, transfer):
    """Decode full-range RGB; libheif has already expanded YCbCr video range."""
    require_sdr_transfer(transfer)
    if transfer == 13:  # IEC 61966-2-1 / sRGB
        return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    if transfer in (1, 6, 14, 15):  # BT.709 / SMPTE 170M / BT.2020
        alpha = 1.09929682680944 if transfer in (14, 15) else 1.099
        beta = 0.018053968510807 if transfer in (14, 15) else 0.018
        return np.where(rgb < 4.5 * beta, rgb / 4.5,
                        ((rgb + alpha - 1) / alpha) ** (1 / 0.45))
    if transfer in (4, 5):
        return rgb ** (2.2 if transfer == 4 else 2.8)
    if transfer == "adobe-rgb":
        return rgb ** (563 / 256)
    if isinstance(transfer, tuple) and transfer[0] == "gamma":
        return rgb ** (1 / transfer[1])
    if transfer == 8:  # linear
        return rgb
    raise ValueError(f"不支持的色彩传递函数 {transfer}；请先导出带 ICC 的 sRGB 图片。")


def render_rgb_array(pixels, maximum, color_space="srgb", transfer=13):
    """Transform high-depth RGB before final 8-bit quantization, in bounded strips."""
    matrix = RGB_TO_XYZ[color_space] if isinstance(color_space, str) else color_space
    transform = XYZ_TO_SRGB @ matrix
    result = np.empty(pixels.shape[:2] + (3,), dtype=np.uint8)
    for start in range(0, pixels.shape[0], 128):
        encoded = pixels[start:start + 128, :, :3].astype(np.float64) / maximum
        linear = decode_transfer(np.clip(encoded, 0, 1), transfer)
        # Avoid batched matmul crashes with macOS Accelerate NumPy wheels.
        rgb = (linear.reshape(-1, 3) @ transform.T).reshape(linear.shape)
        result[start:start + 128] = np.rint(encode_srgb(rgb) * 255).astype(np.uint8)
    return tag_srgb(Image.fromarray(result))


@lru_cache(maxsize=16)
def _icc_transform(profile_bytes, mode):
    profile = ImageCms.ImageCmsProfile(BytesIO(profile_bytes))
    return ImageCms.buildTransformFromOpenProfiles(
        profile, SRGB_PROFILE, mode, "RGB",
        renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
    )


def _exif_color_space(image):
    exif = image.getexif()
    data = exif.get_ifd(34665) if 34665 in exif else exif
    if data.get(40961) == 2:
        return "adobe-rgb"
    if 40965 in data:
        index = exif.get_ifd(40965).get(1)
        if index in ("R03", b"R03", b"R03\x00"):
            return "adobe-rgb"
    return "srgb"


def _gray_to_8(image):
    if image.mode.startswith("I;16") or image.mode == "I":
        samples = np.asarray(image)
        if samples.min() < 0 or samples.max() > 65535:
            raise ValueError("整数灰度超出 0–65535；请先转换为有明确色彩范围的图片。")
        return Image.fromarray(GRAY16_TO_8[samples])
    if image.mode == "F":
        raise ValueError("浮点图片缺少明确的亮度范围；请先导出带 ICC 的 PNG。")
    return image


def _png_matrix(chromaticity):
    """Build an RGB->XYZ D65 matrix from PNG cHRM, adapting its white with Bradford."""
    values = np.asarray(chromaticity, dtype=np.float64)
    if values.shape != (8,) or not np.isfinite(values).all():
        raise ValueError("PNG cHRM 色度信息无效。")
    xy = values.reshape(4, 2)
    if np.any(xy <= 0) or np.any(xy.sum(axis=1) > 1.0001):
        raise ValueError("PNG cHRM 色度信息无效。")
    xyz = np.column_stack((xy[:, 0] / xy[:, 1], np.ones(4),
                           (1 - xy.sum(axis=1)) / xy[:, 1]))
    white, primaries = xyz[0], xyz[1:].T
    try:
        matrix = primaries * np.linalg.solve(primaries, white)
    except np.linalg.LinAlgError as exc:
        raise ValueError("PNG cHRM 原色矩阵不可逆。") from exc
    bradford = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367],
                        [0.0389, -0.0685, 1.0296]])
    d65 = RGB_TO_XYZ["srgb"].sum(axis=1)
    adaptation = np.linalg.inv(bradford) @ np.diag((bradford @ d65) / (bradford @ white))
    return adaptation @ bradford @ matrix


def finish_srgb(image, mode="RGB", background=(255, 255, 255), alpha=None):
    """Preserve alpha for marks, or composite photos against the actual background."""
    if mode not in ("RGB", "RGBA"):
        raise ValueError("色彩管理输出只支持 RGB 或 RGBA。")
    if alpha is not None:
        image = image.convert("RGBA")
        image.putalpha(alpha)
    if mode == "RGBA":
        return tag_srgb(image.convert("RGBA"))
    if image.mode == "RGBA":
        backing = Image.new("RGBA", image.size, (*background, 255))
        image = Image.alpha_composite(backing, image)
    return tag_srgb(image.convert("RGB"))


def normalize_image(image, mode="RGB", background=(255, 255, 255)):
    """Normalize ICC-tagged, untagged, palette, grayscale, and transparent images."""
    image.load()
    reject_hdr_metadata(image.info)
    metadata = image.info.copy()
    alpha = None
    if "A" in image.getbands() or "a" in image.getbands() or "transparency" in metadata:
        straight = image.convert("LA") if image.mode == "La" else image
        alpha = straight.convert("RGBA").getchannel("A")
        if image.mode.startswith("I;16") or image.mode == "I":
            alpha = Image.fromarray(np.where(np.asarray(image) == metadata["transparency"],
                                             0, 255).astype(np.uint8))
    working = _gray_to_8(image)
    if working.mode in ("RGBa", "La"):
        working = working.convert("RGBA" if working.mode == "RGBa" else "LA")
    if working.mode not in ("RGB", "L", "CMYK", "LAB"):
        working = working.convert("L" if working.mode in ("1", "LA", "La") else "RGB")
    profile = metadata.get("icc_profile")
    if profile:
        try:
            if profile != SRGB_ICC or working.mode != "RGB":
                working = ImageCms.applyTransform(working, _icc_transform(profile, working.mode))
        except (ImageCms.PyCMSError, OSError, ValueError, TypeError) as exc:
            raise ValueError("ICC 色彩配置损坏或与像素模式不匹配，无法可靠转换为 sRGB。") from exc
    elif working.mode == "CMYK":
        raise ValueError("CMYK 图片缺少 ICC 色彩配置；请先在编辑软件中导出为 sRGB。")
    elif working.mode == "LAB":
        working = ImageCms.profileToProfile(
            working, ImageCms.createProfile("LAB"), SRGB_PROFILE, outputMode="RGB",
        )
    elif "srgb" not in metadata and _exif_color_space(image) == "adobe-rgb":
        working = render_rgb_array(np.asarray(working.convert("RGB")), 255,
                                   "adobe-rgb", "adobe-rgb")
    elif "srgb" not in metadata and ("gamma" in metadata or "chromaticity" in metadata):
        transfer = 13
        if "gamma" in metadata:
            gamma = float(metadata["gamma"])
            if not np.isfinite(gamma) or gamma <= 0:
                raise ValueError("PNG 的 gamma 色彩信息无效。")
            transfer = ("gamma", gamma)
        matrix = (_png_matrix(metadata["chromaticity"]) if "chromaticity" in metadata
                  else RGB_TO_XYZ["srgb"])
        if image.mode.startswith("I;16") or image.mode == "I":
            samples = np.repeat(np.asarray(image)[..., None], 3, axis=2)
            working = render_rgb_array(samples, 65535, matrix, transfer)
        else:
            working = render_rgb_array(np.asarray(working.convert("RGB")), 255, matrix, transfer)
    return finish_srgb(working, mode, background, alpha)


def open_heif_srgb(path, mode="RGB", background=(255, 255, 255)):
    """Native-depth ICC/NCLX transform, quantizing only after conversion."""
    from .raster import read_raster, raster_to_srgb
    return raster_to_srgb(read_raster(path), mode, background)
