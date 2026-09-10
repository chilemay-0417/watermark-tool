"""Native-depth decoding and color conversion, independent of Pillow's 8-bit RGB buffers."""

import ctypes
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image, ImageCms, _imagingcms

from .color import (
    RGB_TO_XYZ,
    SRGB_ICC,
    _exif_color_space,
    _png_matrix,
    decode_transfer,
    require_sdr_transfer,
    reject_hdr_metadata,
)


@lru_cache(maxsize=1)
def lcms():
    # Resolve the LittleCMS already shipped/linked with Pillow, not an unrelated installation.
    try:
        lib = ctypes.CDLL(_imagingcms.__file__)
        signatures = {
            "cmsOpenProfileFromMem": (ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_uint32]),
            "cmsCloseProfile": (ctypes.c_int, [ctypes.c_void_p]),
            "cmsCreateTransform": (
                ctypes.c_void_p,
                [
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                ],
            ),
            "cmsDoTransform": (
                None,
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32],
            ),
            "cmsDeleteTransform": (None, [ctypes.c_void_p]),
            "cmsBuildTabulatedToneCurve16": (
                ctypes.c_void_p,
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint16)],
            ),
            "cmsFreeToneCurve": (None, [ctypes.c_void_p]),
            "cmsCreateRGBProfile": (
                ctypes.c_void_p,
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
            ),
            "cmsSaveProfileToMem": (
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
            ),
        }
        for name, (restype, argtypes) in signatures.items():
            function = getattr(lib, name)
            function.restype, function.argtypes = restype, argtypes
        return lib
    except (OSError, AttributeError) as exc:
        raise RuntimeError(
            "Pillow 的 LittleCMS 无法提供高精度转换；请安装官方 Pillow wheel。"
        ) from exc


def transform_icc(values, source, destination=SRGB_ICC, *, maximum=1):
    """Transform normalized RGB/gray float arrays without an intermediate 8-bit image."""
    lib = lcms()
    channels = values.shape[-1]
    if channels not in (1, 3):
        raise ValueError("高精度 ICC 转换只支持 RGB / 灰度。")
    src_buffer, dst_buffer = (
        ctypes.create_string_buffer(source),
        ctypes.create_string_buffer(destination),
    )
    src = lib.cmsOpenProfileFromMem(src_buffer, len(source))
    dst = lib.cmsOpenProfileFromMem(dst_buffer, len(destination))
    transform = None
    try:
        if not src or not dst:
            raise ValueError("ICC 色彩配置损坏。")
        # FLOAT_SH(1) | COLORSPACE_SH(PT_RGB/PT_GRAY) | CHANNELS_SH(n) | BYTES_SH(4)
        src_type = (1 << 22) | ((4 if channels == 3 else 3) << 16) | (channels << 3) | 4
        dst_type = (1 << 22) | (4 << 16) | (3 << 3) | 4
        transform = lib.cmsCreateTransform(src, src_type, dst, dst_type, 1, 0)
        if not transform:
            raise ValueError("ICC 色彩配置与像素模式不匹配。")
        output = np.empty(values.shape[:-1] + (3,), dtype=np.float32)
        for start in range(0, values.shape[0], 128):
            stripe = np.ascontiguousarray(values[start : start + 128], dtype=np.float32)
            if maximum != 1:
                stripe = stripe / maximum
            target = output[start : start + 128]
            lib.cmsDoTransform(
                transform, stripe.ctypes.data, target.ctypes.data, stripe.size // channels
            )
        if not np.isfinite(output).all():
            raise ValueError("ICC 转换产生非有限色彩值。")
        return output
    finally:
        if transform:
            lib.cmsDeleteTransform(transform)
        if src:
            lib.cmsCloseProfile(src)
        if dst:
            lib.cmsCloseProfile(dst)


def matrix_profile(matrix, transfer):
    """Build an RGB ICC for SDR matrix/TRC metadata (PNG and HEIF)."""
    require_sdr_transfer(transfer)
    lib = lcms()
    columns = np.asarray(matrix).T
    white = columns.sum(axis=0)

    def xyY(xyz):
        return (ctypes.c_double * 3)(xyz[0] / xyz.sum(), xyz[1] / xyz.sum(), 1)

    wp = xyY(white)
    primaries = (ctypes.c_double * 9)(*(v for col in columns for v in xyY(col)))
    codes = np.linspace(0, 1, 4096)[:, None].repeat(3, axis=1)
    table = np.rint(np.clip(decode_transfer(codes, transfer)[:, 0], 0, 1) * 65535).astype(np.uint16)
    curve = lib.cmsBuildTabulatedToneCurve16(
        None, len(table), table.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16))
    )
    profile = None
    try:
        if not curve:
            raise ValueError("无法创建色彩传递曲线。")
        curves = (ctypes.c_void_p * 3)(curve, curve, curve)
        profile = lib.cmsCreateRGBProfile(wp, primaries, curves)
        length = ctypes.c_uint32()
        if not profile or not lib.cmsSaveProfileToMem(profile, None, ctypes.byref(length)):
            raise ValueError("无法构造输出 ICC。")
        data = ctypes.create_string_buffer(length.value)
        if not lib.cmsSaveProfileToMem(profile, data, ctypes.byref(length)):
            raise ValueError("无法序列化输出 ICC。")
        return data.raw[: length.value]
    finally:
        if profile:
            lib.cmsCloseProfile(profile)
        if curve:
            lib.cmsFreeToneCurve(curve)


@lru_cache(maxsize=128)
def icc_color_key(profile):
    """Compare color-bearing tags, ignoring human-readable descriptions and copyright."""
    ignored = {b"desc", b"cprt", b"dmnd", b"dmdd", b"vued"}
    try:
        count = struct.unpack_from(">I", profile, 128)[0]
        if 132 + count * 12 > len(profile):
            raise ValueError("ICC tag table is truncated")
        tags = []
        for i in range(count):
            tag, offset, length = struct.unpack_from(">4sII", profile, 132 + 12 * i)
            if offset + length > len(profile):
                raise ValueError("ICC tag is truncated")
            if tag not in ignored:
                tags.append((tag, profile[offset:offset + length]))
        return ("icc", profile[8:24], profile[64:80], tuple(sorted(tags)))
    except (struct.error, ValueError):
        # Keep malformed profiles distinct; validation still reports the actual input error.
        return ("invalid-icc", profile)


@dataclass
class ColorSpec:
    icc: bytes | None = None
    matrix: np.ndarray = field(default_factory=lambda: RGB_TO_XYZ["srgb"])
    transfer: object = 13
    cicp: bytes | None = None
    chunks: dict = field(default_factory=dict)

    def __post_init__(self):
        require_sdr_transfer(self.transfer)
        if self.cicp and len(self.cicp) == 4:
            require_sdr_transfer(self.cicp[1])

    def profile(self):
        return self.icc or matrix_profile(self.matrix, self.transfer)

    def key(self):
        if self.icc:
            return icc_color_key(self.icc)
        return ("matrix", self.matrix.tobytes(), self.transfer)


@dataclass
class Raster:
    pixels: np.ndarray
    bits: int
    color: ColorSpec
    alpha: np.ndarray | None = None

    @property
    def size(self):
        return self.pixels.shape[1], self.pixels.shape[0]

    @property
    def maximum(self):
        return (1 << self.bits) - 1


@dataclass
class RasterHeader:
    size: tuple
    bits: int
    color: ColorSpec
    has_alpha: bool
    source_metadata: tuple


def inspect_raster(path):
    """Inspect dimensions, output color, depth and metadata without retaining pixel arrays."""
    from .drawing import HEIC_SUFFIXES, RAW_SUFFIXES, reject_tiff_input
    from .metadata import read_source_metadata

    path = Path(path)
    reject_tiff_input(path)
    if path.suffix.lower() in RAW_SUFFIXES:
        raise ValueError("不再支持 RAW 输入；请先导出 PNG 或 JPEG。")
    if path.suffix.lower() in HEIC_SUFFIXES:
        import pillow_heif

        container = pillow_heif.open_heif(path, convert_hdr_to_8bit=False, hdr_to_16bit=False)
        frame = container[container.primary_index]
        color = color_spec(frame.info)
        bits = int(frame.mode.partition(";")[2] or 8)
        size = frame.size
        alpha = "A" in frame.mode or "a" in frame.mode
        source = read_source_metadata(path)
    else:
        with Image.open(path) as image:
            reject_tiff_input(path, image.format)
            if image.mode in ("CMYK", "LAB"):
                raise ValueError("保真路径不支持 CMYK/Lab；请用 --color-mode srgb 显式转换。")
            source = read_source_metadata(path, image)
            chunks = png_color_chunks(path) if image.format == "PNG" else {}
            color = color_spec(image.info, image, chunks)
            bits = max(8, chunks[b"IHDR"][8]) if chunks else 8
            size = image.size
            if source[0].get(274) in (5, 6, 7, 8):
                size = size[::-1]
            alpha = "A" in image.getbands() or "transparency" in image.info
    # Gray ICC sources are normalized to RGB by read_raster before compositing.
    if (color.icc and
            ImageCms.ImageCmsProfile(BytesIO(color.icc)).profile.xcolor_space.strip() == "GRAY"):
        color = ColorSpec(icc=SRGB_ICC)
    return RasterHeader(size, bits, color, alpha, source)


def png_color_chunks(path):
    result = {}
    with open(path, "rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("PNG 文件签名无效。")
        while True:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("PNG 文件不完整。")
            length, tag = struct.unpack(">I4s", header)
            if tag in (b"IDAT", b"IEND"):
                break
            if tag in (b"IHDR", b"cICP", b"gAMA", b"cHRM", b"sRGB", b"sBIT"):
                if length > 1024:
                    raise ValueError("PNG 色彩块长度无效。")
                data, checksum = stream.read(length), stream.read(4)
                if (
                    len(checksum) != 4
                    or zlib.crc32(tag + data) & 0xFFFFFFFF != struct.unpack(">I", checksum)[0]
                ):
                    raise ValueError("PNG 色彩块校验失败。")
                result[tag] = data
            else:
                stream.seek(length + 4, 1)
    return result


def color_spec(metadata, image=None, chunks=None):
    reject_hdr_metadata(metadata)
    chunks = chunks or {}
    cicp = chunks.get(b"cICP")
    nclx = metadata.get("nclx_profile")
    if cicp is not None:
        if len(cicp) != 4 or cicp[2] != 0 or cicp[3] != 1:
            raise ValueError("暂不支持该 PNG cICP 编码或窄范围；请先导出全范围图片。")
        primaries, transfer = cicp[:2]
    elif nclx:
        primaries = int(nclx.get("color_primaries", 2))
        transfer = int(nclx.get("transfer_characteristics", 2))
    else:
        primaries, transfer = 2, 2
    require_sdr_transfer(transfer)
    # PNG cICP has precedence; HEIF SDR ICC remains authoritative when supplied.
    profile = metadata.get("icc_profile")
    if profile and cicp is None:
        try:
            parsed = ImageCms.ImageCmsProfile(BytesIO(profile))
            if parsed.profile.xcolor_space.strip() not in ("RGB", "GRAY"):
                raise ValueError("保真路径只支持 RGB / 灰度 ICC；CMYK/Lab 请显式选择 sRGB 转换。")
        except (ImageCms.PyCMSError, OSError, TypeError) as exc:
            raise ValueError("ICC 色彩配置损坏。") from exc
        return ColorSpec(icc=profile)
    if cicp is not None or nclx:
        if primaries == 2 and transfer in (2, 13):
            primaries = 1
        if primaries == 1 and transfer == 2:
            transfer = 13
        spaces = {1: "srgb", 9: "rec2020", 12: "display-p3"}
        if primaries not in spaces:
            raise ValueError(f"无法解释色彩原色 {primaries}。")
        matrix = RGB_TO_XYZ[spaces[primaries]]
        decode_transfer(np.zeros((1, 3)), transfer)
        return ColorSpec(
            matrix=matrix,
            transfer=transfer,
            cicp=bytes((primaries, transfer, 0, 1)),
        )
    if "srgb" not in metadata and image is not None and _exif_color_space(image) == "adobe-rgb":
        return ColorSpec(matrix=RGB_TO_XYZ["adobe-rgb"], transfer="adobe-rgb")
    if "srgb" not in metadata and ("gamma" in metadata or "chromaticity" in metadata):
        gamma = metadata.get("gamma")
        if gamma is not None and (not np.isfinite(gamma) or gamma <= 0):
            raise ValueError("PNG gamma 色彩信息无效。")
        matrix = (
            _png_matrix(metadata["chromaticity"])
            if "chromaticity" in metadata
            else RGB_TO_XYZ["srgb"]
        )
        return ColorSpec(
            matrix=matrix,
            transfer=("gamma", gamma) if gamma else 13,
            chunks={k: v for k, v in chunks.items() if k in (b"gAMA", b"cHRM")},
        )
    return ColorSpec(icc=SRGB_ICC)


def orient_array(array, orientation):
    if orientation == 2:
        return array[:, ::-1]
    if orientation == 3:
        return array[::-1, ::-1]
    if orientation == 4:
        return array[::-1]
    if orientation == 5:
        return np.swapaxes(array, 0, 1)
    if orientation == 6:
        return np.rot90(array, 3)
    if orientation == 7:
        return np.swapaxes(array, 0, 1)[::-1, ::-1]
    if orientation == 8:
        return np.rot90(array)
    return array


def read_pillow_samples(image):
    """Decode 8-bit samples in Pillow's native codec, including palette and color-key alpha."""
    transparent = "A" in image.getbands() or "transparency" in image.info
    grayscale = image.mode in {"1", "L", "LA"}
    mode = ("LA" if transparent else "L") if grayscale else ("RGBA" if transparent else "RGB")
    if image.mode == mode:
        samples = np.asarray(image)
    else:
        with image.convert(mode) as decoded:
            samples = np.asarray(decoded)
    if samples.ndim == 2:
        samples = samples[..., None]
    if transparent:
        return samples[..., :-1], samples[..., -1].copy()
    return samples, None


def read_raster(path, *, source_metadata=None):
    """Read original encoded RGB samples, retaining precision and color meaning."""
    from .drawing import HEIC_SUFFIXES, RAW_SUFFIXES, reject_tiff_input
    from .metadata import read_source_metadata

    path = Path(path)
    suffix = path.suffix.lower()
    reject_tiff_input(path)
    if suffix in RAW_SUFFIXES:
        raise ValueError("不再支持 RAW 输入；请先导出 PNG 或 JPEG。")
    alpha = None
    if suffix in HEIC_SUFFIXES:
        import pillow_heif

        with path.open("rb") as stream:
            container = pillow_heif.open_heif(stream, convert_hdr_to_8bit=False, hdr_to_16bit=False)
        frame = container[container.primary_index]
        reject_hdr_metadata(frame.info)
        pixels = np.array(frame)[: frame.size[1], : frame.size[0]]
        mode, _, depth = frame.mode.partition(";")
        bits = int(depth or 8)
        if mode not in ("RGB", "RGBA", "RGBa", "L", "LA", "La", "I"):
            raise ValueError(f"不支持 HEIF 模式 {mode}。")
        if pixels.ndim == 2:
            pixels = pixels[..., None]
        if mode in ("RGBA", "RGBa", "LA", "La"):
            alpha, pixels = pixels[..., -1].copy(), pixels[..., :-1]
        if mode in ("RGBa", "La"):
            opacity = alpha[..., None].astype(np.float64) / ((1 << bits) - 1)
            pixels = np.rint(
                np.clip(
                    np.divide(
                        pixels,
                        opacity,
                        out=np.zeros(pixels.shape, dtype=np.float64),
                        where=opacity > 0,
                    ),
                    0,
                    (1 << bits) - 1,
                )
            ).astype(pixels.dtype)
        color = color_spec(frame.info)
    else:
        with Image.open(path) as image:
            reject_tiff_input(path, image.format)
            if source_metadata is None:
                source_metadata = read_source_metadata(path, image)
            else:
                image.info.update(source_metadata[3])
            orientation = image.getexif().get(274, 1)
            metadata = image.info.copy()
            reject_hdr_metadata(metadata)
            if image.mode in ("CMYK", "LAB"):
                raise ValueError("保真 PNG 路径不支持 CMYK/Lab；请用 --color-mode srgb 显式转换。")
            chunks = png_color_chunks(path) if image.format == "PNG" else {}
            color = color_spec(metadata, image, chunks)
            if image.format == "PNG" and chunks[b"IHDR"][8] <= 8:
                # Pillow's native decoder avoids Python loops over every pixel.
                # Never use this path for 16-bit RGB: Pillow would discard its low bits.
                bits = 8
                pixels, alpha = read_pillow_samples(image)
            elif image.format == "PNG":
                from .png_decoder import decode_png16

                color_type = chunks[b"IHDR"][9]
                pixels = decode_png16(path, color_type)
                bits = pixels.dtype.itemsize * 8
                if pixels.ndim == 2:
                    pixels = pixels[..., None]
                if pixels.shape[-1] in (2, 4):
                    alpha, pixels = pixels[..., -1].copy(), pixels[..., :-1]
                if color_type in (0, 4):
                    pixels = pixels[..., :1]
                if color_type in (0, 2) and "transparency" not in metadata:
                    alpha = None
                if "transparency" in metadata and color_type in (0, 2):
                    # libspng's 16-bit color-key alpha can be opaque; compare native samples.
                    key = np.asarray(metadata["transparency"])
                    alpha = np.where(np.all(pixels == key, axis=-1), 0, 65535).astype(np.uint16)
            else:
                bits = 8
                pixels, alpha = read_pillow_samples(image)
            pixels = orient_array(pixels, orientation)
            if alpha is not None:
                alpha = orient_array(alpha, orientation)
    if pixels.shape[-1] == 1:
        if (
            color.icc
            and ImageCms.ImageCmsProfile(BytesIO(color.icc)).profile.xcolor_space.strip() == "GRAY"
        ):
            converted = transform_icc(pixels.astype(np.float32) / ((1 << bits) - 1), color.icc)
            bits = max(8, bits)
            pixels = np.rint(np.clip(converted, 0, 1) * ((1 << bits) - 1)).astype(
                np.uint16 if bits > 8 else np.uint8
            )
            color = ColorSpec(icc=SRGB_ICC)
        else:
            pixels = np.repeat(pixels, 3, axis=2)
    if pixels.shape[-1] != 3:
        raise ValueError("无法解释图片通道布局。")
    return Raster(np.ascontiguousarray(pixels), bits, color, alpha)


def resize_samples(values, size):
    """Retain native samples when size is unchanged; resize float planes otherwise."""
    if (values.shape[1], values.shape[0]) == size:
        return values
    output = np.empty((size[1], size[0], values.shape[-1]), dtype=np.float32)
    for c in range(values.shape[-1]):
        # Convert one integer plane inside Pillow; avoid both a full NumPy float copy
        # and Pillow's second float copy. F-mode still performs the same precise Lanczos resize.
        with Image.fromarray(values[..., c]) as plane:
            floating = plane.convert("F")
        with floating, floating.resize(size, Image.Resampling.LANCZOS) as resized:
            output[..., c] = np.asarray(resized)
    return output


def srgb_to_color(values, color):
    if color.icc:
        if icc_color_key(color.icc) == icc_color_key(SRGB_ICC):
            return values
        return transform_icc(values, SRGB_ICC, color.icc)
    linear = decode_transfer(values, 13)
    transform = np.linalg.inv(color.matrix) @ RGB_TO_XYZ["srgb"]
    rgb = (linear.reshape(-1, 3) @ transform.T).reshape(linear.shape)
    rgb = np.maximum(rgb, 0)
    t = color.transfer
    require_sdr_transfer(t)
    if t == 13:
        return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - 0.055)
    if t == 8:
        return rgb
    if t in (1, 6, 14, 15):
        a, b = (1.09929682680944, 0.018053968510807) if t in (14, 15) else (1.099, 0.018)
        return np.where(rgb < b, 4.5 * rgb, a * rgb**0.45 - (a - 1))
    exponent = (
        t[1]
        if isinstance(t, tuple)
        else 256 / 563
        if t == "adobe-rgb"
        else 1 / (2.2 if t == 4 else 2.8)
    )
    return rgb**exponent


def raster_to_srgb(raster, mode="RGB", background=(255, 255, 255)):
    from .color import render_rgb_array, finish_srgb, tag_srgb

    if raster.color.icc:
        values = raster.pixels.astype(np.float32) / raster.maximum
        if icc_color_key(raster.color.icc) != icc_color_key(SRGB_ICC):
            values = transform_icc(values, raster.color.icc)
        image = tag_srgb(Image.fromarray(np.rint(np.clip(values, 0, 1) * 255).astype(np.uint8)))
    else:
        image = render_rgb_array(
            raster.pixels, raster.maximum, raster.color.matrix, raster.color.transfer
        )
    alpha = (
        Image.fromarray(
            np.rint(raster.alpha.astype(np.float32) / raster.maximum * 255).astype(np.uint8)
        )
        if raster.alpha is not None
        else None
    )
    return finish_srgb(image, mode, background, alpha)
