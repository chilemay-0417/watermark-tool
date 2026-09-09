import json
import math
import os
import re
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from .config import (
    ASSETS_DIR,
    BRAND_RULES_FILE,
    CANVAS_H,
    CANVAS_W,
    LOGO_HEIGHT,
    LOGO_SIGNATURE_GAP,
    LayoutConfig,
    LayoutMetrics,
    PhotoItem,
    PhotoPlacement,
    PhotoWatermark,
    RIGHT_GAP,
    SIGNATURE_FILE,
    WatermarkAssets,
)
from .drawing import (
    draw_rotated_camera_settings,
    draw_text_with_tracking,
    get_oriented_image_size,
    get_text_bbox_with_tracking,
    load_font,
    load_signature_font,
    make_centered_text_mark_image,
    make_rotated_text_image,
    open_image_correct_orientation,
    resize_by_height,
    save_best_quality_image,
    should_prefer_cjk_font,
)
from .exif_gps import read_photo_metadata
from .utils import info, warn


LOGO_FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".svg")
WORD_CHAR_PATTERN = re.compile(r"[a-z0-9]")


def get_brand_rules_path(base_dir):
    """返回品牌匹配规则文件路径，允许用环境变量覆盖。"""
    override = os.environ.get("WATERMARK_BRANDS_FILE")

    if override:
        return Path(override).expanduser()

    return Path(base_dir) / BRAND_RULES_FILE


def load_brand_rules(base_dir):
    """读取外部品牌 logo 匹配规则。"""
    rules_path = get_brand_rules_path(base_dir)

    if not rules_path.exists():
        warn(f"找不到品牌规则文件：{rules_path}。将不添加品牌 logo，只放签名。")
        return []

    try:
        with rules_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"品牌规则文件不是合法 JSON：{rules_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ValueError(f"品牌规则文件顶层必须是对象：{rules_path}")

    brands = data.get("brands")

    if not isinstance(brands, list):
        raise ValueError(f"品牌规则文件缺少 brands 列表：{rules_path}")

    normalized_rules = []

    for idx, brand in enumerate(brands, start=1):
        if not isinstance(brand, dict):
            raise ValueError(f"品牌规则第 {idx} 项必须是对象：{rules_path}")

        logo_file = brand.get("logo")
        keywords = brand.get("keywords", [])
        display_name = brand.get("display_name") or brand.get("name") or logo_file

        if not isinstance(logo_file, str) or not logo_file.strip():
            raise ValueError(f"品牌规则第 {idx} 项缺少 logo 文件名：{rules_path}")

        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"品牌规则第 {idx} 项缺少 keywords 列表：{rules_path}")

        normalized_keywords = []

        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError(f"品牌规则第 {idx} 项包含无效 keyword：{rules_path}")

            normalized_keywords.append(keyword.strip().lower())

        normalized_rules.append(
            {
                "display_name": str(display_name),
                "logo": logo_file,
                "keywords": normalized_keywords,
            }
        )

    return normalized_rules


def resolve_logo_path(base_dir, logo_file):
    """根据规则里的文件名寻找 logo，兼容旧的 *_400.jpg 命名。"""
    base_dir = Path(base_dir)
    logo_file = Path(logo_file)
    exact_path = base_dir / logo_file

    if exact_path.exists():
        return exact_path

    candidates = []
    stem = logo_file.stem

    if stem.endswith("_400"):
        candidates.extend(
            base_dir / f"{stem[:-4]}{suffix}"
            for suffix in LOGO_FILE_SUFFIXES
        )

    candidates.extend(
        base_dir / f"{stem}{suffix}"
        for suffix in LOGO_FILE_SUFFIXES
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def normalize_brand_match_text(value):
    """归一化相机厂商 / 型号文本，用于更稳定的品牌匹配。"""
    return " ".join(str(value or "").lower().split())


def keyword_matches_text(keyword, text):
    """判断关键词是否命中，短字母数字关键词必须满足词边界。"""
    keyword = normalize_brand_match_text(keyword)
    text = normalize_brand_match_text(text)

    if not keyword or not text:
        return False

    if not WORD_CHAR_PATTERN.search(keyword):
        return keyword in text

    if keyword.isalnum():
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None

    return keyword in text


def keyword_specificity(keyword):
    return len(re.sub(r"[^a-z0-9]", "", normalize_brand_match_text(keyword)))


def is_generic_brand_keyword(rule, keyword):
    """品牌名关键词在 model 中出现时不应压过更具体的机型关键词。"""
    keyword = normalize_brand_match_text(keyword)
    display_name = normalize_brand_match_text(rule.get("display_name", ""))
    logo_stem = normalize_brand_match_text(Path(rule.get("logo", "")).stem)
    generic_text = f"{display_name} {logo_stem}"
    generic_tokens = set(re.findall(r"[a-z0-9]+", generic_text))

    return keyword in generic_tokens or keyword == display_name or keyword == logo_stem


def is_specific_model_keyword(rule, keyword):
    """带型号前缀、系列短语的关键词比单纯品牌名更适合覆盖 EXIF Make。"""
    keyword = normalize_brand_match_text(keyword)

    if is_generic_brand_keyword(rule, keyword):
        return False

    return "-" in keyword or " " in keyword


def score_brand_rule_for_camera(rule, make, model):
    """给品牌规则打分，优先选择明确品牌或更具体的机型规则。"""
    best_score = 0

    for keyword in rule["keywords"]:
        specificity = keyword_specificity(keyword)

        if keyword_matches_text(keyword, make):
            best_score = max(best_score, 600 + specificity)

        if keyword_matches_text(keyword, model):
            if is_specific_model_keyword(rule, keyword):
                score = 700 + specificity
            elif is_generic_brand_keyword(rule, keyword):
                score = 250 + specificity
            else:
                score = 300 + specificity

            best_score = max(best_score, score)

    return best_score


def find_brand_rule_by_camera(make, model, base_dir, rules=None):
    """根据 EXIF 里的 Make / Model 选择最可信的品牌规则。"""
    best_rule = None
    best_score = 0

    for rule in load_brand_rules(base_dir) if rules is None else rules:
        score = score_brand_rule_for_camera(rule, make, model)

        if score > best_score:
            best_rule = rule
            best_score = score

    return best_rule


def find_logo_path_by_camera(make, model, base_dir, rules=None):
    """根据外部品牌规则选择 logo，不输出未知品牌警告。"""
    rule = find_brand_rule_by_camera(make, model, base_dir, rules=rules)

    if rule is None:
        return None

    return resolve_logo_path(base_dir, rule["logo"])


def choose_logo_by_camera(make, model, base_dir, warn_unknown=True, rules=None):
    """根据 EXIF 里的相机品牌 Make 和型号 Model 选择 logo。"""
    logo_path = find_logo_path_by_camera(make, model, base_dir, rules=rules)

    if logo_path is not None:
        return logo_path

    if not warn_unknown:
        return None

    warn(
        f"无法找到可用品牌 logo：Make={make or '空'}，Model={model or '空'}。"
        "将不添加 logo，只放签名。"
    )
    return None


def normalize_camera_device_key(make, model):
    """把 EXIF Make / Model 归一成用于判断同一拍摄设备的 key。"""
    make = " ".join((make or "").lower().split())
    model = " ".join((model or "").lower().split())

    if not make and not model:
        return ""

    return f"{make}|{model}"


def select_logo_paths_for_items(items, base_dir):
    """
    为每张照片生成品牌 logo 和签名计划。

    - 单张照片：在该照片右下侧放品牌 logo，并在其上方放签名。
    - 多张照片设备完全一致：只在最右侧照片右下侧放品牌 logo 和签名。
    - 多张照片设备不一致：每张可识别照片都放自己的品牌 logo，只有最右侧有签名。
    """
    if not items:
        return []

    rules = load_brand_rules(base_dir)
    logo_paths = []
    camera_labels = []
    device_keys = []
    unknown_logo_count = 0

    for item in items:
        metadata = item.metadata
        make = metadata.make or ""
        model = metadata.model or ""
        logo_path = choose_logo_by_camera(
            make, model, base_dir, warn_unknown=False, rules=rules,
        )

        camera_labels.append(f"{make or '未识别'} {model or ''}".strip())
        device_keys.append(normalize_camera_device_key(make, model))
        logo_paths.append(logo_path)

        if logo_path is None:
            unknown_logo_count += 1

    info(f"检测到相机：{'；'.join(camera_labels)}")

    rightmost_idx = len(items) - 1
    all_same_device = all(device_keys) and len(set(device_keys)) == 1

    if len(items) == 1 or all_same_device:
        marks = [(None, False) for _ in items]
        marks[rightmost_idx] = (logo_paths[rightmost_idx], True)

        if logo_paths[rightmost_idx] is None:
            warn("无法从所选照片找到可用品牌 logo。将不添加品牌 logo，只放签名。")
        elif len(items) > 1:
            info("所选照片拍摄设备一致：只在最右侧照片添加品牌 logo 和签名。")

        return marks

    marks = [
        (logo_path, idx == rightmost_idx)
        for idx, logo_path in enumerate(logo_paths)
    ]

    if unknown_logo_count:
        warn(
            f"有 {unknown_logo_count} 张照片无法找到可用品牌 logo。"
            "这些照片将不添加品牌 logo。"
        )

    info("所选照片拍摄设备不一致：分别添加可识别的品牌 logo，签名只添加在最右侧照片。")
    return marks


def select_logo_path_for_items(items, base_dir):
    """兼容旧调用：返回最右侧照片水印计划中的品牌 logo。"""
    for logo_path, include_signature in reversed(select_logo_paths_for_items(items, base_dir)):
        if include_signature:
            return logo_path

    return None


def validate_layout_params(photo_count, config):
    """集中校验命令行排版参数，尽早给出清晰错误。"""
    if photo_count < 1:
        raise ValueError("至少需要 1 张照片。")

    if config.output_mode == "video" and photo_count > 3:
        raise ValueError("video 模式最多支持 3 张照片；更多照片请使用 adaptive 模式。")

    if config.output_mode not in {"video", "adaptive"}:
        raise ValueError("output_mode 只支持 video 或 adaptive。")

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

    if not 1 <= config.jpeg_quality <= 100:
        raise ValueError("jpeg_quality 必须在 1 到 100 之间。")

    if not isinstance(config.show_signature, bool):
        raise ValueError("show_signature 必须是布尔值。")

    if config.signature_font_size <= 0:
        raise ValueError("signature_font_size 必须大于 0。")


def get_asset_base_dir():
    """获取 logo / 签名默认目录。"""
    override = os.environ.get("WATERMARK_ASSETS_DIR")

    if override:
        return Path(override).expanduser()

    installed_assets_dir = Path(sys.prefix) / "share" / "watermark-tool" / "assets"

    for candidate in (ASSETS_DIR, installed_assets_dir):
        if candidate.exists():
            return candidate

    return ASSETS_DIR


def load_photo_items(photo_paths, config, *, defer_pixels=False):
    """准备尺寸、元信息和文字，可延迟解码以免长图合成同时保留所有原图。"""
    items = []

    for path in photo_paths:
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"找不到照片文件：{path}")

        metadata = read_photo_metadata(
            path,
            include_gps_location=config.include_gps_location,
            gps_location_language=config.gps_location_language,
            gps_location_timeout=config.gps_location_timeout,
        )
        image = None if defer_pixels else open_image_correct_orientation(path, mode="RGB")
        source_size = get_oriented_image_size(path) if image is None else image.size
        items.append(PhotoItem(
            path=path,
            image=image,
            source_size=source_size,
            metadata=metadata,
            settings_image=make_rotated_text_image(
                metadata.settings, config.info_font, config.info_color, config.info_tracking,
            ),
            location_image=make_rotated_text_image(
                metadata.location, config.location_font,
                config.info_color, config.location_tracking,
            ),
        ))

    return items


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


def open_logo_image(path):
    """打开品牌 logo，支持常见位图和 SVG。"""
    path = Path(path)

    if path.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError as exc:
            raise RuntimeError(
                f"SVG logo 需要安装 CairoSVG 才能读取：{path}。"
                '请运行 python3 -m pip install "CairoSVG>=2.7,<3.0"，'
                "或把该 logo 导出为 PNG。"
            ) from exc

        png_bytes = cairosvg.svg2png(
            url=str(path),
            output_height=LOGO_HEIGHT * 4,
        )

        with Image.open(BytesIO(png_bytes)) as img:
            return img.convert("RGBA")

    return open_image_correct_orientation(path, mode="RGBA")


def prepare_logo_image(path):
    """把任意原始尺寸的品牌 logo 统一缩放到固定高度并旋转。"""
    logo = open_logo_image(path)
    return resize_by_height(logo, LOGO_HEIGHT).rotate(90, expand=True)


def get_signature_font_path(config, signature_text):
    """英文签名跟随日期字体；中文签名优先使用地点/中文字体。"""
    if config.signature_font_path:
        return config.signature_font_path

    if should_prefer_cjk_font(signature_text):
        return config.location_font_path or config.font_path

    return config.font_path


def prepare_signature_mark(base_dir, config):
    """准备右侧签名图片，或关闭签名时的替代文字。"""
    if config.show_signature:
        signature_path = base_dir / SIGNATURE_FILE

        if not signature_path.exists():
            raise FileNotFoundError(f"找不到签名文件：{signature_path}")

        signature = open_image_correct_orientation(signature_path, mode="RGBA")
        signature = resize_by_height(signature, LOGO_HEIGHT).rotate(90, expand=True)
        info(f"使用签名：{signature_path.name}")
        return signature

    signature_text = str(config.signature_text or "").strip()

    if not signature_text:
        info("不显示签名")
        return None

    if config.signature_font is None:
        signature_font_path = get_signature_font_path(config, signature_text)
        config.signature_font = load_signature_font(
            config.signature_font_size,
            signature_font_path,
            text=signature_text,
        )

    signature = make_centered_text_mark_image(
        signature_text,
        config.signature_font,
        config.info_color,
        config.info_tracking,
        LOGO_HEIGHT,
    )

    if signature is None:
        info("不显示签名")
        return None

    info(f"使用签名替代文字：{signature_text}")
    return signature


def load_watermark_assets(base_dir, config, logo_path=None, logo_plan=None):
    """加载签名和可选品牌 logo。"""
    signature = prepare_signature_mark(base_dir, config)

    if logo_plan is None:
        logo_plan = [(logo_path, True)]

    logo_cache = {}
    photo_marks = []

    for planned_logo_path, include_signature in logo_plan:
        logo = None
        logo_name = None

        if planned_logo_path is not None:
            if not planned_logo_path.exists():
                raise FileNotFoundError(
                    f"找不到 logo 文件：{planned_logo_path}。请确认 assets/ 中存在该文件。"
                )

            if planned_logo_path not in logo_cache:
                info(f"使用 logo：{planned_logo_path.name}")
                logo_cache[planned_logo_path] = prepare_logo_image(planned_logo_path)

            logo = logo_cache[planned_logo_path]
            logo_name = planned_logo_path.name

        photo_marks.append(
            PhotoWatermark(
                logo=logo,
                logo_name=logo_name,
                include_signature=include_signature and signature is not None,
            )
        )

    if not logo_cache and signature is not None:
        info("使用 logo：无，仅使用签名")
    elif not logo_cache:
        info("使用 logo：无")

    mark_widths = [get_mark_width(signature, mark) for mark in photo_marks]
    right_mark_width = mark_widths[-1] if mark_widths else 0
    max_internal_mark_width = max(mark_widths[:-1], default=0)
    logo = photo_marks[-1].logo if photo_marks else None
    logo_name = photo_marks[-1].logo_name if photo_marks else None

    return WatermarkAssets(
        signature=signature,
        logo=logo,
        logo_name=logo_name,
        max_width=max(mark_widths, default=0),
        reserved_right_width=RIGHT_GAP + right_mark_width if right_mark_width else 0,
        internal_reserved_width=(
            RIGHT_GAP + max_internal_mark_width if max_internal_mark_width else 0
        ),
        photo_marks=photo_marks,
    )


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


def draw_photo_item(canvas, draw, item, idx, current_x, metrics, config):
    """把一张照片及其线条、日期、参数文字绘制到画布上。"""
    photo_w = item.image.size[0]
    canvas.paste(item.image, (current_x, metrics.photo_top))

    placement = PhotoPlacement(
        x=current_x,
        y=metrics.photo_top,
        w=photo_w,
        h=metrics.photo_height,
    )

    draw_rotated_camera_settings(
        canvas=canvas,
        photo_x=current_x,
        photo_y=metrics.photo_top,
        photo_h=metrics.photo_height,
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

    for idx, item in enumerate(items, start=1):
        settings_text = item.metadata.settings or "未读取到"
        location_text = item.metadata.location or "未读取到"
        info(f"照片 {idx} 日期：{item.metadata.date}")
        info(f"照片 {idx} 参数：{settings_text}")
        info(f"照片 {idx} 地点：{location_text}")


def prepare_fonts(config):
    config.date_font = load_font(config.date_font_size, config.font_path, label="日期字体")
    config.info_font = load_font(config.info_font_size, config.font_path, label="参数字体")
    config.location_font = load_font(
        config.location_font_size,
        config.location_font_path,
        label="地点字体",
    )

    if not config.show_signature and config.signature_text:
        signature_font_path = get_signature_font_path(config, config.signature_text)
        config.signature_font = load_signature_font(
            config.signature_font_size,
            signature_font_path,
            text=config.signature_text,
        )


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

    base_dir = get_asset_base_dir()
    items = load_photo_items(photo_paths=photo_paths, config=config, defer_pixels=True)

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

    if output_path.suffix.lower() != ".png" and metrics.canvas_w > 65500:
        raise ValueError(
            f"合成宽度为 {metrics.canvas_w}px，超过 JPEG 编码器的 65500px 限制。"
            "请用 -o 指定 .png 输出；adaptive 本身不限制宽度。"
        )

    canvas = Image.new("RGB", (metrics.canvas_w, metrics.canvas_h), config.background_color)
    draw = ImageDraw.Draw(canvas)
    current_x = metrics.side_margin
    photo_placements = []

    if metrics.photo_height < config.photo_height:
        info(f"video 自动降低照片高度：{config.photo_height} → {metrics.photo_height}px。")

    for idx, item in enumerate(items):
        with open_image_correct_orientation(item.path, mode="RGB") as original:
            item.image = original.resize(
                (metrics.photo_widths[idx], metrics.photo_height), Image.Resampling.LANCZOS,
            )
        placement = draw_photo_item(
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

    draw_watermark_assets(
        canvas=canvas,
        watermark_assets=watermark_assets,
        photo_placements=photo_placements,
        metrics=metrics,
        config=config,
    )

    save_best_quality_image(canvas, output_path, jpeg_quality=config.jpeg_quality)
    print_export_summary(output_path=output_path, items=items, metrics=metrics, config=config)
