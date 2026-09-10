# Watermark Tool

**在 Mac 上，右键就能为照片加水印。**

为照片添加边框、拍摄参数、日期、品牌 Logo 和个人签名。支持 macOS Finder 右键快速操作和终端命令，可单张处理、批量导出或多图拼接。

[下载源码](https://github.com/chilemay-0417/watermark-tool/archive/refs/tags/v2.2.5.zip) · [安装指南](docs/usage.md#安装与首次使用) · [使用指南](docs/usage.md) · [签名与品牌定制](docs/customization.md) · [更新日志](CHANGELOG.md)

## 特色：macOS 右键快速操作

在 Finder 选中照片，通过右键「快速操作」即可处理，日常使用无需打开终端。

| 功能 | 右键操作 | 效果 |
| --- | --- | --- |
| 单张加水印 | 单选 → **添加水印** | 生成一张成片 |
| 多图拼接 | 多选 → **添加水印** | 合成为一张成片 |
| 批量加水印 | 多选 → **批量添加水印** | 每张照片分别导出 |

- **自动识别**：读取拍摄参数、日期和相机品牌，匹配对应 Logo。
- **自由定制**：更换个人签名、品牌 Logo，调整布局和文字样式。
- **保留原图**：成片保存到原图目录，重名自动编号；合成时使用第一张输入照片的目录。

## 终端命令

完成 [安装](docs/usage.md#安装与首次使用) 并重新打开终端后，也可用一条命令加水印：

```bash
watermark-tool photo.jpg
```

将 `photo.jpg` 换成照片路径，或直接把照片拖入终端。成片保存在原图目录，无需进入工具文件夹。批量处理和 PNG 导出见 [命令行用法](docs/usage.md#命令与参数)，全部参数可用 `watermark-tool --help` 查看。

## 布局与效果

默认使用 `adaptive`，边框贴合照片。以下样张已压缩，仅展示排版效果，点击可查看大图。

### video：4K 视频素材

生成 **3840 × 2160（16:9）** 图片，供剪辑软件制作视频。支持 1～3 张照片，空间不足时自动降低照片高度。

**单张照片**

<a href="samples/phone1_watermark.jpg"><img src="samples/phone1_watermark.jpg" alt="video 模式：单张照片，左右留白相等" width="720"></a>

**两张竖向照片合成**

<a href="samples/vertical1_vertical2_watermark.jpg"><img src="samples/vertical1_vertical2_watermark.jpg" alt="video 模式：两张竖向照片，左右留白与图间距相等" width="720"></a>

**多张照片：自动降低高度，避免 Logo 与参数重叠**

<a href="samples/phone2_vertical1_vertical2_watermark.jpg"><img src="samples/phone2_vertical1_vertical2_watermark.jpg" alt="video 模式：三张照片自动降低高度，避免 Logo 与相邻参数重叠" width="720"></a>

### adaptive：让边框贴合照片

画布宽度随照片调整，适合单图分享和多图长拼接。横竖照片可混排，实际大小受内存和图片格式限制。

**单张横向照片**

<a href="samples/horizontal1_watermark.jpg"><img src="samples/horizontal1_watermark.jpg" alt="adaptive 模式：单张横向照片，边框贴合照片" width="640"></a>

**单张竖向照片**

<a href="samples/phone2_watermark.jpg"><img src="samples/phone2_watermark.jpg" alt="adaptive 模式：单张竖向照片与紧凑边框" width="360"></a>

**多张照片自由拼接**

<a href="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg"><img src="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg" alt="adaptive 模式：五张不同设备、不同方向的照片拼接成长图" width="960"></a>

### original：保留照片原始尺寸

保留旋正后的照片原始像素尺寸，画布随内容扩展。搭配 PNG 导出可避免缩放和 JPEG 重编码，适合保留细节。

## 使用须知

- 支持 JPEG、PNG、WebP、HEIC / HEIF，导出 JPEG 或 PNG。RAW、TIFF、HDR 请先转换为 SDR PNG / JPEG。
- JPEG 默认质量为 100%，仍是有损格式；需要保留细节可用原尺寸 PNG。
- 地点查询默认开启，有坐标时会发送给 Nominatim 查询地名，本机缓存 30 天。可在配置中关闭；成片默认不保留 EXIF GPS。

代码采用 [MIT License](LICENSE)。样张、个人签名和品牌 Logo 的授权需分别确认。问题反馈见 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues)，维护者见 [开发说明](docs/development.md)。
