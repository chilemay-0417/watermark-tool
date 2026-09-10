"""Prepare inputs once, calculate shared geometry and dispatch to a color backend."""

from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from . import annotations
from .assets import get_asset_base_dir, load_watermark_assets, prepare_fonts
from .brands import select_logo_paths_for_items
from .color import tag_srgb
from .config import LayoutConfig, PhotoItem
from .drawing import (
    read_image_header, make_rotated_text_image,
    open_image_correct_orientation, save_best_quality_image,
)
from .exif_gps import read_photo_metadata
from .layout import calculate_layout_metrics, validate_layout_params
from .metadata import collect_metadata, read_source_metadata
from .preserved import render_preserved_canvas
from .raster import inspect_raster
from .utils import info, progress


def load_photo_items(photo_paths, config, *, defer_pixels=False, headers=None):
    """准备尺寸、元信息和文字，可延迟解码以免长图合成同时保留所有原图。"""
    items = []

    for index, path in enumerate(photo_paths):
        path = Path(path)
        progress(f"正在准备第 {index + 1}/{len(photo_paths)} 张：{path.name}")

        if not path.exists():
            raise FileNotFoundError(f"找不到照片文件：{path}")

        # Reject unsupported images before any metadata network request.
        image = None if defer_pixels else open_image_correct_orientation(
            path, mode="RGB", background=config.background_color,
        )
        if headers is not None:
            source_size = headers[index].size
            source = headers[index].source_metadata
        elif image is None:
            source_size, source = read_image_header(path)
        else:
            source_size = image.size
            source = read_source_metadata(path)
        metadata = read_photo_metadata(
            path,
            include_gps_location=config.include_gps_location,
            gps_location_language=config.gps_location_language,
            gps_location_timeout=config.gps_location_timeout,
            source=source,
        )
        items.append(PhotoItem(
            path=path,
            image=image,
            source_size=source_size,
            metadata=metadata,
            source_metadata=source,
            settings_image=make_rotated_text_image(
                metadata.settings, config.info_font, config.info_color, config.info_tracking,
            ),
            location_image=make_rotated_text_image(
                metadata.location, config.location_font,
                config.info_color, config.location_tracking,
            ),
        ))

    return items


def print_export_summary(output_path, items, metrics, config):
    """输出排版参数，方便 Finder 错误日志和手动调参时查看。"""
    info(f"已导出：{output_path}")
    info(f"画布尺寸：{metrics.canvas_w} x {metrics.canvas_h}")
    info(f"照片高度 photo_height：{metrics.photo_height}（请求 {config.photo_height}）")
    info(f"横线底部边距 line_bottom_margin：{config.line_bottom_margin}")
    info(f"左右留白 side_margin：{metrics.side_margin}")
    info(f"照片间距 photo_gap：{metrics.photo_gap}")
    info(f"横线左侧偏移 line_left_offset：{config.line_left_offset}")
    info(f"输出模式 output_mode：{config.output_mode}")
    info(f"横线长度 line_length：{config.line_length}")
    info(f"日期字号 date_font_size：{config.date_font_size}")
    info(f"日期字距 date_tracking：{config.date_tracking}")
    info(f"参数字号 info_font_size：{config.info_font_size}")
    info(f"参数字距 info_tracking：{config.info_tracking}")
    info(f"参数距离照片左侧 info_gap_x：{config.info_gap_x}")
    info(f"地点距离照片左侧 location_gap_x：{config.location_gap_x}")
    info(f"参数距离照片底部 info_bottom_gap：{config.info_bottom_gap}")
    info(f"地点字号 location_font_size：{config.location_font_size}")
    info(f"地点字距 location_tracking：{config.location_tracking}")
    info(f"地点和参数距离 info_location_gap：{config.info_location_gap}")
    info(f"追加 GPS 地点 include_gps_location：{config.include_gps_location}")
    info(f"显示签名 show_signature：{config.show_signature}")
    if not config.show_signature:
        info(f"签名替代文字 signature_text：{config.signature_text or '无'}")
        info(f"签名替代文字字号 signature_font_size：{config.signature_font_size}")
    info(f"JPEG 质量 jpeg_quality：{config.jpeg_quality}")
    if config.color_mode == "srgb":
        info("输出色彩：sRGB / SDR / 8 位，已嵌入 ICC 色彩配置")

    for idx, item in enumerate(items, start=1):
        settings_text = item.metadata.settings or "未读取到"
        location_text = item.metadata.location or "未读取到"
        info(f"照片 {idx} 日期：{item.metadata.date}")
        info(f"照片 {idx} 参数：{settings_text}")
        info(f"照片 {idx} 地点：{location_text}")


def make_canvas(photo_paths, output_path, config=None):
    """将照片排版到画布并导出；adaptive 不限制张数或画布宽度。"""
    config = replace(config) if config is not None else LayoutConfig()
    photo_paths = [Path(p) for p in photo_paths]
    output_path = Path(output_path)

    validate_layout_params(photo_count=len(photo_paths), config=config)
    if output_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("输出文件只支持 .jpg、.jpeg 或 .png 后缀。")
    for path in photo_paths:
        if output_path.resolve() == path.resolve() or (
            output_path.exists() and path.exists() and output_path.samefile(path)
        ):
            raise ValueError("输出路径不能与任何输入照片相同，请另选文件名以保留原图。")
    prepare_fonts(config)
    headers = (
        [inspect_raster(path) for path in photo_paths]
        if config.color_mode == "preserve" else None
    )

    base_dir = get_asset_base_dir()
    items = load_photo_items(
        photo_paths, config, defer_pixels=True, headers=headers,
    )

    logo_plan = select_logo_paths_for_items(items, base_dir)
    watermark_assets = load_watermark_assets(
        base_dir=base_dir,
        config=config,
        logo_plan=logo_plan,
    )
    metrics = calculate_layout_metrics(
        items=items,
        config=config,
        watermark_assets=watermark_assets,
    )

    if headers is not None:
        render_preserved_canvas(
            photo_paths, output_path, config, items, headers, watermark_assets, metrics,
        )
    else:
        _render_srgb_canvas(photo_paths, output_path, items, watermark_assets, metrics, config)
    print_export_summary(output_path, items, metrics, config)


def _render_srgb_canvas(photo_paths, output_path, items, watermark_assets, metrics, config):
    """Composite one decoded source at a time in an 8-bit sRGB canvas."""
    if output_path.suffix.lower() != ".png" and metrics.canvas_w > 65500:
        raise ValueError(
            f"合成宽度为 {metrics.canvas_w}px，超过 JPEG 编码器的 65500px 限制。"
            "请用 -o 指定 .png 输出；adaptive 本身不限制宽度。"
        )

    canvas = tag_srgb(Image.new(
        "RGB", (metrics.canvas_w, metrics.canvas_h), config.background_color,
    ))
    draw = ImageDraw.Draw(canvas)
    current_x = metrics.side_margin
    photo_placements = []

    if metrics.photo_height < config.photo_height:
        info(f"video 自动降低照片高度：{config.photo_height} → {metrics.photo_height}px。")

    for idx, item in enumerate(items):
        progress(f"正在处理第 {idx + 1}/{len(items)} 张：{item.path.name}")
        with open_image_correct_orientation(
            item.path, mode="RGB", background=config.background_color,
        ) as original:
            item.image = original.resize(
                (original.size if config.output_mode == "original" else
                 (metrics.photo_widths[idx], metrics.photo_height)), Image.Resampling.LANCZOS,
            )
        placement = annotations.draw_photo_item(
            canvas=canvas,
            draw=draw,
            item=item,
            idx=idx,
            current_x=current_x,
            metrics=metrics,
            config=config,
        )
        photo_placements.append(placement)
        current_x += placement.w + metrics.photo_gap
        item.image.close()
        item.image = None

    annotations.draw_watermark_assets(
        canvas=canvas,
        watermark_assets=watermark_assets,
        photo_placements=photo_placements,
        metrics=metrics,
        config=config,
    )

    metadata = collect_metadata(
        photo_paths, canvas.size, config.metadata_policy, config.preserve_gps,
        sources=[item.source_metadata for item in items],
    )
    progress(f"正在保存：{output_path.name}")
    save_best_quality_image(
        canvas, output_path, jpeg_quality=config.jpeg_quality, metadata=metadata,
        png_compression=config.png_compression,
    )
