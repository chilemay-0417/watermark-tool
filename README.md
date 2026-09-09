# Watermark Tool

为照片添加边框、拍摄参数、日期、品牌 Logo 和个人签名，支持单张处理、批量导出和多图拼接。可通过命令行使用，也可配置 macOS Finder 右键快速操作。

[下载最新版本](https://github.com/chilemay-0417/watermark-tool/releases/latest) · [使用指南](docs/usage.md) · [签名与品牌定制](docs/customization.md) · [更新日志](CHANGELOG.md)

## 两种模式

### video：为照片制作视频

生成 **3840 × 2160（16:9）** 图片，供剪辑软件制作视频。支持 1～3 张照片，左右留白与照片间距相等；水印空间不足时，自动降低照片高度。

**单张照片**

<a href="samples/phone1_watermark.jpg"><img src="docs/previews/phone1_watermark.jpg" alt="video 模式：单张照片，左右留白相等" width="720"></a>

**两张竖向照片合成**

<a href="samples/vertical1_vertical2_watermark.jpg"><img src="docs/previews/vertical1_vertical2_watermark.jpg" alt="video 模式：两张竖向照片，左右留白与图间距相等" width="720"></a>

**多张照片：自动降低高度，避免 Logo 与参数重叠**

<a href="samples/phone2_vertical1_vertical2_watermark.jpg"><img src="docs/previews/phone2_vertical1_vertical2_watermark.jpg" alt="video 模式：三张照片自动降低高度，避免 Logo 与相邻参数重叠" width="720"></a>

### adaptive：让边框贴合照片

画布宽度随照片调整，适合单图分享和多图长拼接。横向、竖向照片可以混排，程序不限制拼接张数或宽度，实际导出受内存和图片格式限制。

**单张横向照片**

<a href="samples/horizontal1_watermark.jpg"><img src="docs/previews/horizontal1_watermark.jpg" alt="adaptive 模式：单张横向照片，边框贴合照片" width="640"></a>

**单张竖向照片**

<a href="samples/phone2_watermark.jpg"><img src="docs/previews/phone2_watermark.jpg" alt="adaptive 模式：单张竖向照片与紧凑边框" width="360"></a>

**多张照片自由拼接**

<a href="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg"><img src="docs/previews/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg" alt="adaptive 模式：五张不同设备、不同方向的照片拼接成长图" width="960"></a>

以上为压缩预览，点击图片可查看完整成片。默认模式为 `adaptive`。

## 安装与使用

需要 **Python 3.10+**。下载并解压项目，在终端中运行（将路径替换为实际项目目录）：

```bash
cd /path/to/watermark_tool
python3 -m pip install -r requirements.txt
```

为单张照片加水印：

```bash
python3 layout.py samples/horizontal1.jpg --include-gps-location false
```

将多张照片合成一张图片，用 `--output-mode` 选择模式：

```bash
python3 layout.py samples/vertical1.jpg samples/vertical2.jpg --output-mode video --include-gps-location false
```

默认在第一张照片的目录保存 `原文件名_watermark.jpg`，合成时会连接各照片文件名；重名时自动追加序号。可用 `-o output.png` 指定输出路径及格式。

**macOS 右键使用**：按 [Finder 配置步骤](docs/usage.md#在-finder-中右键使用) 添加「照片加水印」和「合成水印照片」两个快速操作，即可在 Finder 中选中照片后右键运行。

**调整默认设置**：修改 [config.py](src/watermark_tool/config.py) 中的 `OUTPUT_MODE` 等配置；更多命令与参数见 [使用指南](docs/usage.md)。

## 使用须知

- 焦距优先显示 **35mm 等效焦距**，缺失时显示实际焦距；照片没有拍摄日期时会使用处理时间。
- 地点查询默认开启，会将照片中的 GPS 经纬度发送给 Nominatim 查询地名。以上命令用 `--include-gps-location false` 关闭查询；Finder 中可将配置项 `INCLUDE_GPS_LOCATION` 改为 `False`。
- 支持 JPEG、PNG、TIFF、WebP，以及通过解码库读取 HEIC / HEIF 和 RAW。导出为 JPEG 或 PNG，不保留原始 EXIF；未进行 ICC 色彩管理。详细兼容性和排版限制见 [使用指南](docs/usage.md#使用限制与排错)。

## 许可

代码采用 [MIT License](LICENSE)。照片样张、个人签名和第三方品牌 Logo 的授权需分别确认。
