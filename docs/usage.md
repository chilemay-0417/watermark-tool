# 使用指南

[返回 README](../README.md) · [签名与品牌定制](customization.md) · [更新日志](../CHANGELOG.md)

以下命令均在项目目录中运行；安装步骤见 [README](../README.md#安装与使用)。需要使用项目记录的依赖版本时，可将安装命令中的 `requirements.txt` 换成 `requirements.lock`。

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

脚本会自动寻找已安装所需依赖的 Python。如需指定 Python，可在脚本调用前添加 `export WATERMARK_PYTHON_BIN="/path/to/python3"`，填入安装依赖时使用的 Python 路径。

右键操作使用 [config.py](../src/watermark_tool/config.py) 中的默认设置。要切换模式，修改其中的 `OUTPUT_MODE = "adaptive"` 或 `OUTPUT_MODE = "video"`；要关闭地点联网查询，将 `INCLUDE_GPS_LOCATION` 改为 `False`。两个 Shell 脚本接收照片路径，临时调整其他参数请使用下方命令行入口。

## 命令与参数

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

日期、字体、线条和间距等更多参数可运行 `python3 layout.py --help` 查看。长期使用的默认设置可在 [config.py](../src/watermark_tool/config.py) 中修改。

## 排版规则

- **video**：固定 3840 × 2160 画布，支持 1～3 张照片，左右留白与图间距相等。原始间距不足以容纳相邻水印时，自动降低统一照片高度，直到间距至少达到横向占用之和 `a` 的 1.5 倍；日期和横线保持指定字号、长度和间距。
- **adaptive**：画布宽度随照片增长，不设张数或布局宽度上限。多图时，照片间距、左留白和右留白均为上留白的 1.8 倍，取整到整数像素；单图使用紧凑边框。

## 相机与图片格式

工具根据照片 EXIF 中的厂商和型号信息自动匹配品牌 Logo，并读取拍摄参数。当前附带 Logo 和匹配规则的品牌有：

| 相机品牌 | 手机品牌 |
| --- | --- |
| Canon、Nikon、Sony、Fujifilm | Apple、Honor、Samsung、OnePlus |
| Leica、Hasselblad、Ricoh、Panasonic Lumix | OPPO、vivo、Xiaomi |
| Olympus / OM System（使用 Olympus 标志） | |

品牌匹配不代表所有机型都经过验证。没有 EXIF、未匹配到品牌或缺少 Logo 文件时，会跳过品牌标志，仍可按设置显示签名。

支持 JPEG、PNG、TIFF、WebP；HEIC / HEIF 通过 `pillow-heif` 读取，NEF、ARW、CR2、CR3、RAF、DNG 等 RAW 格式通过 `rawpy` 读取。实际 RAW 兼容性取决于相机型号和解码库，拍摄参数不一定能够完整读取。

品牌规则位于 [assets/brands.json](../assets/brands.json)。添加品牌 Logo、更换签名和指定资源目录的方法见 [定制说明](customization.md)。

## 使用限制与排错

- **地点查询**：默认开启。照片有 GPS 时，经纬度会发送给 Nominatim（OpenStreetMap）查询地名；照片文件本身在本地处理。关闭方式为 `--include-gps-location false`，或修改默认配置。查询失败或超时时，图片仍可继续导出。
- **多图排版**：`video` 自动降低照片高度以容纳照片和两侧水印；如果字号或间距本身已占满画布，会提示减小参数或切换 `adaptive`。日期和横线保留指定字号及长度，窄图下仍需检查相邻日期是否拥挤。为保证整数像素上的等间距，video 部分照片宽度会在等比取整结果上增加 1px，不裁切内容。adaptive 自定义高度过大、使 1.8 倍上留白不足以容纳标记时，会提示降低高度或减小字号。参数、地点、日期或签名超出画布上下边界时，会明确报错并提示调整，避免悄悄截断内容。
- **超长图片**：`adaptive` 不设布局宽度或张数上限，但实际受内存、图片格式及查看软件能力影响。JPEG 编码器单边最多支持 65,500px，超过时请使用 `-o 长图.png`。程序会逐张解码并释放照片，但最终画布仍需要内存。
- **拍摄参数**：焦距优先显示 EXIF 中有效的 35mm 等效焦距；缺失、为 0 或无效时显示实际焦距，两者都无效时省略。快门在倒数表示误差不超过 0.1% 时显示为 `1/Ns`，否则保留秒数，例如 `0.8s`、`0.4s`、`1.25s`。
- **拍摄日期**：缺失日期时，当前版本会使用处理时的日期和时间。需要准确记录时，请核对成片文字。
- **色彩与元数据**：当前导出不保留原始 EXIF，也未进行 ICC 色彩管理，广色域照片可能出现色彩差异。RAW 会先转换为 8-bit RGB，再进入排版流程。
- **运行环境**：若 Finder 提示缺少依赖，可在终端运行 `python3 -c "import sys; print(sys.executable)"` 查看 Python 路径，并通过 `WATERMARK_PYTHON_BIN` 指定它。字体默认从系统查找，也可通过 `--font`、`--location-font` 指定。

## 开发与预览图片

安装开发依赖并运行检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover
python3 -m ruff check .
```

README 预览可用 `python3 scripts/build_readme_previews.py` 重新生成；完整成片保存在 `samples/`，压缩预览保存在 `docs/previews/`。
