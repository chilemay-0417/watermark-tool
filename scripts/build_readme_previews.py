"""从 samples 的展示样张生成 README 预览，不修改样张。"""
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watermark_tool.color import SRGB_ICC  # noqa: E402
from watermark_tool.drawing import open_image_correct_orientation  # noqa: E402

PREVIEWS = (
    ("phone1_watermark.jpg", 1920),
    ("vertical1_vertical2_watermark.jpg", 1920),
    ("phone2_vertical1_vertical2_watermark.jpg", 1920),
    ("horizontal1_watermark.jpg", 1600),
    ("phone2_watermark.jpg", 1080),
    ("horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg", 3840),
)


def main():
    output_dir = ROOT / "docs" / "previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    original_bytes = preview_bytes = 0
    for name, max_width in PREVIEWS:
        source = ROOT / "samples" / name
        output = output_dir / name
        with open_image_correct_orientation(source) as image:
            preview = image
            if preview.width > max_width:
                height = max(1, round(preview.height * max_width / preview.width))
                preview = preview.resize((max_width, height), Image.Resampling.LANCZOS)
            preview.save(output, quality=90, subsampling=0, optimize=True,
                         progressive=True, icc_profile=SRGB_ICC)
            print(f"{name}: {preview.width} x {preview.height}, {output.stat().st_size:,} bytes")
        original_bytes += source.stat().st_size
        preview_bytes += output.stat().st_size
    print(f"Total: {original_bytes:,} -> {preview_bytes:,} bytes "
          f"({1 - preview_bytes / original_bytes:.1%} smaller)")


if __name__ == "__main__":
    main()
