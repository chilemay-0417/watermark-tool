"""Composite in the output color space at native precision, quantizing only at export."""

from pathlib import Path
import os
import struct
import tempfile
import zlib

import numpy as np
from PIL import Image, ImageDraw

from .config import LayoutMetrics, PhotoPlacement, LOGO_SIGNATURE_GAP
from .color import require_sdr_transfer
from .metadata import collect_metadata
from .raster import (
    ColorSpec,
    inspect_raster,
    matrix_profile,
    read_raster,
    resize_samples,
    srgb_to_color,
    transform_icc,
)
from .utils import info, warn


def png_chunk(stream, tag, data):
    stream.write(struct.pack(">I", len(data)))
    stream.write(tag)
    stream.write(data)
    stream.write(struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, pixels, bits, color, metadata):
    """Stream 8/16-bit lossless PNG with matching color and rebuilt metadata."""
    require_sdr_transfer(color.transfer)
    if color.cicp:
        require_sdr_transfer(color.cicp[1])
    with open(path, "wb") as stream:
        stream.write(b"\x89PNG\r\n\x1a\n")
        png_chunk(
            stream,
            b"IHDR",
            struct.pack(
                ">IIBBBBB",
                pixels.shape[1],
                pixels.shape[0],
                bits,
                6 if pixels.shape[-1] == 4 else 2,
                0,
                0,
                0,
            ),
        )
        if color.cicp:
            png_chunk(stream, b"cICP", color.cicp)
        png_chunk(stream, b"iCCP", b"Output\0\0" + zlib.compress(color.profile()))
        if metadata.get("exif"):
            png_chunk(stream, b"eXIf", metadata["exif"].removeprefix(b"Exif\0\0"))
        if metadata.get("dpi"):
            x, y = metadata["dpi"]
            png_chunk(stream, b"pHYs", struct.pack(">IIB", round(x / 0.0254), round(y / 0.0254), 1))
        if metadata.get("xmp"):
            png_chunk(stream, b"iTXt", b"XML:com.adobe.xmp\0\0\0\0\0" + metadata["xmp"])
        compressor = zlib.compressobj(6)
        for row in pixels:
            data = row.astype(">u2" if bits == 16 else np.uint8).tobytes()
            encoded = compressor.compress(b"\0" + data)
            if encoded:
                png_chunk(stream, b"IDAT", encoded)
        png_chunk(stream, b"IDAT", compressor.flush())
        png_chunk(stream, b"IEND", b"")


def choose_color(rasters):
    first = rasters[0].color
    if all(r.color.key() == first.key() for r in rasters):
        return first
    # ProPhoto RGB contains the usual sRGB, Display P3 and Adobe RGB photographic gamuts.
    # Reject any out-of-range pixels during conversion instead of silently clipping them.
    matrix = np.array(
        [
            [0.7977666449, 0.1351812974, 0.0313477341],
            [0.2880748288, 0.7118352342, 0.0000899369],
            [0, 0, 0.8251046025],
        ]
    )
    info("混合色域：使用 ProPhoto RGB 合成并嵌入 ICC。建议 PNG 16 位以减少量化损失。")
    return ColorSpec(icc=matrix_profile(matrix, ("gamma", 1 / 1.8)))


def convert_samples(raster, target):
    if raster.color.key() != target.key():
        values = transform_icc(
            raster.pixels, raster.color.profile(), target.profile(), maximum=raster.maximum,
        )
        if values.min() < -1e-4 or values.max() > 1.0001:
            raise ValueError("原图部分颜色超出合成色域，已停止以避免裁切；请分别导出。")
        return values
    return raster.pixels.astype(np.float32) / raster.maximum


def original_metrics(items, cfg, assets):
    from .renderer import get_annotation_extents, get_photo_marks
    from .drawing import get_text_bbox_with_tracking

    left, right = get_annotation_extents(items, cfg, assets)
    sizes = [item.source_size for item in items]
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    footer_extra = []
    for item, size in zip(items, sizes, strict=True):
        bbox = get_text_bbox_with_tracking(
            measure, item.metadata.date, cfg.date_font, cfg.date_tracking,
        ) or (0, 0, 0, 0)
        footer_extra.append(max(0, cfg.line_left_offset + max(cfg.line_length, bbox[2]) - size[0]))
    margin = max(80, left[0] + 20, right[-1] + 20, footer_extra[-1] + 20)
    gap = max([margin] + [right[i] + left[i + 1] + 40 for i in range(len(items) - 1)]
              + [extra + 20 for extra in footer_extra[:-1]])
    height = max(size[1] for size in sizes)
    top = 100
    # Enough room for long vertical marks even on small source images.
    for item, mark in zip(items, get_photo_marks(assets, len(items)), strict=True):
        mark_h = mark.logo.height if mark.logo else 0
        if mark.include_signature and assets.signature:
            mark_h += assets.signature.height + (LOGO_SIGNATURE_GAP if mark.logo else 0)
        texts = [im for im in (item.settings_image, item.location_image) if im is not None]
        text_h = sum(im.height for im in texts) + cfg.info_bottom_gap
        if len(texts) == 2:
            text_h += cfg.info_location_gap
        top = max(top, max(mark_h, text_h) - item.source_size[1] + 20)
    return LayoutMetrics(
        sum(s[0] for s in sizes) + 2 * margin + (len(items) - 1) * gap,
        top + height + max(80, cfg.line_bottom_margin) + 40,
        gap,
        top,
        margin,
        height,
        tuple(s[0] for s in sizes),
    )


def make_preserved_canvas(paths, output_path, config):
    from .renderer import (
        prepare_fonts,
        load_photo_items,
        get_asset_base_dir,
        select_logo_paths_for_items,
        load_watermark_assets,
        calculate_layout_metrics,
        draw_photo_item,
        draw_watermark_assets,
        print_export_summary,
    )

    prepare_fonts(config)
    # Inspect every source first, then hold at most one decoded photograph during compositing.
    headers = [inspect_raster(path) for path in paths]
    target = choose_color(headers)
    is_png = output_path.suffix.lower() == ".png"
    bits = (
        16
        if is_png
        and (
            max(r.bits for r in headers) > 8 or any(r.color.key() != target.key() for r in headers)
        )
        else 8
    )
    if not is_png and max(r.bits for r in headers) > 8:
        warn("JPEG 只支持此路径的 8 位输出，原图位深将降低；保留位深请改用 .png。")
    items = load_photo_items(paths, config, defer_pixels=True, headers=headers)
    base = get_asset_base_dir()
    assets = load_watermark_assets(base, config, logo_plan=select_logo_paths_for_items(items, base))
    metrics = (
        original_metrics(items, config, assets)
        if config.output_mode == "original"
        else calculate_layout_metrics(items, config, assets)
    )
    if not is_png and max(metrics.canvas_w, metrics.canvas_h) > 65500:
        raise ValueError("成片尺寸超过 JPEG 65500px 限制，请使用 .png。")
    # Pillow draws annotations only. Source photo pixels never pass through this 8-bit canvas.
    annotations = Image.new("RGB", (metrics.canvas_w, metrics.canvas_h), config.background_color)
    draw = ImageDraw.Draw(annotations)
    placements = []
    current_x = metrics.side_margin
    for idx, (item, header) in enumerate(zip(items, headers, strict=True)):
        size = (
            header.size
            if config.output_mode == "original"
            else (metrics.photo_widths[idx], metrics.photo_height)
        )
        item.image = Image.new("RGB", size, config.background_color)
        placement = draw_photo_item(
            canvas=annotations,
            draw=draw,
            item=item,
            idx=idx,
            current_x=current_x,
            metrics=metrics,
            config=config,
        )
        placements.append(PhotoPlacement(placement.x, placement.y, size[0], size[1]))
        item.image.close()
        item.image = None
        current_x += size[0] + metrics.photo_gap
    draw_watermark_assets(annotations, assets, placements, metrics, config)
    dtype, maximum = (np.uint16, 65535) if bits == 16 else (np.uint8, 255)
    has_alpha = is_png and any(header.has_alpha for header in headers)
    output = np.empty((metrics.canvas_h, metrics.canvas_w, 4 if has_alpha else 3), dtype=dtype)
    if has_alpha:
        output[..., 3] = maximum
    for start in range(0, metrics.canvas_h, 128):
        stripe = (
            np.asarray(
                annotations.crop((0, start, metrics.canvas_w, min(start + 128, metrics.canvas_h)))
            ).astype(np.float32)
            / 255
        )
        converted = srgb_to_color(stripe, target)
        output[start : start + len(stripe), :, :3] = np.rint(
            np.clip(converted, 0, 1) * maximum
        ).astype(dtype)
    annotations.close()
    for item, header, placement in zip(items, headers, placements, strict=True):
        raster = read_raster(item.path, source_metadata=header.source_metadata)
        if raster.size != header.size or raster.color.key() != header.color.key():
            raise ValueError("照片在处理过程中发生变化，请重新运行。")
        size = (placement.w, placement.h)
        alpha = resized_alpha = None
        same_color = raster.color.key() == target.key()
        # Resize integer source planes before allocating normalized RGB, keeping large JPEGs lean.
        values = raster.pixels if same_color else convert_samples(raster, target)
        scale = raster.maximum if same_color else 1
        if size != raster.size:
            if raster.alpha is not None:
                alpha = raster.alpha.astype(np.float32)[..., None] / raster.maximum
                resized_alpha = np.clip(resize_samples(alpha, size), 0, 1)
                values = np.divide(
                    resize_samples(values * alpha, size),
                    resized_alpha,
                    out=np.zeros((size[1], size[0], 3), dtype=np.float32),
                    where=resized_alpha > 0,
                )
                opacity = resized_alpha[..., 0]
            else:
                values = resize_samples(values, size)
                opacity = None
        else:
            opacity = (
                raster.alpha.astype(np.float32) / raster.maximum
                if raster.alpha is not None
                else None
            )
        region = output[
            placement.y : placement.y + placement.h, placement.x : placement.x + placement.w
        ]
        if opacity is not None and not is_png:
            bg = srgb_to_color(
                np.asarray([[config.background_color]], dtype=np.float32) / 255, target
            )
            warn("JPEG 不支持透明度，已按画布背景合成；保留透明度请使用 PNG。")
        # Quantize/composite strips instead of allocating several full-size float photographs.
        for start in range(0, placement.h, 128):
            chunk = values[start:start + 128].astype(np.float32) / scale
            if opacity is not None and not is_png:
                a = opacity[start:start + 128, :, None]
                chunk = chunk * a + bg * (1 - a)
            region[start:start + 128, :, :3] = np.rint(
                np.clip(chunk, 0, 1) * maximum,
            ).astype(dtype)
            if has_alpha:
                region[start:start + 128, :, 3] = (
                    maximum if opacity is None else
                    np.rint(opacity[start:start + 128] * maximum).astype(dtype)
                )
        # Do not retain the previous source or its float working buffers while decoding the next.
        del raster, values, opacity, alpha, resized_alpha, chunk
    metadata = collect_metadata(
        paths, (metrics.canvas_w, metrics.canvas_h), config.metadata_policy, config.preserve_gps,
        sources=[header.source_metadata for header in headers],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".watermark-", suffix=output_path.suffix, dir=output_path.parent, delete=False
    ) as temporary:
        temp_path = Path(temporary.name)
    try:
        if is_png:
            write_png(temp_path, output, bits, target, metadata)
        else:
            Image.fromarray(output).save(
                temp_path,
                format="JPEG",
                quality=config.jpeg_quality,
                subsampling=0,
                icc_profile=target.profile(),
                **metadata,
            )
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    print_export_summary(output_path, items, metrics, config)
    info(
        f"输出：{'PNG 无损' if is_png else 'JPEG 质量 ' + str(config.jpeg_quality)} / {bits} 位 / "
        "SDR / 保留来源色域或使用 ProPhoto RGB 合成"
    )
    if config.output_mode != "original":
        info("当前布局会缩放照片；原尺寸输出请使用 --output-mode original。")
