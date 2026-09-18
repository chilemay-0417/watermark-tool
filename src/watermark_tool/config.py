from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple

from PIL import Image

from .theme import ColorInput, parse_color


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
SAMPLES_DIR = PROJECT_ROOT / "samples"

# 输出模式：video 固定 4K；adaptive 固定高度、调整宽度；original 保留原尺寸。
OUTPUT_MODE = "video"

# 内置配色：编号与 README 样张对应，每组依次为（背景色，水印色）。
# 按 01–12 连续编号；logo 始终使用素材原色。
COLOR_PRESETS = {
    "01": ("#F5F5F7", "#1D1D1F"),  # 极简瓷白
    "02": ("#E7E5E0", "#3A3A3C"),  # 原色钛银
    "03": ("#F2EEE6", "#51483E"),  # 星光米白
    "04": ("#E8EEE8", "#3C5145"),  # 鼠尾草雾
    "05": ("#ECE0CC", "#594735"),  # 沙丘香槟
    "06": ("#DFE2E6", "#343B45"),  # 北欧云灰
    "07": ("#1D1D1F", "#F5F5F7"),  # 深空石墨
    "08": ("#1B2635", "#E6EDF5"),  # 午夜深蓝
    "09": ("#304457", "#E4ECF3"),  # 蓝钛暮色
    "10": ("#263D34", "#E8EFE7"),  # 松针森林
    "11": ("#383342", "#EBE6F1"),  # 紫夜烟岚
    "12": ("#3E342F", "#EEE4D8"),  # 可可乌木
}

# 内部初始化，无需修改；确保重新加载配置时不会沿用上次选择。
BACKGROUND_COLOR = WATERMARK_COLOR = None

# 使用内置配色：修改编号即可切换，默认 "01" 为极简瓷白。
# 例如 "09" 是蓝钛暮色；注释下一行后，下面的手动配色才会生效。
BACKGROUND_COLOR, WATERMARK_COLOR = COLOR_PRESETS["01"]

# 手动配色：先注释上面的 COLOR_PRESETS 赋值行，再修改下面两个颜色值。
# 保留 if 条件和缩进，避免手动颜色覆盖已经选用的内置配色。
if BACKGROUND_COLOR is None and WATERMARK_COLOR is None:
    # 边框 / 留白颜色，适用于 video、adaptive、original。
    # 支持 CSS4 颜色名称、"rgb(40, 40, 40)"、(40, 40, 40)、"#282828"。
    BACKGROUND_COLOR = "black"

    # 水印统一颜色：同时设置文字、横线和签名，不改变品牌 logo 的颜色。
    # 不会随背景自动变色；深色背景可用 "white"，浅色背景可用 "black"。
    WATERMARK_COLOR = "white"

# 单项颜色；None 跟随 WATERMARK_COLOR。INFO_COLOR 同时控制拍摄参数和地点。
LINE_COLOR = None
DATE_COLOR = None
INFO_COLOR = None
SIGNATURE_COLOR = None

# video 模式下的固定输出尺寸。
CANVAS_W = 3840
CANVAS_H = 2160

# 照片缩放后的统一高度，宽度按原图比例自动计算。
DEFAULT_PHOTO_HEIGHT = 1850

# 横线距离画布底部的距离。数值越大，横线和日期越往上。
DEFAULT_LINE_BOTTOM_MARGIN = 110

# 横线和日期相对照片左边缘的水平偏移。
DEFAULT_LINE_LEFT_OFFSET = 80

# 每张照片下方横线的长度。
DEFAULT_LINE_LENGTH = 900

# logo、签名图片和签名替代文字透明画布的统一高度。旋转后会影响右侧占用宽度。
LOGO_HEIGHT = 55

# 右侧签名和品牌 logo 之间的垂直间距。
LOGO_SIGNATURE_GAP = 60

# 右侧签名 / logo 与最右侧照片之间的水平间距。
RIGHT_GAP = 20

# 日期距离横线下方的垂直距离。
DATE_GAP_BELOW_LINE = 20

# 日期文字字号。
DATE_FONT_SIZE = 55

# 日期文字字距。Courier New 是等宽字体，一般 0-2 就够。
DATE_TRACKING = 1

# 日期和拍摄参数字体路径。None 表示自动寻找等宽字体，优先 Courier New。
FONT_PATH = None

# 是否默认联网读取 GPS 地点。开启后会调用 Nominatim 反查经纬度。
INCLUDE_GPS_LOCATION = True

# GPS 地点语言。en 会尽量输出英文，并清理 district/county 等后缀。
GPS_LOCATION_LANGUAGE = "en"

# GPS 地点反查超时时间，单位秒。
GPS_LOCATION_TIMEOUT = 5

# 地点文字字体路径。None 表示自动寻找等宽字体，优先 Courier New。
LOCATION_FONT_PATH = None

# 地点文字字号。
LOCATION_FONT_SIZE = 35

# 地点文字字距。
LOCATION_TRACKING = 1

# 地点文字和拍摄参数文字之间的距离。
INFO_LOCATION_GAP = 35

# 拍摄参数字号，例如焦距、光圈、快门、ISO。
INFO_FONT_SIZE = 35

# 拍摄参数字距。
INFO_TRACKING = 1

# 拍摄参数距离照片左侧的水平距离。
INFO_GAP_X = 15

# 地点文字距离照片左侧的水平距离。
LOCATION_GAP_X = 15

# 拍摄参数距离照片底部的距离。
INFO_BOTTOM_GAP = 0

# assets/ 中的签名文件名。
SIGNATURE_FILE = "signature_400.jpg"

# 是否默认显示签名图片。
SHOW_SIGNATURE = True

# 关闭签名图片时可显示的一行替代文字。留空则不显示替代文字。
SIGNATURE_TEXT = "哈哈哈"

# 自定义签名文字字体路径。None 表示英文跟随日期字体，中文默认黑体-简。
SIGNATURE_FONT_PATH = None

# 自定义签名文字字号。文字会居中绘制在高度为 LOGO_HEIGHT 的透明画布中。
SIGNATURE_FONT_SIZE = 50

# assets/ 中的品牌 logo 匹配规则。
BRAND_RULES_FILE = "brands.json"

# JPEG 默认最高质量；仍为有损编码，保真输出使用 PNG。
JPEG_QUALITY = 100

# PNG 三档均为无损，仅改变编码耗时和体积。
PNG_COMPRESSION = "balanced"
PNG_COMPRESSION_LEVELS = {"fast": 1, "balanced": 6, "small": 9}

RGB = Tuple[int, int, int]


@dataclass
class LayoutConfig:
    """排版入口使用的可调参数，以及渲染阶段缓存的字体对象。"""

    photo_height: int = DEFAULT_PHOTO_HEIGHT
    line_bottom_margin: int = DEFAULT_LINE_BOTTOM_MARGIN
    line_left_offset: int = DEFAULT_LINE_LEFT_OFFSET
    line_length: int = DEFAULT_LINE_LENGTH
    background_color: ColorInput = BACKGROUND_COLOR
    line_color: Optional[ColorInput] = LINE_COLOR
    line_width: int = 2
    date_color: Optional[ColorInput] = DATE_COLOR
    date_font_size: int = DATE_FONT_SIZE
    date_gap_below_line: int = DATE_GAP_BELOW_LINE
    date_tracking: float = DATE_TRACKING
    info_color: Optional[ColorInput] = INFO_COLOR
    info_font_size: int = INFO_FONT_SIZE
    info_gap_x: int = INFO_GAP_X
    location_gap_x: int = LOCATION_GAP_X
    info_bottom_gap: int = INFO_BOTTOM_GAP
    info_tracking: float = INFO_TRACKING
    font_path: Optional[str] = FONT_PATH
    location_font_path: Optional[str] = LOCATION_FONT_PATH
    location_font_size: int = LOCATION_FONT_SIZE
    location_tracking: float = LOCATION_TRACKING
    info_location_gap: int = INFO_LOCATION_GAP
    output_mode: str = OUTPUT_MODE
    include_gps_location: bool = INCLUDE_GPS_LOCATION
    gps_location_language: str = GPS_LOCATION_LANGUAGE
    gps_location_timeout: int = GPS_LOCATION_TIMEOUT
    show_signature: bool = SHOW_SIGNATURE
    signature_text: str = SIGNATURE_TEXT
    signature_font_path: Optional[str] = SIGNATURE_FONT_PATH
    signature_font_size: int = SIGNATURE_FONT_SIZE
    color_mode: str = "preserve"
    metadata_policy: str = "safe"
    preserve_gps: bool = False
    jpeg_quality: int = JPEG_QUALITY
    png_compression: str = PNG_COMPRESSION
    date_font: Optional[Any] = None
    info_font: Optional[Any] = None
    location_font: Optional[Any] = None
    signature_font: Optional[Any] = None
    watermark_color: ColorInput = WATERMARK_COLOR
    signature_color: Optional[ColorInput] = SIGNATURE_COLOR
    _color_inputs: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        # Keep None overrides so a CLI watermark color applies to all inherited items.
        names = ("background_color", "watermark_color", "line_color", "date_color",
                 "info_color", "signature_color")
        self._color_inputs = {name: getattr(self, name) for name in names}
        self.background_color = parse_color(self.background_color, "BACKGROUND_COLOR")
        self.watermark_color = parse_color(self.watermark_color, "WATERMARK_COLOR")
        for name in ("line_color", "date_color", "info_color", "signature_color"):
            value = getattr(self, name)
            setattr(self, name, self.watermark_color if value is None
                    else parse_color(value, name.upper()))


@dataclass
class PhotoMetadata:
    """一张照片最终会显示和用于选 logo 的元信息。"""

    date: str
    make: str
    model: str
    settings: str
    location: str


@dataclass
class PhotoItem:
    """排版阶段使用的一张照片，原图在确定最终布局后只缩放一次。"""

    path: Path
    image: Optional[Image.Image]
    metadata: PhotoMetadata
    settings_image: Optional[Image.Image] = None
    location_image: Optional[Image.Image] = None
    source_size: Optional[Tuple[int, int]] = None
    source_metadata: Optional[Any] = None


@dataclass
class PhotoWatermark:
    """一张照片右下侧需要绘制的品牌 logo 和签名状态。"""

    logo: Optional[Image.Image]
    logo_name: Optional[str]
    include_signature: bool


@dataclass
class WatermarkAssets:
    """右侧 logo / 签名资源与逐图水印计划；尺寸由布局阶段实时测量。"""

    signature: Optional[Image.Image]
    logo: Optional[Image.Image]
    logo_name: Optional[str]
    photo_marks: Optional[Any] = None


@dataclass
class LayoutMetrics:
    """画布和照片横向排版计算结果。"""

    canvas_w: int
    canvas_h: int
    photo_gap: int
    photo_top: int
    side_margin: int
    photo_height: int
    photo_widths: Tuple[int, ...]


@dataclass
class PhotoPlacement:
    """已贴入画布的一张照片位置。"""

    x: int
    y: int
    w: int
    h: int
