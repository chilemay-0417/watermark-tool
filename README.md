# Watermark Tool

**版本：2.2.3**

为照片添加边框、拍摄参数、日期、品牌 Logo 和个人签名，支持单张处理、批量导出和多图拼接。可通过命令行使用，也可双击安装 macOS Finder 右键快速操作。

[下载 2.2.3](https://github.com/chilemay-0417/watermark-tool/archive/refs/tags/v2.2.3.zip) · [使用指南](docs/usage.md) · [签名与品牌定制](docs/customization.md) · [开发说明](docs/development.md) · [更新日志](CHANGELOG.md)

## 功能与效果

- 自动读取拍摄参数、日期和相机品牌，添加边框、Logo 与个人签名。
- 支持单张处理、逐张批量导出和多图合成，提供三种布局模式。
- 支持 JPEG、PNG、WebP、HEIC / HEIF 输入，导出 JPEG 或 PNG；支持来源色域、16 位 PNG 及可选的元数据保留。

### video：为照片制作视频

生成 **3840 × 2160（16:9）** 图片，供剪辑软件制作视频。支持 1～3 张照片，左右留白与照片间距相等；水印空间不足时，自动降低照片高度。

**单张照片**

<a href="samples/phone1_watermark.jpg"><img src="samples/phone1_watermark.jpg" alt="video 模式：单张照片，左右留白相等" width="720"></a>

**两张竖向照片合成**

<a href="samples/vertical1_vertical2_watermark.jpg"><img src="samples/vertical1_vertical2_watermark.jpg" alt="video 模式：两张竖向照片，左右留白与图间距相等" width="720"></a>

**多张照片：自动降低高度，避免 Logo 与参数重叠**

<a href="samples/phone2_vertical1_vertical2_watermark.jpg"><img src="samples/phone2_vertical1_vertical2_watermark.jpg" alt="video 模式：三张照片自动降低高度，避免 Logo 与相邻参数重叠" width="720"></a>

### adaptive：让边框贴合照片

画布宽度随照片调整，适合单图分享和多图长拼接。横向、竖向照片可以混排，程序不限制拼接张数或宽度，实际导出受内存和图片格式限制。

**单张横向照片**

<a href="samples/horizontal1_watermark.jpg"><img src="samples/horizontal1_watermark.jpg" alt="adaptive 模式：单张横向照片，边框贴合照片" width="640"></a>

**单张竖向照片**

<a href="samples/phone2_watermark.jpg"><img src="samples/phone2_watermark.jpg" alt="adaptive 模式：单张竖向照片与紧凑边框" width="360"></a>

**多张照片自由拼接**

<a href="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg"><img src="samples/horizontal1_phone1_phone2_vertical1_vertical2_watermark.jpg" alt="adaptive 模式：五张不同设备、不同方向的照片拼接成长图" width="960"></a>

以上图片及 `samples/` 中的照片均已压缩，仅供效果展示，点击可查看展示大图。默认模式为 `adaptive`，以 JPEG 100% 质量、4:4:4 色度采样导出；固定 4K 画布请指定 `--output-mode video`。

### original：保留照片原始尺寸

保留每张照片旋正后的原始像素尺寸，顶部对齐，画布随照片和水印扩展。使用 `--output-mode original -o output.png` 可避免照片缩放和 JPEG 重编码；适合保留细节，输出体积也更大。

## 安装与使用

### macOS：双击安装右键操作

**推荐 Python + pip**：安装 [Python 3.10+](https://www.python.org/downloads/macos/)，将完整项目解压到「图片」等固定位置。安装器会通过 pip 自动安装依赖，使用内置 PNG Logo 无需安装 Homebrew、Conda 或 Cairo。详细步骤见 [使用指南](docs/usage.md#方案一python--pip)。

1. 双击 **[右键操作安装.command](右键操作安装.command)**，安装器会准备项目环境和依赖。
2. 等待终端显示“安装完成”，按回车关闭窗口。
3. 在 Finder 选中照片 → 右键 → **快速操作**，按用途选择：

| 功能 | 选图与右键操作 | 输出 |
| --- | --- | --- |
| 单张加水印 | 单选 → **添加水印** | 一张成片 |
| 批量加水印 | 多选 → **批量添加水印** | 每张各自生成成片 |
| 多图合成 | 多选 → **添加水印** | 多张拼接为一张成片 |

成片保存在原图目录：合成时使用第一张输入照片的目录。文件名以 `_watermark.jpg` 结尾，重名自动追加序号，原图保留。

双击 **[右键操作卸载.command](右键操作卸载.command)** 可卸载两个入口。首次安装依赖需要联网；环境排错、菜单排序及项目移动后的设置见 [使用指南](docs/usage.md)。

### 更多设置

右键操作使用 [config.py](src/watermark_tool/config.py) 中的默认设置，签名和 Logo 的调整见 [定制说明](docs/customization.md)。需要临时选择 PNG、其他布局或导出参数时，再参考 [进阶命令行用法](docs/usage.md#命令与参数)；日常右键使用无需打开终端。

## 使用须知

- 仅处理 SDR 图片，不支持 RAW 和 TIFF。默认保留来源 RGB 色域；分享时可选 `--color-mode srgb`。
- GPS 地点查询默认开启，有坐标时会发送给 Nominatim 查询地名，并在本机缓存 30 天。可用 `--include-gps-location false` 关闭；成片默认不保留 GPS 字段。
- JPEG 即使设为 100% 仍是有损编码；PNG 可避免 JPEG 重编码，但缩放和色彩转换仍可能改变像素。大尺寸、多图合成会占用较多内存。

参数、色彩和元数据策略见 [使用指南](docs/usage.md)。遇到问题可提交 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues)，附上系统、Python 版本、复现步骤及完整报错。

## 许可

代码采用 [MIT License](LICENSE)。照片样张、个人签名和第三方品牌 Logo 的授权需分别确认。
