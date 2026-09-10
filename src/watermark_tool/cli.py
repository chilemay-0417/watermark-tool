import argparse
import sys
from pathlib import Path

from .config import LayoutConfig
from .renderer import make_canvas
from .utils import configure_logging, error, info, progress


def parse_bool(value):
    """解析命令行里的布尔值。"""
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True

    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise argparse.ArgumentTypeError(
        "布尔参数只支持 true/false、yes/no、1/0、on/off。"
    )


def make_unique_output_path(path):
    """如果默认输出路径已存在，自动追加序号避免覆盖。"""
    path = Path(path)

    if not path.exists():
        return path

    for idx in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")

        if not candidate.exists():
            return candidate

    raise FileExistsError(f"无法生成不重名的输出文件：{path}")


def make_default_output_path(photo_paths):
    """根据输入照片生成统一的默认输出文件名。"""
    paths = [Path(path) for path in photo_paths]

    if not paths:
        raise ValueError("没有收到照片文件。")

    output_dir = paths[0].parent
    joined_stem = "_".join(path.stem for path in paths)
    if len(joined_stem.encode("utf-8")) > 180:
        short_stem = paths[0].stem.encode("utf-8")[:120].decode("utf-8", errors="ignore")
        joined_stem = f"{short_stem}_and_{len(paths) - 1}_photos" if len(paths) > 1 else short_stem
    return make_unique_output_path(output_dir / f"{joined_stem}_watermark.jpg")


def make_output_path_from_original(photo_path):
    """兼容旧调用：根据单张原图生成默认输出文件名。"""
    return make_default_output_path([photo_path])


def build_parser(defaults=None):
    defaults = defaults or LayoutConfig()
    parser = argparse.ArgumentParser(
        prog="watermark-tool",
        description=(
            "将照片排版到画布，并自动添加日期、拍摄参数、"
            "相机品牌 logo 与签名。video 支持 1-3 张，输出 3840x2160；"
            "adaptive 不限制张数或画布宽度。"
        )
    )

    parser.add_argument(
        "photos",
        nargs="+",
        help="输入照片路径。video 最多 3 张；adaptive 可合成任意多张。",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="逐张导出所有输入照片，在同一进程中复用水印和地点缓存；不能与 -o 同用。",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "输出文件名。不指定时，默认使用输入照片名加 _watermark，"
            "多张照片会拼接文件名；.png 支持无损和 16 位 SDR。"
        ),
    )
    parser.add_argument(
        "--height",
        type=int,
        default=defaults.photo_height,
        help=f"照片高度，默认 {defaults.photo_height}px；video 空间不足时自动降低。",
    )
    parser.add_argument(
        "--line-bottom-margin",
        type=int,
        default=defaults.line_bottom_margin,
        help=f"横线距离画布底部的距离，默认 {defaults.line_bottom_margin}px。",
    )
    parser.add_argument(
        "--line-left-offset",
        type=int,
        default=defaults.line_left_offset,
        help=f"横线和日期距离照片左侧的横向距离，默认 {defaults.line_left_offset}px。",
    )
    parser.add_argument(
        "--line-length",
        type=int,
        default=defaults.line_length,
        help=f"横线长度，默认 {defaults.line_length}px。",
    )
    parser.add_argument(
        "--date-font-size",
        type=int,
        default=defaults.date_font_size,
        help=f"日期字体大小，默认 {defaults.date_font_size}px。",
    )
    parser.add_argument(
        "--date-gap",
        type=int,
        default=defaults.date_gap_below_line,
        help=f"日期距离横线的垂直距离，默认 {defaults.date_gap_below_line}px。",
    )
    parser.add_argument(
        "--date-tracking",
        type=float,
        default=defaults.date_tracking,
        help=f"日期字距，默认 {defaults.date_tracking}px。",
    )
    parser.add_argument(
        "--info-font-size",
        type=int,
        default=defaults.info_font_size,
        help=f"拍摄参数字体大小，默认 {defaults.info_font_size}px。",
    )
    parser.add_argument(
        "--info-gap-x",
        type=int,
        default=defaults.info_gap_x,
        help=f"拍摄参数距离照片左侧的水平距离，默认 {defaults.info_gap_x}px。",
    )
    parser.add_argument(
        "--location-gap-x",
        type=int,
        default=defaults.location_gap_x,
        help=f"地点距离照片左侧的水平距离，默认 {defaults.location_gap_x}px。",
    )
    parser.add_argument(
        "--info-bottom-gap",
        type=int,
        default=defaults.info_bottom_gap,
        help=f"拍摄参数距离照片底部的距离，默认 {defaults.info_bottom_gap}px。",
    )
    parser.add_argument(
        "--info-tracking",
        type=float,
        default=defaults.info_tracking,
        help=f"拍摄参数字距，默认 {defaults.info_tracking}px。",
    )
    parser.add_argument(
        "--location-font-size",
        type=int,
        default=defaults.location_font_size,
        help=f"地点字体大小，默认 {defaults.location_font_size}px。",
    )
    parser.add_argument(
        "--location-tracking",
        type=float,
        default=defaults.location_tracking,
        help=f"地点字距，默认 {defaults.location_tracking}px。",
    )
    parser.add_argument(
        "--info-location-gap",
        type=int,
        default=defaults.info_location_gap,
        help=f"地点和相机参数之间的距离，默认 {defaults.info_location_gap}px。",
    )
    parser.add_argument(
        "--output-mode",
        choices=("video", "adaptive", "original"),
        default=defaults.output_mode,
        help=(
            "输出模式。video 固定输出 3840x2160；adaptive 根据照片内容自动调整画布宽度；"
            "original 保留原始像素尺寸。"
            f"当前默认 {defaults.output_mode}。"
        ),
    )
    parser.add_argument(
        "--color-mode", choices=("preserve", "srgb"), default=defaults.color_mode,
        help="preserve 保留来源色域，混合 SDR 色域使用 ProPhoto RGB；srgb 显式转换为 8 位 SDR。",
    )
    parser.add_argument(
        "--metadata", choices=("safe", "none"), default=defaults.metadata_policy,
        help="safe 保留筛选后的拍摄信息和版权（默认）；none 删除非色彩元数据。",
    )
    parser.add_argument(
        "--preserve-gps", nargs="?", const=True, type=parse_bool, default=defaults.preserve_gps,
        help="保留单图输出中的 GPS 元数据（默认关闭）；不控制地点联网查询。",
    )
    parser.add_argument(
        "--png-compression", choices=("fast", "balanced", "small"),
        default=defaults.png_compression,
        help="PNG 无损压缩：fast 快速导出、balanced 均衡（默认）、small 较小文件；JPEG 忽略。",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=defaults.jpeg_quality,
        help=(
            "JPEG 输出质量，范围 1-100。默认 "
            f"{defaults.jpeg_quality}，使用 .png 输出时忽略。"
        ),
    )
    parser.add_argument(
        "--include-gps-location",
        nargs="?",
        const=True,
        default=defaults.include_gps_location,
        type=parse_bool,
        help=(
            "如果照片包含 GPS 信息，是否联网反查城市/地点并追加到拍摄参数后面。"
            f"当前默认 {str(defaults.include_gps_location).lower()}，可传 true/false 临时覆盖。"
        ),
    )
    parser.add_argument(
        "--show-signature",
        nargs="?",
        const=True,
        default=defaults.show_signature,
        type=parse_bool,
        help=(
            "是否显示 assets 中的签名图片。"
            f"当前默认 {str(defaults.show_signature).lower()}，可传 true/false 临时覆盖。"
        ),
    )
    parser.add_argument(
        "--signature-text",
        default=defaults.signature_text,
        help=(
            "当 --show-signature false 时，可用这行文字替代签名图片。"
            "文字会居中绘制在固定高度透明画布中，并按画布边缘与 logo 保持间距。"
        ),
    )
    parser.add_argument(
        "--signature-font",
        default=defaults.signature_font_path,
        help=(
            "签名替代文字字体文件路径。默认英文跟随日期字体，中文使用黑体-简。"
        ),
    )
    parser.add_argument(
        "--signature-font-size",
        type=int,
        default=defaults.signature_font_size,
        help=(
            "签名替代文字字号。文字会居中绘制在高度为 logo/签名高度的透明画布中，"
            f"默认 {defaults.signature_font_size}px。"
        ),
    )
    parser.add_argument(
        "--font",
        default=defaults.font_path,
        help=f"日期和拍摄参数字体文件路径。当前默认 {defaults.font_path or '自动寻找等宽字体'}。",
    )
    parser.add_argument(
        "--location-font",
        default=defaults.location_font_path,
        help=(
            "地点文字字体文件路径。当前默认 "
            f"{defaults.location_font_path or '自动寻找等宽字体'}。"
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="只输出警告和错误，隐藏正常导出摘要。",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出更详细的调试信息。",
    )

    return parser


def config_from_args(args):
    return LayoutConfig(
        photo_height=args.height,
        line_bottom_margin=args.line_bottom_margin,
        line_left_offset=args.line_left_offset,
        line_length=args.line_length,
        date_font_size=args.date_font_size,
        date_gap_below_line=args.date_gap,
        date_tracking=args.date_tracking,
        info_font_size=args.info_font_size,
        info_gap_x=args.info_gap_x,
        location_gap_x=args.location_gap_x,
        info_bottom_gap=args.info_bottom_gap,
        info_tracking=args.info_tracking,
        font_path=args.font,
        location_font_path=args.location_font,
        location_font_size=args.location_font_size,
        location_tracking=args.location_tracking,
        info_location_gap=args.info_location_gap,
        output_mode=args.output_mode,
        include_gps_location=args.include_gps_location,
        show_signature=args.show_signature,
        signature_text=args.signature_text,
        signature_font_path=args.signature_font,
        signature_font_size=args.signature_font_size,
        color_mode=args.color_mode,
        metadata_policy=args.metadata,
        preserve_gps=args.preserve_gps,
        jpeg_quality=args.jpeg_quality,
        png_compression=args.png_compression,
    )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(quiet=args.quiet, verbose=args.verbose)
    if args.batch:
        if args.output:
            parser.error("--batch 逐张生成输出文件名，不能与 -o 同用。")
        config = config_from_args(args)
        failed = 0
        for index, photo in enumerate(args.photos, start=1):
            progress(f"批量处理第 {index}/{len(args.photos)} 张：{Path(photo).name}")
            try:
                make_canvas([photo], make_default_output_path([photo]), config=config)
            except Exception as exc:
                failed += 1
                error(f"{photo}：{exc}")
        summary = f"成功处理 {len(args.photos) - failed} 张照片，失败 {failed} 张。"
        if failed:
            raise RuntimeError(summary)
        info(summary)
        return
    output_path = args.output or make_default_output_path(args.photos)
    make_canvas(args.photos, output_path, config=config_from_args(args))


def run():
    try:
        main()
    except Exception as exc:
        error(str(exc))
        sys.exit(1)
