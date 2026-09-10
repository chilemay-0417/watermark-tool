from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .color import (
    SRGB_ICC,
    normalize_image,
    open_heif_srgb,
)
from .config import PNG_COMPRESSION_LEVELS
from .utils import atomic_output_path, info, warn


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

    target_w = max(1, round(w * target_h / h))
    return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


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


def reject_tiff_input(path, image_format=None):
    """Reject TIFF by filename or detected format, including renamed TIFF files."""
    if Path(path).suffix.lower() in {".tif", ".tiff"} or image_format == "TIFF":
        raise ValueError("不再支持 TIFF 输入；请先在编辑软件中导出 PNG 或 JPEG。")


def open_image_correct_orientation(path, mode="RGB", background=(255, 255, 255)):
    """打开并旋正图片，转换为 sRGB；透明照片与指定背景合成。"""
    path = Path(path)
    suffix = path.suffix.lower()
    reject_tiff_input(path)

    if suffix in RAW_SUFFIXES:
        raise ValueError("不再支持 RAW 输入；请先在编辑软件中导出 PNG 或 JPEG。")

    if suffix in HEIC_SUFFIXES:
        register_heif_opener()
        return open_heif_srgb(path, mode, background)

    with Image.open(path) as header:
        reject_tiff_input(path, header.format)
        use_native = header.format == "PNG" and header.mode not in ("CMYK", "LAB")
    if use_native:
        from .raster import read_raster, raster_to_srgb
        return raster_to_srgb(read_raster(path), mode, background)
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return normalize_image(img, mode, background)


def read_image_header(path):
    """Read oriented dimensions and a metadata snapshot without decoding pixels."""
    from .metadata import read_source_metadata

    path = Path(path)
    reject_tiff_input(path)
    if path.suffix.lower() in RAW_SUFFIXES:
        raise ValueError("不再支持 RAW 输入；请先导出 PNG 或 JPEG。")
    if path.suffix.lower() in HEIC_SUFFIXES:
        register_heif_opener()
    with Image.open(path) as img:
        reject_tiff_input(path, img.format)
        width, height = img.size
        source = read_source_metadata(path, img)
        if source[0].get(274) in (5, 6, 7, 8):
            width, height = height, width
        return (width, height), source


def get_oriented_image_size(path):
    """只读取旋正后尺寸；尺寸和元数据共享同一读取入口。"""
    return read_image_header(path)[0]


@lru_cache(maxsize=64)
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
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


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
        bbox = draw.textbbox((current_x, 0), char, font=font)

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
    draw_text_with_tracking(
        text_draw, (padding - min_x, padding - min_y), text, font, fill, tracking,
    )

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
    text_y = round((mark_height - text_h) / 2 - min_y)
    draw_text_with_tracking(mark_draw, (-min_x, text_y), text, font, fill, tracking)

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
    prepared_images=None,
):
    """在每张照片的左下侧插入旋转后的拍摄参数和地点。"""
    if not settings_text and not location_text:
        return

    if prepared_images is None:
        settings_img = make_rotated_text_image(settings_text, font, fill, tracking)
        location_img = make_rotated_text_image(
            location_text, location_font, fill, location_tracking,
        )
    else:
        settings_img, location_img = prepared_images

    current_bottom = photo_y + photo_h - bottom_gap
    images = [img for img in (settings_img, location_img) if img is not None]
    text_height = sum(img.height for img in images)
    if len(images) == 2:
        text_height += location_gap
    if current_bottom - text_height < 0 or current_bottom > canvas.height:
        raise ValueError(
            "参数 / 地点文字超出画布上下边界。"
            "请减小 info_font_size、location_font_size、info_location_gap 或 info_bottom_gap。"
        )

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


def save_best_quality_jpeg(img, output_path, quality=100, *, metadata=None):
    prepared = img if img.mode == "RGB" and img.info == {"icc_profile": SRGB_ICC} else (
        normalize_image(img)
    )
    prepared.save(
        output_path,
        format="JPEG",
        quality=quality,
        subsampling=0,
        optimize=False,
        progressive=False,
        icc_profile=SRGB_ICC,
        **(metadata or {}),
    )


def save_best_quality_image(
    img, output_path, jpeg_quality=100, *, metadata=None, png_compression="balanced",
):
    """先完整编码到同目录临时文件，成功后原子替换，失败不破坏已有输出。"""
    output_path = Path(output_path)
    with atomic_output_path(output_path) as temp_path:
        if output_path.suffix.lower() == ".png":
            prepared = img if img.mode == "RGB" and img.info == {"icc_profile": SRGB_ICC} else (
                normalize_image(img)
            )
            from PIL.PngImagePlugin import PngInfo
            options = dict(metadata or {})
            xmp = options.pop("xmp", None)
            if xmp:
                chunks = PngInfo()
                chunks.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8"))
                options["pnginfo"] = chunks
            prepared.save(
                temp_path, format="PNG", compress_level=PNG_COMPRESSION_LEVELS[png_compression],
                icc_profile=SRGB_ICC, **options,
            )
        else:
            save_best_quality_jpeg(img, temp_path, quality=jpeg_quality,
                                   **({"metadata": metadata} if metadata is not None else {}))
