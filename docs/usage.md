# 使用指南

[返回 README](../README.md) · [签名与品牌定制](customization.md) · [更新日志](../CHANGELOG.md)

以下命令均在项目目录中运行；安装步骤见 [README](../README.md#安装与使用)。需要使用项目记录的依赖版本时，可将安装命令中的 `requirements.txt` 换成 `requirements.lock`。

## 从 1.1.0 升级到 2.0.0

本文对应已发布的 **2.0.0**。本次升级移除了 1.1.0 的 RAW 和 TIFF 输入支持，并新增色彩管理、原始尺寸布局及元数据保留，完整变化见 [更新日志](../CHANGELOG.md)。

1. 备份自行修改的 `config.py`、签名、Logo 和品牌规则，再更新整个项目文件夹。按需迁移配置，避免直接用旧配置文件覆盖新版。
2. 在项目目录中安装新依赖；Python 要求仍为 3.10+。已有 `.venv` 可继续使用，没有时先创建：

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

   新版增加 NumPy、pyspng，Pillow 最低版本提高至 12.2，不再需要 rawpy；项目也不再依赖 TIFF 解码库 tifffile 和 imagecodecs。Finder 优先使用项目虚拟环境；显式设置的 `WATERMARK_PYTHON_BIN` 仍优先。
3. 原有 RAW 或 TIFF 照片需先导出为 SDR PNG 或 JPEG；检测到 HDR 标记的照片也需先转为 SDR。原来的命令行入口和 Finder 脚本路径保留，项目路径不变时无需重建快速操作。
4. 用样张离线验证新环境；以下示例保留原始尺寸并导出 PNG：

   ```bash
   python layout.py samples/horizontal1.jpg --output-mode original --include-gps-location false -o output/upgrade-check.png
   ```

默认仍为 video 4K、JPEG 100%、4:4:4 色度采样，地点联网查询仍开启。新增的 `--metadata safe` 默认保留筛选后的拍摄信息、作者及版权，但不导出 GPS；需要去除非色彩元数据时用 `--metadata none`。广色域成片需使用支持 ICC 的软件查看；分享时可选择 `--color-mode srgb`。

## 在 Finder 中右键使用

先在项目目录中赋予入口脚本执行权限：

```bash
chmod +x watermark_batch_each.sh watermark_combine_selected.sh
```

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

脚本优先使用项目 `.venv/bin/python`，再寻找其他已安装所需依赖的 Python。如需指定 Python，可在脚本调用前添加 `export WATERMARK_PYTHON_BIN="/path/to/python3"`，填入安装依赖时使用的 Python 路径。

右键操作使用 [config.py](../src/watermark_tool/config.py) 中的默认设置。默认模式为 `video`。`OUTPUT_MODE` 可改为 `adaptive` 或 `original`；地点联网查询默认开启；不需要时将 `INCLUDE_GPS_LOCATION` 改为 `False`。两个 Shell 脚本接收照片路径，临时调整其他参数请使用下方命令行入口。

## 命令与参数

以下命令均在项目目录中、激活 `.venv` 后运行。GPS 查询默认开启；需要离线处理时添加 `--include-gps-location false`。

```bash
# 单张照片：边框紧凑贴合照片
python3 layout.py samples/horizontal1.jpg --output-mode adaptive

# 单张照片：生成 16:9 视频素材
python3 layout.py samples/phone1.jpg --output-mode video

# 两张竖向照片：合成为一张 16:9 图片
python3 layout.py samples/vertical1.jpg samples/vertical2.jpg --output-mode video

# 多张照片：合成长图，保持原定照片高度
python3 layout.py samples/horizontal1.jpg samples/phone1.jpg samples/phone2.jpg samples/vertical1.jpg samples/vertical2.jpg --output-mode adaptive

# 指定输出文件，使用 .png 后缀导出 PNG
python3 layout.py samples/horizontal1.jpg -o output.png

# 使用自定义文字替代签名图片
python3 layout.py samples/horizontal1.jpg --show-signature false --signature-text "Shot by You"

# 完全隐藏签名图片及替代文字
python3 layout.py samples/horizontal1.jpg --show-signature false --signature-text ""
```

批量为多张照片分别导出时，可使用 Finder 的「照片加水印」，或运行：

```bash
./watermark_batch_each.sh samples/horizontal1.jpg samples/vertical2.jpg
```

这条批量命令与 Finder 使用相同默认设置，包括输出模式和 GPS 开关。批处理在同一个 Python 进程中逐张执行，复用水印、字体和地点缓存；单张失败会继续处理其余照片，最终汇总成功与失败数量。

命令行也可显式选择逐张导出，并调整本次参数：

```bash
python3 layout.py --batch samples/horizontal1.jpg samples/vertical2.jpg --output-mode original --include-gps-location false
```

`--batch` 自动为每张照片生成不重名的文件名，不能与 `-o` 同用。不加 `--batch` 时，多张输入仍表示**合成一张**。

默认单张输出名为 `原文件名_watermark.jpg`；合成输出名为 `文件名1_文件名2_watermark.jpg`，保存在第一张照片的目录。文件名过长时会自动缩短为首张照片名加其余张数，避免超过文件系统限制。默认命名不会自动加入模式名称；可用 `-o` 自行指定。显式指定 `-o` 时，程序会拒绝覆盖任何输入原图；已有的其他输出文件会在新文件完整写入后被替换。输出仅支持 `.jpg`、`.jpeg` 和 `.png`。

常用调整参数：

| 参数 | 用途 | 当前默认值 |
| --- | --- | --- |
| `--output-mode` | `video` 固定 4K；`adaptive` 调整宽度；`original` 保留原尺寸 | `video` |
| `--height` | 照片高度，单位为像素；video 空间不足时自动降低 | `1850` |
| `--jpeg-quality` | JPEG 质量，范围 1～100；分享可尝试 95 | `100` |
| `--include-gps-location` | 是否发送经纬度联网查询地点 | `true` |
| `--color-mode` | `preserve` 保留来源色域；`srgb` 转为 SDR sRGB | `preserve` |
| `--metadata` | `safe` 保留筛选后的元数据；`none` 删除 | `safe` |
| `--preserve-gps` | 保留单张成片的 GPS 字段，与联网开关独立 | `false` |
| `--show-signature` | 是否显示签名图片 | `true` |
| `--signature-text` | 关闭签名图片后显示的文字，空字符串表示隐藏 | `哈哈哈` |

日期、字体、线条和间距等更多参数可运行 `python3 layout.py --help` 查看。长期使用的默认设置可在 [config.py](../src/watermark_tool/config.py) 中修改。

## 排版规则

- **video**：固定 3840 × 2160 画布，支持 1～3 张照片，左右留白与图间距相等。原始间距不足以容纳相邻水印时，自动降低统一照片高度，直到间距至少达到横向占用之和 `a` 的 1.5 倍；日期和横线保持指定字号、长度和间距。
- **adaptive**：画布宽度随照片增长，不设张数或布局宽度上限。多图时，照片间距、左留白和右留白均为上留白的 1.8 倍，取整到整数像素；单图使用紧凑边框。

- **original**：保留每张照片原始像素尺寸，顶部对齐，画布随内容扩展；`--height` 不参与缩放。按各张照片高度预留水印顶部空间，日期和横线也纳入画布宽度及图间距，避免窄图截断。搭配 `.png` 可避免照片区域的重采样和 JPEG 重编码。

## 相机与图片格式

工具根据照片 EXIF 中的厂商和型号信息自动匹配品牌 Logo，并读取拍摄参数。当前附带 Logo 和匹配规则的品牌有：

| 相机品牌 | 手机品牌 |
| --- | --- |
| Canon、Nikon、Sony、Fujifilm | Apple、Honor、Samsung、OnePlus |
| Leica、Hasselblad、Ricoh、Panasonic Lumix | OPPO、vivo、Xiaomi |
| Olympus / OM System（使用 Olympus 标志） | |

品牌匹配不代表所有机型都经过验证。没有 EXIF、未匹配到品牌或缺少 Logo 文件时，会跳过品牌标志，仍可按设置显示签名。

支持 JPEG、PNG、WebP；HEIC / HEIF 通过 `pillow-heif` 读取。RAW 显影及 TIFF 处理已移除；RAW、`.tif`、`.tiff` 或改名后的 TIFF 输入会明确报错，请先在照片编辑软件中导出 SDR PNG 或 JPEG。Logo 和签名素材也不支持 TIFF。

品牌规则位于 [assets/brands.json](../assets/brands.json)。添加品牌 Logo、更换签名和指定资源目录的方法见 [定制说明](customization.md)。

## 使用限制与排错

- **地点查询**：默认开启。照片有 GPS 时会将经纬度发送给 Nominatim（OpenStreetMap）查询地名；照片文件本身在本地处理。可用 `--include-gps-location false` 关闭。联网查询与导出 GPS 元数据是两个独立选项。多次查询共用超时预算；后续查询失败时保留已查到的地名，仍可导出。
- **多图排版**：`video` 自动降低照片高度以容纳照片和两侧水印；如果字号或间距本身已占满画布，会提示减小参数或切换 `adaptive`。日期和横线保留指定字号及长度，窄图下仍需检查相邻日期是否拥挤。为保证整数像素上的等间距，video 部分照片宽度会在等比取整结果上增加 1px，不裁切内容。adaptive 自定义高度过大、使 1.8 倍上留白不足以容纳标记时，会提示降低高度或减小字号。参数、地点、日期或签名超出画布上下边界时，会明确报错并提示调整，避免悄悄截断内容。
- **超长图片**：`adaptive` 不设布局宽度或张数上限，但实际受内存、图片格式及查看软件能力影响。JPEG 编码器单边最多支持 65,500px，超过时请使用 `-o 长图.png`。高精度路径逐张解码并释放原图，但最终画布和当前照片仍需要内存；大批量照片建议用 `--batch` 分别导出。
- **拍摄参数**：焦距优先显示 EXIF 中有效的 35mm 等效焦距；缺失、为 0 或无效时显示实际焦距，两者都无效时省略。快门在倒数表示误差不超过 0.1% 时显示为 `1/Ns`，否则保留秒数，例如 `0.8s`、`0.4s`、`1.25s`。
- **拍摄日期**：水印仅使用有效的 EXIF `DateTimeOriginal`，按照片记录的拍摄时间显示到秒，例如 `Wed, 04 Aug 2021 13:23:39`。不显示小数秒和 `+08:00` 等时区后缀，也不转换到电脑当前时区。拍摄时间缺失或无效时不显示日期，不回退到数字化、修改或当前时间。导出 EXIF 的时区与亚秒字段仍按元数据保留策略处理。
- **元数据**：单图保留筛选后的 EXIF 拍摄信息、作者、版权、DPI；从 XMP/IPTC 中保留标题、描述、关键词、作者、版权和评级。旧方向、尺寸、缩略图、MakerNote、设备序列号不照搬。多图只保留所有来源一致的作者、版权及筛选后的共同 XMP，不指定单一相机、日期或位置。`--metadata none` 删除所有非色彩元数据；`--preserve-gps true` 仅在 safe 策略下保留单图的 EXIF GPS。
- **运行环境**：若 Finder 提示缺少依赖，可在终端运行 `python3 -c "import sys; print(sys.executable)"` 查看 Python 路径，并通过 `WATERMARK_PYTHON_BIN` 指定它。字体默认从系统查找，也可通过 `--font`、`--location-font` 指定。

## 运行速度

程序缓存完成色彩转换及缩放的 Logo 和签名图片，Finder 批处理使用单个 Python 进程。合成时先读取尺寸、色彩和元数据，再逐张解码原图；元数据复用于最终导出。16 位 PNG 改用原生解码，并保留低位精度和透明度。

本机 macOS / Python 3.14.2 的结果如下，比较对象为本次审查前后的 2.0.0 工作区，优化前已包含上一轮的 8 位 PNG 解码加速：

| 样图场景 | 优化前中位数 | 优化后缓存建立后的中位数 | 优化后首次处理 |
| --- | --- | --- | --- |
| `phone1.jpg` 单图 | 1.15 秒 | 0.94 秒 | 1.03 秒 |
| `phone2.jpg` 单图 | 1.89 秒 | 0.57 秒 | 1.81 秒 |
| `phone2.jpg` + `vertical1.jpg` + `vertical2.jpg` 合成 | 3.80 秒 | 1.26 秒 | 3.79 秒 |

每个场景使用独立空缓存，先记录首次调用，再运行三次取中位数。测量为默认 video 4K、JPEG 100%、4:4:4、保留色域，关闭 GPS 查询及日志，计时完整 `make_canvas` 调用，包含保存文件、不含进程启动。保留真实拍摄日期，三组 JPEG 解码后的像素与优化前全部一致。首次处理仍需建立缓存，主要加速体现在重复运行和批处理中。

1800 × 1200 的合成 16 位 RGB PNG（Up 行过滤）解码中位数从 0.808 秒降至 0.029 秒，原始像素 SHA-256 一致；这是解码阶段的测试，不代表所有格式或完整导出的加速倍数。三图独立进程的单次内存对比中，峰值驻留内存约从 855 MiB 降至 711 MiB（已有素材缓存）；此值会随系统、分配器和照片变化，并非内存上限。

可用以下命令重新测量当前版本；成片及计时 JSON 保存到指定目录：

```bash
python3 scripts/benchmark_render.py --output-dir output/benchmark --iterations 3
```

该脚本用临时素材缓存测量首次和后续运行，不清理日常使用的缓存。

### 缓存位置

macOS 默认目录为 `~/Library/Caches/watermark-tool/assets`。缓存只包含处理好的位图 Logo 和签名，不保存照片或 GPS 坐标。源素材内容、目标尺寸或处理版本变化后会重新生成；SVG 可能引用外部文件，因此每次重新处理。损坏或不可写的缓存不会阻止导出。

可删除该目录清理磁盘缓存，下次运行会重建；使用环境变量可指定目录或关闭缓存：

```bash
WATERMARK_CACHE_DIR=/path/to/cache python3 layout.py photo.jpg
WATERMARK_CACHE_DIR=off python3 layout.py photo.jpg
```

GPS 查询结果只在当前进程内复用，默认仍开启联网。多次地点反查共享配置中的超时预算，后续失败会保留已有地名；不需要地点文字时可添加 `--include-gps-location false`。实际耗时还取决于照片尺寸、格式、硬件及网络。

## 色彩处理

默认保留 **4K 布局、JPEG 100%、4:4:4 色度采样**。不设置文件体积目标。JPEG 100% 仍为有损重编码，固定 4K 布局也会缩放照片；它们不保证原始细节和位深全部保留。

`--jpeg-quality 100` 是 JPEG 编码质量的最高档，不是文件大小百分比，也不是相对原图的画质百分比。同样的像素、尺寸和其他编码设置下，质量越高通常体积越大；从 95 提高到 100，体积可能明显增长，但画质提升并非按比例增长。照片内容、尺寸、噪点、色度采样和元数据也会影响体积。

```bash
# 默认：4K / JPEG 100%，保留来源 RGB 色域
python3 layout.py photo.jpg

# 保留原始尺寸、来源色域，使用无损 PNG（高位深来源自动输出 16 位）
python3 layout.py photo.png --output-mode original -o output.png

# 主动选择兼容普通分享软件的 sRGB / 8 位 / SDR 输出
python3 layout.py photo.jpg --color-mode srgb -o share.jpg

# 保留筛选后的元数据及单图 EXIF GPS，但关闭地点联网查询
python3 layout.py photo.jpg --preserve-gps true --include-gps-location false

# 去除非色彩元数据
python3 layout.py photo.jpg --metadata none
```

- **来源色域**：`preserve` 对相同 RGB 配置沿用来源 ICC 或色彩定义；多张 SDR 照片的色域不同时，先用高精度转换到 ProPhoto RGB 再合成，建议以 16 位 PNG 输出。单图无缩放、相同 RGB 定义的 PNG 路径保留解码后的原始 RGB 样本。混合色域涉及数值转换和最终量化，不能称为逐像素无损。
- **查看软件**：广色域 JPEG 必须由支持 ICC 的软件显示；忽略 ICC 的软件可能显示错误。此时可主动使用 `--color-mode srgb` 生成分享版本。
- **高位深**：PNG 直接读取原始整数样本；HEIF 保留原生 10/12 位样本。ICC 转换使用浮点缓冲，缩放完成后才量化到最终输出位深。PNG 高位深输出为 16 位；JPEG 降为 8 位时会提示。不接受 TIFF；保真路径中的 CMYK/Lab 会报错；带有效 ICC 的 CMYK/Lab 可选择 `--color-mode srgb` 转换。
- **色彩标记优先级**：PNG 的有效 cICP 优先于 ICC，再考虑 sRGB、EXIF Adobe RGB、gAMA/cHRM。支持常见 BT.709、BT.2020、Display P3 原色及其 SDR 传递函数。暂不支持的 cICP 窄范围或未知传递函数会明确报错，避免无声误标为 sRGB。完全未标记的 RGB/灰度按 sRGB 解释，无法猜回遗失的原始色域。
- **输入范围**：仅处理 SDR，不提供 HDR 转换、HDR 增益图处理或 HDR 导出。检测到 PQ/HLG 或已知增益图标记的输入会明确报错，请先在照片编辑软件中导出 SDR；不会将 HDR 像素直接误当成 SDR 输出。
- **sRGB 转换**：选择 `--color-mode srgb` 时，将普通 SDR 照片统一转换到 8 位 sRGB，适用于不支持广色域 ICC 的分享环境。
- **透明度**：保真 PNG 保留照片 alpha；JPEG 按画布背景合成并提示。水印素材先转为 sRGB 绘制，再转换到最终照片色域；原照片不会经过用于文字绘制的 8 位画布。
- **失败处理**：损坏或不匹配的 ICC、无法解释的色彩配置会明确报错。先完整编码临时文件再替换成片，失败不会覆盖原图或已有输出。

参考：[Pillow / LittleCMS](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html)、[PNG cICP](https://www.w3.org/TR/png-3/#11cICP)、[RGB 色彩转换](https://www.w3.org/TR/css-color-4/#color-conversion-code)。

## 开发与预览图片

安装开发依赖并运行检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover
python3 -m ruff check .
```

README 预览可用 `python3 scripts/build_readme_previews.py` 重新生成；完整成片保存在 `samples/`，压缩预览保存在 `docs/previews/`。
