"""Draw photo annotations identically for sRGB and native-color output."""

from .config import LOGO_SIGNATURE_GAP, RIGHT_GAP, PhotoPlacement
from .drawing import (
    draw_rotated_camera_settings, draw_text_with_tracking, get_text_bbox_with_tracking,
)
from .layout import get_mark_width, get_photo_marks
from .utils import warn


def draw_photo_item(canvas, draw, item, idx, current_x, metrics, config, *, photo_size=None):
    """绘制照片及标注；传 photo_size 时跳过照片粘贴，只按尺寸定位。"""
    photo_w, photo_h = photo_size if photo_size is not None else item.image.size
    if photo_size is None:
        canvas.paste(item.image, (current_x, metrics.photo_top))

    placement = PhotoPlacement(
        x=current_x,
        y=metrics.photo_top,
        w=photo_w,
        h=photo_h,
    )

    draw_rotated_camera_settings(
        canvas=canvas,
        photo_x=current_x,
        photo_y=metrics.photo_top,
        photo_h=photo_h,
        settings_text=item.metadata.settings,
        location_text=item.metadata.location,
        font=config.info_font,
        location_font=config.location_font,
        fill=config.info_color,
        tracking=config.info_tracking,
        location_tracking=config.location_tracking,
        location_gap=config.info_location_gap,
        gap_x=config.info_gap_x,
        location_gap_x=config.location_gap_x,
        bottom_gap=config.info_bottom_gap,
        prepared_images=(item.settings_image, item.location_image),
    )

    line_y = metrics.canvas_h - config.line_bottom_margin
    line_start_x = current_x + config.line_left_offset
    line_end_x = line_start_x + config.line_length

    if line_y < 0 or line_y > metrics.canvas_h:
        raise ValueError("横线位置超出画布。请检查 line_bottom_margin。")

    if line_start_x > metrics.canvas_w:
        raise ValueError("横线起点超出画布右侧。请减小 line_left_offset 或降低 photo_height。")

    if line_end_x > current_x + photo_w:
        warn(
            f"第 {idx + 1} 张照片的横线超出照片右边界，"
            "但仍会按指定 line_length 绘制。"
        )

    draw.line(
        (line_start_x, line_y, line_end_x, line_y),
        fill=config.line_color,
        width=config.line_width,
    )

    date_text = item.metadata.date
    date_bbox = get_text_bbox_with_tracking(
        draw,
        date_text,
        config.date_font,
        config.date_tracking,
    ) or (0, 0, 0, 0)
    date_x = current_x + config.line_left_offset
    date_y = line_y + config.date_gap_below_line

    if date_x + date_bbox[2] > metrics.canvas_w:
        warn(
            f"第 {idx + 1} 张照片的日期文字可能超出画布右侧，"
            "但仍会按指定位置绘制。"
        )

    if date_y + date_bbox[3] > metrics.canvas_h:
        raise ValueError(
            "日期文字会超出画布底部。"
            "请减小 date_font_size、date_gap_below_line，或增大 line_bottom_margin。"
        )

    draw_text_with_tracking(
        draw,
        (date_x, date_y),
        date_text,
        font=config.date_font,
        fill=config.date_color,
        tracking=config.date_tracking,
    )

    return placement


def draw_single_photo_watermark(
    canvas,
    watermark_assets,
    mark,
    placement,
    next_placement,
    metrics,
    config,
):
    """在单张照片右下侧绘制品牌 logo，并按需在上方绘制签名。"""
    has_signature_mark = mark.include_signature and watermark_assets.signature is not None

    if mark.logo is None and not has_signature_mark:
        return

    photo_right = placement.x + placement.w
    photo_bottom = placement.y + placement.h
    mark_width = get_mark_width(watermark_assets.signature, mark)

    mark_x = photo_right + RIGHT_GAP
    bottom_y = photo_bottom
    logo_y = None
    sig_y = None

    if mark.logo is not None:
        _, logo_h = mark.logo.size
        logo_y = bottom_y - logo_h
        bottom_y = logo_y

    if has_signature_mark:
        _, sig_h = watermark_assets.signature.size

        if mark.logo is not None:
            sig_y = bottom_y - LOGO_SIGNATURE_GAP - sig_h
        else:
            sig_y = bottom_y - sig_h

    right_boundary = next_placement.x if next_placement is not None else metrics.canvas_w

    if mark_x + mark_width > right_boundary:
        raise ValueError(
            "logo / 签名会超出可用空间。"
            "请减小 photo_height、减小 RIGHT_GAP / LOGO_HEIGHT，或改用 adaptive 输出模式。"
        )

    top_y = min(y for y in (sig_y, logo_y) if y is not None)

    if top_y < 0:
        raise ValueError("logo / 签名超出画布顶部。请缩短签名文字或减小标记尺寸。")
    if top_y < metrics.photo_top:
        if mark.logo is not None and mark.include_signature:
            warn("签名和 logo 的组合高度过高，可能超过照片顶部。")
        elif has_signature_mark:
            warn("签名高度过高，可能超过照片顶部。")
        else:
            warn("logo 高度过高，可能超过照片顶部。")

    if sig_y is not None and watermark_assets.signature is not None:
        canvas.paste(watermark_assets.signature, (mark_x, sig_y), watermark_assets.signature)

    if mark.logo is not None and logo_y is not None:
        canvas.paste(mark.logo, (mark_x, logo_y), mark.logo)


def draw_watermark_assets(canvas, watermark_assets, photo_placements, metrics, config):
    """按照片水印计划绘制签名和品牌 logo。"""
    photo_marks = get_photo_marks(watermark_assets, len(photo_placements))

    for idx, (placement, mark) in enumerate(zip(photo_placements, photo_marks, strict=True)):
        next_placement = (
            photo_placements[idx + 1]
            if idx + 1 < len(photo_placements)
            else None
        )
        draw_single_photo_watermark(
            canvas=canvas,
            watermark_assets=watermark_assets,
            mark=mark,
            placement=placement,
            next_placement=next_placement,
            metrics=metrics,
            config=config,
        )
