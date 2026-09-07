from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .utils import info, warn


HEIC_SUFFIXES = {".heic", ".heif", ".hif"}
RAW_SUFFIXES = {
    ".3fr",
    ".arw",
    ".cr2",
    ".cr3",
    ".crw",
    ".dng",
    ".erf",
    ".fff",
    ".iiq",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rw2",
    ".rwl",
    ".sr2",
    ".srf",
    ".srw",
    ".x3f",
}
HEIF_OPENER_REGISTERED = False

MONOSPACE_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Courier.ttc",
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/Library/Fonts/Courier New.ttf",
    str(Path.home() / "Library/Fonts/Courier New.ttf"),
    "C:/Windows/Fonts/cour.ttf",
    "C:/Windows/Fonts/courbd.ttf",
    "C:/Windows/Fonts/couri.ttf",
    "C:/Windows/Fonts/courbi.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Courier_New.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Courier_New_Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]

CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]

SIGNATURE_LATIN_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Courier.ttc",
    "/Library/Fonts/Courier New.ttf",
    str(Path.home() / "Library/Fonts/Courier New.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Narrow.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "C:/Windows/Fonts/courbd.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]

SIGNATURE_CJK_FONT_CANDIDATES = [
    ("/System/Library/Fonts/STHeiti Light.ttc", 1),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
]


def resize_by_height(img, target_h):
    """按指定高度等比例缩放图片。"""
    w, h = img.size

    if h <= 0:
        raise ValueError("图片高度异常，无法缩放。")

    target_w = round(w * target_h / h)

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    return img.resize((target_w, target_h), resample)


def register_heif_opener():
    """启用 HEIC/HEIF 读取支持。"""
    global HEIF_OPENER_REGISTERED

    if HEIF_OPENER_REGISTERED:
        return

    try:
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise RuntimeError(
            "读取 HEIC/HEIF 图片需要安装 pillow-heif。"
            '请运行 python3 -m pip install "pillow-heif>=1.0,<2.0"，'
            "或先把图片转换为 JPEG/PNG。"
        ) from exc

    register_heif_opener()
    HEIF_OPENER_REGISTERED = True


def open_raw_image(path, mode):
    """使用 rawpy 读取常见相机 RAW 文件并转换为 Pillow 图片。"""
    try:
        import rawpy
    except ImportError as exc:
        raise RuntimeError(
            "读取 RAW 图片需要安装 rawpy。"
            '请运行 python3 -m pip install "rawpy>=0.26,<1.0"，'
            "或先把 RAW 转换为 JPEG/TIFF。"
        ) from exc

    try:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    except Exception as exc:
        raise RuntimeError(f"读取 RAW 图片失败：{path}，原因：{exc}") from exc

    return Image.fromarray(rgb).convert(mode)


def open_image_correct_orientation(path, mode="RGB"):
    """打开图片，并根据 EXIF Orientation 自动旋正。"""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in RAW_SUFFIXES:
        return open_raw_image(path, mode)

    if suffix in HEIC_SUFFIXES:
        register_heif_opener()

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.convert(mode)


def load_font(font_size, font_path=None, label="日期字体", prefer_cjk=False):
    """加载字体；地点文字可优先寻找支持中文/多语言的字体。"""
    if font_path:
        font_path = Path(font_path)

        if not font_path.exists():
            raise FileNotFoundError(f"指定的字体文件不存在：{font_path}")

        info(f"{label}：{font_path}")
        return ImageFont.truetype(str(font_path), font_size)

    if prefer_cjk:
        font_candidates = CJK_FONT_CANDIDATES + MONOSPACE_FONT_CANDIDATES
    else:
        font_candidates = MONOSPACE_FONT_CANDIDATES

    for path in font_candidates:
        p = Path(path)

        if p.exists():
            try:
                info(f"{label}：{p}")
                return ImageFont.truetype(str(p), font_size)
            except Exception:
                pass

    raise FileNotFoundError(
        "没有找到可用字体。请使用 --font 或 --location-font 手动指定字体文件路径。"
    )


def load_font_candidate(candidate, font_size):
    if isinstance(candidate, (tuple, list)):
        path, index = candidate
    else:
        path = candidate
        index = 0

    p = Path(path)

    if not p.exists():
        return None, None

    try:
        return ImageFont.truetype(str(p), font_size, index=index), f"{p}#{index}"
    except Exception:
        return None, None


def should_prefer_cjk_font(text):
    """签名文字含非 ASCII 字符时，优先选择支持中文的字体。"""
    return any(ord(char) > 127 for char in str(text or ""))


def load_signature_font(font_size, font_path=None, text=""):
    """加载自定义签名文字字体，默认优先选择干净的细体。"""
    if font_path:
        return load_font(font_size, font_path, label="签名替代文字字体")

    if should_prefer_cjk_font(text):
        font_candidates = (
            SIGNATURE_CJK_FONT_CANDIDATES
            + SIGNATURE_LATIN_FONT_CANDIDATES
            + CJK_FONT_CANDIDATES
            + MONOSPACE_FONT_CANDIDATES
        )
    else:
        font_candidates = (
            SIGNATURE_LATIN_FONT_CANDIDATES
            + SIGNATURE_CJK_FONT_CANDIDATES
            + CJK_FONT_CANDIDATES
            + MONOSPACE_FONT_CANDIDATES
        )

    for path in font_candidates:
        font, label = load_font_candidate(path, font_size)

        if font is not None:
            family, style = font.getname()
            info(f"签名替代文字字体：{label} ({family} {style})")
            return font

    raise FileNotFoundError(
        "没有找到可用签名文字字体。请使用 --font 或 --location-font 手动指定字体文件路径。"
    )


def get_text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return draw.textsize(text, font=font)


def get_text_size_with_tracking(draw, text, font, tracking):
    if not text:
        return 0, 0

    total_w = 0
    max_h = 0

    for i, char in enumerate(text):
        char_w, char_h = get_text_size(draw, char, font)
        total_w += char_w
        max_h = max(max_h, char_h)

        if i != len(text) - 1:
            total_w += tracking

    return total_w, max_h


def draw_text_with_tracking(draw, position, text, font, fill, tracking=1):
    x, y = position

    for char in text:
        draw.text((x, y), char, fill=fill, font=font)
        char_w, _ = get_text_size(draw, char, font)
        x += char_w + tracking


def get_text_bbox_with_tracking(draw, text, font, tracking):
    if not text:
        return None

    current_x = 0
    min_x = None
    min_y = None
    max_x = None
    max_y = None

    for i, char in enumerate(text):
        try:
            bbox = draw.textbbox((current_x, 0), char, font=font)
        except Exception:
            char_w, char_h = get_text_size(draw, char, font)
            bbox = (current_x, 0, current_x + char_w, char_h)

        if min_x is None:
            min_x, min_y, max_x, max_y = bbox
        else:
            min_x = min(min_x, bbox[0])
            min_y = min(min_y, bbox[1])
            max_x = max(max_x, bbox[2])
            max_y = max(max_y, bbox[3])

        char_w, _ = get_text_size(draw, char, font)

        if i != len(text) - 1:
            current_x += char_w + tracking

    return min_x, min_y, max_x, max_y


def make_rotated_text_image(text, font, fill, tracking):
    """生成一张逆时针旋转 90 度后的透明文字图。"""
    if not text:
        return None

    temp_img = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = get_text_bbox_with_tracking(temp_draw, text, font, tracking)

    if not bbox:
        return None

    min_x, min_y, max_x, max_y = bbox
    text_w = max_x - min_x
    text_h = max_y - min_y
    padding = 8
    text_img = Image.new(
        "RGBA",
        (int(text_w + padding * 2), int(text_h + padding * 2)),
        (255, 255, 255, 0),
    )
    text_draw = ImageDraw.Draw(text_img)
    current_x = padding - min_x
    text_y = padding - min_y

    for i, char in enumerate(text):
        text_draw.text((current_x, text_y), char, fill=fill, font=font)
        char_w, _ = get_text_size(text_draw, char, font)

        if i != len(text) - 1:
            current_x += char_w + tracking

    rotated = text_img.rotate(90, expand=True)
    bbox = rotated.getbbox()

    if bbox:
        rotated = rotated.crop(bbox)

    return rotated


def make_centered_text_mark_image(text, font, fill, tracking, mark_height):
    """将文字居中绘制到固定高度透明画布中，再旋转成右侧签名标记。"""
    if not text:
        return None

    temp_img = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = get_text_bbox_with_tracking(temp_draw, text, font, tracking)

    if not bbox:
        return None

    min_x, min_y, max_x, max_y = bbox
    text_w = max(1, int(round(max_x - min_x)))
    text_h = max(1, int(round(max_y - min_y)))
    mark_height = max(1, int(mark_height))
    mark_img = Image.new("RGBA", (text_w, mark_height), (255, 255, 255, 0))
    mark_draw = ImageDraw.Draw(mark_img)
    current_x = -min_x
    text_y = round((mark_height - text_h) / 2 - min_y)

    for i, char in enumerate(text):
        mark_draw.text((current_x, text_y), char, fill=fill, font=font)
        char_w, _ = get_text_size(mark_draw, char, font)

        if i != len(text) - 1:
            current_x += char_w + tracking

    return mark_img.rotate(90, expand=True)


def draw_rotated_camera_settings(
    canvas,
    photo_x,
    photo_y,
    photo_h,
    settings_text,
    location_text,
    font,
    location_font,
    fill,
    tracking,
    location_tracking,
    location_gap,
    gap_x,
    location_gap_x,
    bottom_gap,
):
    """在每张照片的左下侧插入旋转后的拍摄参数和地点。"""
    if not settings_text and not location_text:
        return

    settings_img = make_rotated_text_image(settings_text, font, fill, tracking)
    location_img = make_rotated_text_image(
        location_text,
        location_font,
        fill,
        location_tracking,
    )

    current_bottom = photo_y + photo_h - bottom_gap

    if settings_img is not None:
        settings_w, settings_h = settings_img.size
        settings_x = photo_x - gap_x - settings_w
        settings_y = current_bottom - settings_h

        if settings_x < 0:
            warn(
                f"参数文字 '{settings_text}' 可能超出画布左侧。"
                "请减小 info_font_size / info_gap_x，或降低 photo_height 以增加 photo_gap。"
            )

        canvas.paste(settings_img, (int(settings_x), int(settings_y)), settings_img)
        current_bottom = settings_y - location_gap

    if location_img is not None:
        location_w, location_h = location_img.size
        location_x = photo_x - location_gap_x - location_w
        location_y = current_bottom - location_h

        if location_x < 0:
            warn(
                f"地点文字 '{location_text}' 可能超出画布左侧。"
                "请减小 location_font_size / location_gap_x，或降低 photo_height 以增加 photo_gap。"
            )

        canvas.paste(location_img, (int(location_x), int(location_y)), location_img)


def save_best_quality_jpeg(img, output_path, quality=95):
    img.save(
        output_path,
        format="JPEG",
        quality=quality,
        subsampling=0,
        optimize=False,
        progressive=False,
    )


def save_best_quality_image(img, output_path, jpeg_quality=95):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".png":
        img.save(output_path, format="PNG", compress_level=0)
    else:
        save_best_quality_jpeg(img, output_path, quality=jpeg_quality)
