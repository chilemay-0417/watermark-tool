# Watermark Tool

一个为照片添加水印和边框的工具。可以处理单张照片，也可以一次选择多张照片，批量导出每张照片的水印图片；还支持将多张照片合成为一张排版图：`video` 最多 3 张，`adaptive` 不限制张数。

水印可包含拍摄日期、焦距、光圈、快门、ISO、拍摄地点、相机品牌 Logo 和个人签名。在 macOS 中配置 Finder 快速操作后，选中照片，右键即可运行。

当前版本：**1.1.0**（版本 1.1）。[下载最新版本](https://github.com/chilemay-0417/watermark-tool/releases/latest) · [更新日志](CHANGELOG.md)

## 两种输出模式

### video：为照片制作视频

生成统一的 **3840 × 2160（16:9）** 图片，方便导入剪辑软件制作视频相册。照片按原比例缩放，单张照片左右留白相等；多张照片的左右留白和图间距相等。

**单张照片**

<a href="samples/phone1_watermark.jpg"><img src="docs/previews/phone1_watermark.jpg" alt="video 模式：单张照片，左右留白相等" width="720"></a>

**两张竖向照片合成**

<a href="samples/vertical1_vertical2_watermark.jpg"><img src="docs/previews/vertical1_vertical2_watermark.jpg" alt="video 模式：两张竖向照片，左右留白与图间距相等" width="720"></a>

**多张照片：自动降低高度，给水印留出空间**

当照片间距不足以容纳 Logo 和相邻照片的拍摄参数时，工具会自动降低所有照片的统一高度，并保持等间距。下图是三张照片的合成结果：

<a href="samples/phone2_vertical1_vertical2_watermark.jpg"><img src="docs/previews/phone2_vertical1_vertical2_watermark.jpg" alt="video 模式：三张照片自动降低高度，避免 Logo 与相邻参数重叠" width="720"></a>

video 支持 **1～3 张**照片。防重叠计算以水印和参数的横向占用之和 `a` 为基准：原始间距小于 `a` 时，自动降低照片高度，直到间距至少达到 `1.5 × a`。横线和日期保留原有字号、长度和间距，不随照片缩小。

### adaptive：让边框贴合照片

根据照片内容调整画布宽度，保留照片高度，适合直接分享单张照片或多图长拼接。

**单张横向照片**

<a href="samples/horizontal1_watermark.jpg"><img src="docs/previews/horizontal1_watermark.jpg" alt="adaptive 模式：单张横向照片，边框贴合照片" width="640"></a>

**单张竖向照片**

<a href="samples/phone2_watermark.jpg"><img src="docs/previews/phone2_watermark.jpg" alt="adaptive 模式：单张竖向照片与紧凑边框" width="360"></a>

**多张照片自由拼接**

程序不限制拼接张数或画布宽度，横向、竖向照片可以混合排列。下图将五张照片拼接成一张长图：

<a href="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg"><img src="docs/previews/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg" alt="adaptive 模式：五张不同设备、不同方向的照片拼接成长图" width="960"></a>

多张照片时，**照片间距 = 左留白 = 右留白 = 1.8 × 上留白**，取整到整数像素。例如上留白为 100px 时，横向间距均为 180px。实际可导出的尺寸受内存、图片格式和查看软件影响，超长图片的说明见下方限制部分。

以上使用压缩预览，点击图片可查看 `samples/` 中的完整成片。两种模式都支持单张导出和多图合成，默认使用 `adaptive`。

## 1.1 更新

- **布局更规整**：video 统一边距并自动避让水印；adaptive 按上留白的 1.8 倍设置多图间距，取消张数限制。
- **拍摄参数更准确**：优先显示 35mm 等效焦距，缺失时使用实际焦距；修复慢快门和小数秒的显示问题。
- **导出更稳妥**：保护输入原图，保存失败不会破坏已有输出；长文件名自动缩短，越界和无效参数会给出明确提示。
- **运行更省资源**：照片按最终尺寸只缩放一次，逐张读取并释放；文字和品牌规则复用，Finder 两个入口共用检查逻辑。

完整记录见 [更新日志](CHANGELOG.md)。从 1.0 升级时，更新整个项目文件夹并保留 `scripts/`、`src/`、`assets/`，原有 Finder 快速操作路径仍可使用。

## 安装

需要 **Python 3.10 或更新版本**；Finder 右键快速操作需要 macOS。

下载项目并解压，或克隆仓库后，在终端进入项目目录，直接安装依赖：

```bash
cd /path/to/watermark_tool
python3 -m pip install -r requirements.txt
chmod +x watermark_batch_each.sh watermark_combine_selected.sh
```

将 `/path/to/watermark_tool` 替换为项目实际路径。首次运行可以用自带样张验证，下面的命令关闭 GPS 联网查询：

```bash
python3 layout.py samples/horizontal1.jpg --include-gps-location false
```

默认在原图所在目录生成 `horizontal1_watermark.jpg`。如果该名称已经存在，会追加 `_2`、`_3` 等序号。需要使用项目记录的依赖版本时，将安装命令中的 `requirements.txt` 换成 `requirements.lock`。

## 在 Finder 中右键使用

打开 macOS「自动操作」（Automator），新建「快速操作」，添加「运行 Shell 脚本」，设置如下：

| 设置项 | 选择 |
| --- | --- |
| 工作流程收到当前 | 图像文件 |
| 位于 | 访达（Finder） |
| Shell | `/bin/zsh` |
| 传递输入 | 作为自变量 |

**单张 / 批量加水印**：在脚本框内粘贴以下内容，保存为「照片加水印」。选择一张或多张照片时，每张照片都会单独导出。

```bash
"/path/to/watermark_tool/watermark_batch_each.sh" "$@"
```

**多图合成**：另建一个快速操作，粘贴以下内容，保存为「合成水印照片」。选中的照片合成为一张图片。`adaptive` 不限制张数；`video` 最多 3 张。

```bash
"/path/to/watermark_tool/watermark_combine_selected.sh" "$@"
```

将两个脚本路径替换为项目实际路径。请保留整个项目文件夹，包括共用的 `scripts/` 目录。保存后，在 Finder 中选中照片，右键 →「快速操作」→ 选择对应操作。

脚本会自动寻找已安装所需依赖的 Python。如需指定 Python，可在脚本调用前添加 `export WATERMARK_PYTHON_BIN="/path/to/python3"`，填入安装依赖时使用的 Python 路径。

右键操作使用 [config.py](src/watermark_tool/config.py) 中的默认设置。要切换模式，修改其中的 `OUTPUT_MODE = "adaptive"` 或 `OUTPUT_MODE = "video"`；要关闭地点联网查询，将 `INCLUDE_GPS_LOCATION` 改为 `False`。两个 Shell 脚本接收照片路径，临时调整其他参数请使用下方命令行入口。

## 适配相机与图片格式

工具根据照片 EXIF 中的厂商和型号信息自动匹配品牌 Logo，并读取拍摄参数。当前附带 Logo 和匹配规则的品牌有：

| 相机品牌 | 手机品牌 |
| --- | --- |
| Canon、Nikon、Sony、Fujifilm | Apple、Honor、Samsung、OnePlus |
| Leica、Hasselblad、Ricoh、Panasonic Lumix | OPPO、vivo、Xiaomi |
| Olympus / OM System（使用 Olympus 标志） | |

品牌匹配不代表所有机型都经过验证。没有 EXIF、未匹配到品牌或缺少 Logo 文件时，会跳过品牌标志，仍可按设置显示签名。

支持 JPEG、PNG、TIFF、WebP；HEIC / HEIF 通过 `pillow-heif` 读取，NEF、ARW、CR2、CR3、RAF、DNG 等 RAW 格式通过 `rawpy` 读取。实际 RAW 兼容性取决于相机型号和解码库，拍摄参数不一定能够完整读取。

品牌规则位于 [assets/brands.json](assets/brands.json)。添加品牌 Logo、更换签名和指定资源目录的方法见 [定制说明](docs/customization.md)。

## 常用命令

以下命令均在项目目录中运行。示例关闭了 GPS 查询；需要显示拍摄地点时，将 `--include-gps-location false` 改为 `true`。

```bash
# 单张照片：边框紧凑贴合照片
python3 layout.py samples/horizontal1.jpg --output-mode adaptive --include-gps-location false

# 单张照片：生成 16:9 视频素材
python3 layout.py samples/phone1.jpg --output-mode video --include-gps-location false

# 两张竖向照片：合成为一张 16:9 图片
python3 layout.py samples/vertical1.jpg samples/vertical2.jpg --output-mode video --include-gps-location false

# 多张照片：合成长图，保持原定照片高度
python3 layout.py samples/horizontal1.jpg samples/phone1.jpg samples/phone2.jpg samples/vertical1.jpg samples/vertical2.jpg --output-mode adaptive --include-gps-location false

# 指定输出文件，使用 .png 后缀导出 PNG
python3 layout.py samples/horizontal1.jpg -o output.png --include-gps-location false

# 使用自定义文字替代签名图片
python3 layout.py samples/horizontal1.jpg --show-signature false --signature-text "Shot by You" --include-gps-location false

# 完全隐藏签名图片及替代文字
python3 layout.py samples/horizontal1.jpg --show-signature false --signature-text "" --include-gps-location false
```

批量为多张照片分别导出时，可使用 Finder 的「照片加水印」，或运行：

```bash
./watermark_batch_each.sh samples/horizontal1.jpg samples/vertical2.jpg
```

这条批量命令与 Finder 使用相同默认设置，包括输出模式和 GPS 开关。直接向 `layout.py` 传入多张照片表示**合成一张**，而不是逐张导出。

默认单张输出名为 `原文件名_watermark.jpg`；合成输出名为 `文件名1_文件名2_watermark.jpg`，保存在第一张照片的目录。文件名过长时会自动缩短为首张照片名加其余张数，避免超过文件系统限制。默认命名不会自动加入模式名称；可用 `-o` 自行指定。显式指定 `-o` 时，程序会拒绝覆盖任何输入原图；已有的其他输出文件会在新文件完整写入后被替换。输出仅支持 `.jpg`、`.jpeg` 和 `.png`。

常用调整参数：

| 参数 | 用途 | 当前默认值 |
| --- | --- | --- |
| `--output-mode` | `video` 固定 16:9；`adaptive` 调整画布宽度 | `adaptive` |
| `--height` | 照片高度，单位为像素；video 空间不足时自动降低 | `1850` |
| `--jpeg-quality` | JPEG 质量，范围 1～100；分享可尝试 95 | `100` |
| `--include-gps-location` | 是否联网查询拍摄地点 | `true` |
| `--show-signature` | 是否显示签名图片 | `true` |
| `--signature-text` | 关闭签名图片后显示的文字，空字符串表示隐藏 | `哈哈哈` |

日期、字体、线条和间距等更多参数可运行 `python3 layout.py --help` 查看。长期使用的默认设置可在 [config.py](src/watermark_tool/config.py) 中修改。

## 使用说明与当前限制

- **地点查询**：默认开启。照片有 GPS 时，经纬度会发送给 Nominatim（OpenStreetMap）查询地名；照片文件本身在本地处理。关闭方式为 `--include-gps-location false`，或修改默认配置。查询失败或超时时，图片仍可继续导出。
- **多图排版**：`video` 自动降低照片高度以容纳照片和两侧水印；如果字号或间距本身已占满画布，会提示减小参数或切换 `adaptive`。日期和横线保留指定字号及长度，窄图下仍需检查相邻日期是否拥挤。为保证整数像素上的等间距，video 部分照片宽度会在等比取整结果上增加 1px，不裁切内容。adaptive 自定义高度过大、使 1.8 倍上留白不足以容纳标记时，会提示降低高度或减小字号。参数、地点、日期或签名超出画布上下边界时，会明确报错并提示调整，避免悄悄截断内容。
- **超长图片**：`adaptive` 不设布局宽度或张数上限，但实际受内存、图片格式及查看软件能力影响。JPEG 编码器单边最多支持 65,500px，超过时请使用 `-o 长图.png`。程序会逐张解码并释放照片，但最终画布仍需要内存。
- **拍摄参数**：焦距优先显示 EXIF 中有效的 35mm 等效焦距；缺失、为 0 或无效时显示实际焦距，两者都无效时省略。快门在倒数表示误差不超过 0.1% 时显示为 `1/Ns`，否则保留秒数，例如 `0.8s`、`0.4s`、`1.25s`。
- **拍摄日期**：缺失日期时，当前版本会使用处理时的日期和时间。需要准确记录时，请核对成片文字。
- **色彩与元数据**：当前导出不保留原始 EXIF，也未进行 ICC 色彩管理，广色域照片可能出现色彩差异。RAW 会先转换为 8-bit RGB，再进入排版流程。
- **运行环境**：若 Finder 提示缺少依赖，可在终端运行 `python3 -c "import sys; print(sys.executable)"` 查看 Python 路径，并通过 `WATERMARK_PYTHON_BIN` 指定它。字体默认从系统查找，也可通过 `--font`、`--location-font` 指定。

## 开发与许可

安装开发依赖并运行检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover
python3 -m ruff check .
```

README 预览可用 `python3 scripts/build_readme_previews.py` 重新生成；完整成片保存在 `samples/`，压缩预览保存在 `docs/previews/`。

代码使用 [MIT License](LICENSE)。照片样张、个人签名和第三方品牌 Logo 的使用与分发需分别确认其授权。
