"""Prepare reusable fonts, logos and signature images."""

from io import BytesIO
import os
from pathlib import Path
import sys

from PIL import Image

from .asset_cache import prepared_asset
from .color import normalize_image
from .config import ASSETS_DIR, LOGO_HEIGHT, SIGNATURE_FILE, PhotoWatermark, WatermarkAssets
from .drawing import (
    load_font, load_signature_font, make_centered_text_mark_image,
    open_image_correct_orientation, resize_by_height, should_prefer_cjk_font,
)
from .utils import info


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
            return normalize_image(img, mode="RGBA")

    return open_image_correct_orientation(path, mode="RGBA")


def prepare_logo_image(path):
    """把任意原始尺寸的品牌 logo 统一缩放到固定高度并旋转。"""
    def prepare():
        with open_logo_image(path) as logo:
            return resize_by_height(logo, LOGO_HEIGHT).rotate(90, expand=True)
    if Path(path).suffix.lower() == ".svg":
        # SVGs may refer to other files; their bytes alone cannot identify all dependencies.
        return prepare()
    return prepared_asset(path, LOGO_HEIGHT, "logo", prepare)


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

        def prepare():
            with open_image_correct_orientation(signature_path, mode="RGBA") as image:
                return resize_by_height(image, LOGO_HEIGHT).rotate(90, expand=True)
        signature = prepared_asset(signature_path, LOGO_HEIGHT, "signature", prepare)
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

    logo = photo_marks[-1].logo if photo_marks else None
    logo_name = photo_marks[-1].logo_name if photo_marks else None

    return WatermarkAssets(
        signature=signature,
        logo=logo,
        logo_name=logo_name,
        photo_marks=photo_marks,
    )


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
