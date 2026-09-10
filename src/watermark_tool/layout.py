"""Shared geometry and validation for video, adaptive and original layouts."""

import math

from PIL import Image, ImageDraw

from .config import CANVAS_H, CANVAS_W, LOGO_SIGNATURE_GAP, RIGHT_GAP, LayoutMetrics, PhotoWatermark
from .drawing import get_text_bbox_with_tracking


def validate_layout_params(photo_count, config):
    """集中校验命令行排版参数，尽早给出清晰错误。"""
    if photo_count < 1:
        raise ValueError("至少需要 1 张照片。")

    if config.output_mode == "video" and photo_count > 3:
        raise ValueError("video 模式最多支持 3 张照片；更多照片请使用 adaptive 模式。")

    if config.output_mode not in {"video", "adaptive", "original"}:
        raise ValueError("output_mode 只支持 video、adaptive 或 original。")

    if config.color_mode not in {"preserve", "srgb"}:
        raise ValueError("color_mode 只支持 preserve 或 srgb。")
    if config.metadata_policy not in {"safe", "none"}:
        raise ValueError("metadata_policy 只支持 safe 或 none。")

    for name in ("date_tracking", "info_tracking", "location_tracking", "gps_location_timeout"):
        if not math.isfinite(getattr(config, name)):
            raise ValueError(f"{name} 必须是有限数值。")
    if config.gps_location_timeout <= 0:
        raise ValueError("gps_location_timeout 必须大于 0。")

    if config.photo_height <= 0 or config.photo_height >= CANVAS_H:
        raise ValueError("photo_height 必须大于 0 且小于画布高度。")

    if config.line_bottom_margin <= 0 or config.line_bottom_margin >= CANVAS_H:
        raise ValueError("line_bottom_margin 必须大于 0 且小于画布高度。")

    if config.line_left_offset < 0:
        raise ValueError("line_left_offset 不能小于 0。")

    if config.line_length <= 0:
        raise ValueError("line_length 必须大于 0。")

    if config.line_width <= 0:
        raise ValueError("line_width 必须大于 0。")

    if config.date_font_size <= 0:
        raise ValueError("date_font_size 必须大于 0。")

    if config.date_gap_below_line < 0:
        raise ValueError("date_gap_below_line 不能小于 0。")

    if config.date_tracking < 0:
        raise ValueError("date_tracking 不能小于 0。")

    if config.info_font_size <= 0:
        raise ValueError("info_font_size 必须大于 0。")

    if config.info_gap_x < 0:
        raise ValueError("info_gap_x 不能小于 0。")

    if config.location_gap_x < 0:
        raise ValueError("location_gap_x 不能小于 0。")

    if config.info_bottom_gap < 0:
        raise ValueError("info_bottom_gap 不能小于 0。")

    if config.info_tracking < 0:
        raise ValueError("info_tracking 不能小于 0。")

    if config.location_font_size <= 0:
        raise ValueError("location_font_size 必须大于 0。")

    if config.location_tracking < 0:
        raise ValueError("location_tracking 不能小于 0。")

    if config.info_location_gap < 0:
        raise ValueError("info_location_gap 不能小于 0。")

    if config.png_compression not in ("fast", "balanced", "small"):
        raise ValueError("png_compression 必须是 fast、balanced 或 small。")

    if not 1 <= config.jpeg_quality <= 100:
        raise ValueError("jpeg_quality 必须在 1 到 100 之间。")

    if not isinstance(config.show_signature, bool):
        raise ValueError("show_signature 必须是布尔值。")

    if config.signature_font_size <= 0:
        raise ValueError("signature_font_size 必须大于 0。")


def get_mark_width(signature, mark):
    """返回某张照片右侧水印组合的最大横向占用宽度。"""
    widths = []

    if mark.include_signature and signature is not None:
        widths.append(signature.size[0])

    if mark.logo is not None:
        widths.append(mark.logo.size[0])

    if not widths:
        return 0

    return max(widths)


def get_photo_marks(watermark_assets, photo_count):
    """统一水印计划；兼容只指定最右侧水印的旧调用。"""
    marks = watermark_assets.photo_marks
    if not marks:
        marks = [PhotoWatermark(None, None, False) for _ in range(photo_count)]
        marks[-1] = PhotoWatermark(
            watermark_assets.logo, watermark_assets.logo_name, True,
        )
    if len(marks) != photo_count:
        raise ValueError("水印计划和照片数量不一致。")
    return marks


def get_annotation_extents(items, config, watermark_assets):
    """计算照片左右两侧的实际横向占用，测量和绘制使用同一份文字图。"""
    left_extents = []
    for item in items:
        widths = [0]
        for image, gap in (
            (getattr(item, "settings_image", None), config.info_gap_x),
            (getattr(item, "location_image", None), config.location_gap_x),
        ):
            if image is not None:
                widths.append(gap + image.width)
        left_extents.append(max(widths))

    right_extents = []
    for mark in get_photo_marks(watermark_assets, len(items)):
        width = get_mark_width(watermark_assets.signature, mark)
        right_extents.append(RIGHT_GAP + width if width else 0)
    return left_extents, right_extents


def calculate_layout_metrics(items, config, watermark_assets):
    """统一计算边距、图间距及最终尺寸，不修改原图或调用者的配置。"""
    n = len(items)
    if not n:
        raise ValueError("没有可绘制的照片。")
    if config.output_mode == "original":
        return original_metrics(items, config, watermark_assets)
    sizes = [getattr(item, "source_size", None) or item.image.size for item in items]

    def widths_at_height(height):
        return [max(1, round(width * height / source_height)) for width, source_height in sizes]

    left, right = get_annotation_extents(items, config, watermark_assets)
    # a 按最右图两侧占用计算；同时覆盖每对相邻图的实际占用。
    collision_width = max(
        [right[-1] + left[-1]]
        + [right[i] + left[i + 1] for i in range(n - 1)]
    ) if n > 1 else 0
    height = config.photo_height
    available_height = CANVAS_H - config.line_bottom_margin

    if config.output_mode == "adaptive":
        photo_top = round((available_height - height) / 2)
        if height > available_height:
            raise ValueError("photo_height 太大，照片超出画布高度。请降低 photo_height。")
        if n > 1:
            side_margin = round(photo_top * 1.8)
            if side_margin < max(left[0], right[-1], collision_width + 1):
                raise ValueError(
                    "上留白的 1.8 倍不足以容纳水印和参数。"
                    "请降低 photo_height 以增加上留白，或减小字号 / 标记间距。"
                )
        else:
            side_margin = max(photo_top, left[0], right[-1], 1)
        photo_gap = side_margin
        widths = widths_at_height(height)
        canvas_w = sum(widths) + 2 * side_margin + (n - 1) * photo_gap
    else:
        height = min(height, available_height)
        initial_gap = (CANVAS_W - sum(widths_at_height(height))) // (n + 1)
        min_gap = max(1, left[0], right[-1])
        # 仅在初始间距小于 a 时触发缓冲；已有 a 到 1.5a 的间距保持原高度。
        if n > 1 and initial_gap < collision_width:
            min_gap = max(min_gap, (3 * collision_width + 1) // 2)
        max_photo_width = CANVAS_W - (n + 1) * min_gap
        # 宽度随高度单调增加：二分寻找能容纳照片和水印的最大整数高度。
        low, high = 0, min(height, available_height)
        while low < high:
            mid = (low + high + 1) // 2
            if sum(widths_at_height(mid)) <= max_photo_width:
                low = mid
            else:
                high = mid - 1
        height = low
        if height == 0:
            raise ValueError(
                "水印和参数占用过宽，video 画布无法容纳。"
                "请减小字号或标记间距，或改用 adaptive 模式。"
            )
        widths = widths_at_height(height)
        photo_gap, remainder = divmod(CANVAS_W - sum(widths), n + 1)
        # 将余数分配到照片宽度（每张最多 +1px），避免最后一侧累积取整误差。
        order = sorted(
            range(n),
            key=lambda i: sizes[i][0] * height / sizes[i][1] - widths[i],
            reverse=True,
        )
        for i in order[:remainder]:
            widths[i] += 1
        side_margin = photo_gap
        canvas_w = CANVAS_W
        photo_top = round((available_height - height) / 2)

    return LayoutMetrics(
        canvas_w=canvas_w,
        canvas_h=CANVAS_H,
        photo_gap=photo_gap,
        photo_top=photo_top,
        side_margin=side_margin,
        photo_height=height,
        photo_widths=tuple(widths),
    )


def original_metrics(items, cfg, assets):
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
