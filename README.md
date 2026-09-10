# Watermark Tool

**版本：2.2.0**

为照片添加边框、拍摄参数、日期、品牌 Logo 和个人签名，支持单张处理、批量导出和多图拼接。可通过命令行使用，也可双击安装 macOS Finder 右键快速操作。

[下载 2.2.0](https://github.com/chilemay-0417/watermark-tool/archive/refs/tags/v2.2.0.zip) · [使用指南](docs/usage.md) · [签名与品牌定制](docs/customization.md) · [开发说明](docs/development.md) · [更新日志](CHANGELOG.md)

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

电脑需已有 **Python 3.10+**。下载并解压项目，保留完整文件夹，将它放在固定位置，例如 `~/Pictures/watermark_tool`。

1. 双击 **[右键操作安装.command](右键操作安装.command)**，安装器会准备项目环境和依赖。
2. 等待终端显示“安装完成”，按回车关闭窗口。
3. 在 Finder 选中一张或多张照片 → 右键 → **快速操作 → 添加水印**。

单选处理一张，多选则逐张处理。成片分别保存在原图目录，命名为 `原文件名_watermark.jpg`；重名时追加序号，原图保留。无需打开或配置 Automator。

首次安装依赖需要联网；缺少 Python 或 Cairo 系统库时，按 [环境排错说明](docs/usage.md#环境要求与排错) 补齐后重试。安装器会备份并移除本工具可识别的旧入口，项目移动后重新双击安装即可。卸载时双击 **[右键操作卸载.command](右键操作卸载.command)**。

### 命令行：合成或自定义导出

完成安装后，在项目目录运行。例如将两张照片合成为一张 4K 图片：

```bash
.venv/bin/python layout.py samples/vertical1.jpg samples/vertical2.jpg --output-mode video
```

保留原始尺寸并导出无损 PNG：

```bash
.venv/bin/python layout.py photo.png --output-mode original -o output.png
```

命令行多张输入默认合成一张，添加 `--batch` 才会逐张导出。完整命令与参数见 [使用指南](docs/usage.md#命令与参数)。右键操作的长期默认设置在 [config.py](src/watermark_tool/config.py) 中修改，签名和 Logo 的调整见 [定制说明](docs/customization.md)。

## 使用须知

- 焦距优先显示 **35mm 等效焦距**，缺失时显示实际焦距；日期仅显示 EXIF 拍摄时间，精确到秒，不显示小数秒和时区；拍摄时间缺失或无效时不显示日期。
- GPS 地点查询默认开启，有坐标时会发送经纬度给 Nominatim 查询地名。成功地点查询会在本机缓存 30 天，缓存设置及清理方式见 [使用指南](docs/usage.md#缓存与运行速度)。可用 `--include-gps-location false` 关闭地点查询；`--preserve-gps true` 单独控制单图成片中的 GPS 字段，GPS 字段保留默认关闭。
- 仅处理 SDR 图片，不支持 RAW 和 TIFF；请先在照片编辑软件中转换为 SDR PNG 或 JPEG。默认保留来源 RGB 色域，混合 SDR 色域使用 ProPhoto RGB；广色域成片需用支持 ICC 的软件查看，分享可选 `--color-mode srgb`。
- 默认保留筛选后的拍摄参数、作者、版权和单图 DPI，重建尺寸及方向，移除旧缩略图、MakerNote、设备序列号；可用 `--metadata none` 删除非色彩元数据。详细策略见 [使用指南](docs/usage.md#色彩与元数据)。
- JPEG 100% 仍为有损编码；PNG 无损编码不代表缩放或色彩转换没有损失。大尺寸、多图合成会占用较多内存。

## 支持与反馈

安装、Finder 配置及常见问题见 [使用指南](docs/usage.md)，更换签名和 Logo 见 [定制说明](docs/customization.md)，代码结构、验证与性能测量见 [开发说明](docs/development.md)。遇到问题可提交 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues)，附上系统、Python 版本、运行命令或操作步骤，以及完整报错。

## 许可

代码采用 [MIT License](LICENSE)。照片样张、个人签名和第三方品牌 Logo 的授权需分别确认。
