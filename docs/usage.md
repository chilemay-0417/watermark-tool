# 使用指南

[返回 README](../README.md) · [签名与品牌定制](customization.md) · [更新日志与升级说明](../CHANGELOG.md)

本文适用于 **2.0.0**。首次安装见 [README](../README.md#安装与使用)；从 1.1.0 升级见 [升级步骤](../CHANGELOG.md#从-110-升级)。以下命令均在项目目录中运行，并先执行 `source .venv/bin/activate`。需要使用项目记录的依赖版本时，可将 `requirements.txt` 换成 `requirements.lock`。

## 在 Finder 中右键使用

### 1. 安装并验证环境

先完成 README 中的 Python 和依赖安装。建议将项目放在固定位置，例如 `~/Pictures/watermark_tool`，保留其中的 `layout.py`、`src/`、`assets/`、`scripts/` 和两个 `.sh` 入口文件。

打开「终端」，进入实际项目目录，赋予脚本执行权限，并用样张验证：

```bash
cd "$HOME/Pictures/watermark_tool"
chmod +x watermark_batch_each.sh watermark_combine_selected.sh
.venv/bin/python layout.py samples/horizontal1.jpg --include-gps-location false
```

出现完成提示后，在 `samples/` 中确认生成了带 `_watermark` 的图片，再继续配置。若项目放在其他位置，请替换上面的目录。可在项目目录运行 `pwd` 获取完整路径，供下一步粘贴。

### 2. 创建「照片加水印」

1. 按 `⌘ Space` 搜索并打开「自动操作」（Automator）。
2. 选择「文件」→「新建」→「快速操作」→「选取」。
3. 在工作流程顶部，将接收内容设为「图像文件」，应用设为「访达（Finder）」。
4. 在左侧搜索「运行 Shell 脚本」，双击或拖入右侧工作流程区域。
5. 将 Shell 设为 `/bin/zsh`，将「传递输入」设为「作为自变量」。
6. 删除脚本框中的默认内容，粘贴以下一行：

   ```bash
   "/完整路径/watermark_tool/watermark_batch_each.sh" "$@"
   ```

   将 `/完整路径/watermark_tool` 替换为 `pwd` 显示的路径，例如 `/Users/你的用户名/Pictures/watermark_tool`。保留两组英文双引号和 `"$@"`，这样带空格的路径及多张照片才能正确传入。
7. 按 `⌘ S`，命名为「照片加水印」并保存。

这个操作会为选中的每张照片分别导出成片。

### 3. 创建「合成水印照片」

再次新建「快速操作」，按上一步设置图像文件、Finder、`/bin/zsh` 和「作为自变量」，将脚本内容换成：

```bash
"/完整路径/watermark_tool/watermark_combine_selected.sh" "$@"
```

替换为同一项目的完整路径，保存为「合成水印照片」。这个操作将所选照片合成一张；默认 `video` 最多支持 3 张，`adaptive` 和 `original` 不设张数上限。

### 4. 从右键菜单运行

在 Finder 中选中照片，右键 →「快速操作」→「照片加水印」或「合成水印照片」。运行时无需打开终端或手动激活虚拟环境。

成片默认保存在输入照片所在目录；合成时使用第一张输入照片的目录。重名时自动追加序号。合成成功后会在 Finder 中定位成片；失败时会打开错误日志。批量处理中单张失败会继续处理其余照片。

需要固定拼接顺序时，使用命令行按顺序列出照片路径。不要直接在 Automator 中点「运行」测试，这时可能没有选中的照片传入。

### 5. 修改默认设置与排错

右键操作使用 [config.py](../src/watermark_tool/config.py) 的默认值。常用设置如下，保存后下次运行生效：

```python
OUTPUT_MODE = "adaptive"      # video / adaptive / original
INCLUDE_GPS_LOCATION = False   # 关闭地点联网查询
```

两个入口脚本只接收照片路径。需要临时调整参数或导出 PNG 时，使用下方命令行示例。

| 情况 | 处理方法 |
| --- | --- |
| 右键菜单中没有操作 | 确认选中的是图片，并检查工作流程接收「图像文件」、应用为 Finder。若菜单有「自定」，进入后启用对应操作；也可在系统设置中搜索「扩展」检查 Finder 项目。 |
| 提示没有收到照片 | 将「传递输入」改为「作为自变量」，确认脚本末尾保留 `"$@"`，然后从 Finder 选图运行。 |
| 提示找不到脚本或 Permission denied | 核对完整路径和引号，重新执行上面的 `chmod +x`。项目移动或改名后，需要同步修改两个快速操作中的路径。 |
| 提示找不到 Python 或缺少依赖 | 在项目目录执行 `.venv/bin/python -m pip install -r requirements.txt`，再运行样张验证命令。 |
| 提示无法访问照片或保存目录 | 检查文件读写权限；若 macOS 弹出访问请求，按提示允许访问照片所在文件夹。 |

脚本会优先尝试项目 `.venv/bin/python`。需要指定其他已装好依赖的 Python 时，在 Automator 的脚本调用前添加：

```bash
export WATERMARK_PYTHON_BIN="/完整路径/python3"
```

创建快速操作的系统界面说明可参考 [Apple 自动操作使用手册](https://support.apple.com/zh-cn/guide/automator/aut7cac58839/mac)。

## 命令与参数

```bash
# 单张照片：紧凑边框
python3 layout.py photo.jpg --output-mode adaptive

# 两张照片：合成为 16:9 视频素材（按输入顺序排列）
python3 layout.py photo1.jpg photo2.jpg --output-mode video

# 多张照片：合成长图
python3 layout.py photo1.jpg photo2.jpg photo3.jpg --output-mode adaptive

# 保留原始尺寸并导出 PNG
python3 layout.py photo.png --output-mode original -o output.png

# 逐张批量导出，关闭地点联网查询
python3 layout.py --batch photo1.jpg photo2.jpg --output-mode original --include-gps-location false

# 使用文字签名；文字设为空字符串可完全隐藏签名
python3 layout.py photo.jpg --show-signature false --signature-text "Shot by You"
```

**多张输入默认合成一张，添加 `--batch` 才会逐张导出。** `--batch` 不能与 `-o` 同用，默认导出 JPEG。

默认文件名为 `原文件名_watermark.jpg`；合成时连接各照片文件名，过长时缩短为首张名称加其余张数。文件保存在第一张输入照片的目录，重名时追加序号。`-o` 仅支持 `.jpg`、`.jpeg`、`.png`，会替换同名的已有成片，但拒绝覆盖任何输入原图；编码失败不会损坏已有输出。

| 参数 | 用途 | 默认值 |
| --- | --- | --- |
| `--output-mode` | `video` 固定 4K；`adaptive` 调整宽度；`original` 保留原尺寸 | `video` |
| `--height` | 照片高度（像素）；不影响 original | `1850` |
| `--jpeg-quality` | JPEG 质量 1～100；不影响 PNG | `100` |
| `--include-gps-location` | 是否发送经纬度联网查询地点 | `true` |
| `--color-mode` | `preserve` 保留来源色域；`srgb` 转为 8 位 SDR sRGB | `preserve` |
| `--metadata` | `safe` 保留筛选后的元数据；`none` 删除非色彩元数据 | `safe` |
| `--preserve-gps` | safe 模式下保留单张成片的 EXIF GPS | `false` |
| `--show-signature` | 是否显示签名图片 | `true` |
| `--signature-text` | 关闭签名图片后显示的文字，空字符串表示隐藏 | `哈哈哈` |

日期、字体、线条和间距等参数见 `python3 layout.py --help`；长期默认值在 [config.py](../src/watermark_tool/config.py) 中修改。

## 排版规则

- **video**：固定 3840 × 2160，支持 1～3 张照片，左右留白与图间距相等。空间不足时自动降低照片高度，日期字号和横线长度保持指定值。
- **adaptive**：按指定高度缩放照片，画布宽度随内容增长。单图使用紧凑边框；多图的图间距和左右留白均为上留白的 1.8 倍。
- **original**：保留旋正后的原始像素尺寸，顶部对齐，画布随照片、水印和日期扩展；`--height` 不参与缩放。搭配 PNG 可避免照片重采样和 JPEG 重编码。

## 相机与图片格式

支持 JPEG、PNG、WebP 和 HEIC / HEIF（通过 `pillow-heif` 读取），仅处理 SDR。不支持 RAW、TIFF 或 HDR，请先在照片编辑软件中导出 SDR PNG 或 JPEG。Logo 和签名素材也不支持 TIFF。

工具根据 EXIF 中的厂商和型号匹配 Logo，当前附带以下品牌素材：

| 相机品牌 | 手机品牌 |
| --- | --- |
| Canon、Nikon、Sony、Fujifilm | Apple、Honor、Samsung、OnePlus |
| Leica、Hasselblad、Ricoh、Panasonic Lumix | OPPO、vivo、Xiaomi |
| Olympus / OM System（使用 Olympus 标志） | |

品牌匹配不代表所有机型都经过验证。没有 EXIF、未匹配到品牌或缺少 Logo 时会跳过标志，仍可显示签名。添加品牌及更换签名见 [定制说明](customization.md)。

## 色彩与元数据

默认以 JPEG 100%、4:4:4 色度采样输出，保留来源 RGB 色域。JPEG 仍为有损编码，提高质量不等于按比例提高画质；需要避免照片缩放和 JPEG 重编码时，使用 `--output-mode original -o output.png`。

- **色域**：相同 RGB 色彩定义沿用来源色域；混合 SDR 色域转为 ProPhoto RGB。广色域成片需在支持 ICC 的软件中查看，普通分享可用 `--color-mode srgb`。
- **位深与透明度**：保留色域模式下，高位深来源或混合色域合成导出 PNG 时自动使用 16 位；PNG 保留照片透明度，JPEG 降为 8 位并将透明区域合成到背景上。sRGB 模式输出为 8 位。
- **保真范围**：相同 RGB 定义、无缩放的 PNG 照片区域可保留解码后的原始 RGB 样本；缩放、混合色域转换仍会改变像素。未标记色域的 RGB / 灰度按 sRGB 解释。
- **不支持的输入**：检测到 HDR、损坏或不匹配的 ICC、不支持的色彩标记时会报错。带有效 ICC 的 CMYK / Lab 图片可用 `--color-mode srgb` 转换。
- **单图元数据**：默认保留筛选后的拍摄参数、作者、版权、DPI，以及 XMP / IPTC 中的标题、描述、关键词和评级等；重建尺寸及方向，移除旧缩略图、MakerNote 和设备序列号。
- **多图元数据**：仅保留共同的作者、版权及筛选后的共同 XMP，不指定单一相机、日期或位置。`--metadata none` 删除非色彩元数据，仍保留正确显示所需的色彩配置。

GPS 地点查询默认开启：有坐标时会将经纬度发送给 Nominatim（OpenStreetMap）查询地名，照片文件在本地处理。`--include-gps-location false` 关闭联网；`--preserve-gps true` 控制 safe 模式下单图 EXIF GPS 的导出，两者独立。元数据开关不会隐藏已绘制到图片上的文字。

```bash
# 分享为 sRGB JPEG
python3 layout.py photo.jpg --color-mode srgb -o share.jpg

# 保留单图 EXIF GPS，同时关闭地点联网查询
python3 layout.py photo.jpg --preserve-gps true --include-gps-location false

# 不保留非色彩元数据，也不联网查询地点
python3 layout.py photo.jpg --metadata none --include-gps-location false
```

## 使用限制与排错

- **排版拥挤**：减小高度、字号或间距，或将 video 改为 adaptive / original。日期和横线保持指定大小，窄图仍需检查效果；水印超出上下边界时程序会报错。
- **超长图片**：adaptive / original 的实际大小受内存和图片格式限制。JPEG 单边最多 65,500px，超出时使用 PNG；大批量照片宜用 `--batch` 分别导出。
- **拍摄参数**：焦距优先使用有效的 35mm 等效焦距，缺失时用实际焦距。快门按倒数或小数秒显示，如 `1/125s`、`0.8s`。
- **拍摄日期**：仅使用有效的 EXIF `DateTimeOriginal`，显示到秒，不显示小数秒或时区，不转换到电脑时区。缺失或无效时省略，不使用文件修改时间。
- **字体缺失**：默认查找系统字体，可通过 `--font`、`--location-font` 指定字体文件。
- **处理较慢**：耗时取决于尺寸、格式、硬件和网络。无需地点文字时可关闭 GPS 查询；素材缓存和同进程批处理有助于减少重复处理。

## 缓存与运行速度

macOS 素材缓存位于 `~/Library/Caches/watermark-tool/assets`，只保存处理后的位图 Logo 和签名，不保存照片或 GPS 坐标。更换素材后自动重新生成；可删除该目录清理缓存，下次运行会重建。GPS 查询结果仅在当前进程内复用。

```bash
# 指定缓存目录，或关闭磁盘缓存
WATERMARK_CACHE_DIR=/path/to/cache python3 layout.py photo.jpg
WATERMARK_CACHE_DIR=off python3 layout.py photo.jpg

# 测量本机首次及后续处理耗时，结果保存到指定目录
python3 scripts/benchmark_render.py --output-dir output/benchmark --iterations 3
```

## 支持与开发

遇到问题可提交 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues)，附上系统和 Python 版本、输入格式、复现步骤及完整报错；Finder 失败时会自动打开错误日志。

开发检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover
python3 -m ruff check .
```

README 直接使用 `samples/` 中的展示样张。样张已缩小尺寸并压缩，不用于评估原始画质；工具实际导出仍由所选参数决定。
