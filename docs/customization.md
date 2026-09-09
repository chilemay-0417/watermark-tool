# 签名与品牌定制

[返回 README](../README.md) · [使用指南](usage.md)

## 替换签名

默认签名文件是：

```text
assets/signature_400.jpg
```

保持文件名不变，直接替换这个文件即可。

如果想改签名文件名，修改 [config.py](../src/watermark_tool/config.py)：

```python
SIGNATURE_FILE = "signature_400.jpg"
```

也可以在命令行临时隐藏签名图片和替代文字：

```bash
python3 layout.py photo.jpg --show-signature false --signature-text ""
```

关闭签名图片后，如果想用一行文字替代签名：

```bash
python3 layout.py photo.jpg --show-signature false --signature-text "Shot by Chile"
```

也可以调整替代文字字号：

```bash
python3 layout.py photo.jpg --show-signature false --signature-text "Shot by Chile" --signature-font-size 42
```

替代文字会先放到一块高度为 `LOGO_HEIGHT`、宽度随文字长度变化的透明画布中居中，再整体旋转到品牌 logo 上方。英文默认和日期使用同一字族，默认是 Courier New Regular；如果文字包含中文，默认使用黑体-简（Heiti SC）避免缺字。签名到照片右侧、签名到 logo 的距离都按这块透明画布的边缘计算。

## 添加新相机 Logo

默认品牌规则写在：

```text
assets/brands.json
```

当前随仓库提供 logo 文件的品牌：

```text
Apple / Canon / Fujifilm / Hasselblad / Honor / Leica / Lumix / Nikon /
Olympus / OnePlus / OPPO / Ricoh / Samsung / Sony / Vivo / Xiaomi
```

`brands.json` 里已经预置了更多常见品牌的匹配规则；如果对应 logo 文件还不存在，
工具会自动跳过品牌 logo，只保留签名。添加新品牌 logo 时按下面步骤扩展。

1. 把 logo 图片放进 `assets/`。

例如：

```text
assets/Canon.png
```

2. 在 `assets/brands.json` 的 `brands` 列表中添加规则：

```json
{
  "display_name": "Canon",
  "logo": "Canon.png",
  "keywords": ["canon", "eos", "powershot"]
}
```

`display_name` 方便阅读；`logo` 是 `assets/` 里的文件名；`keywords` 会和照片 EXIF 的
Make / Model 做不区分大小写的包含匹配。

logo 原图不需要是固定尺寸，PNG / JPG / SVG 都可以；导出时会自动缩放到统一高度。
如果使用 SVG，请确保安装了 CairoSVG 依赖。

之后照片 EXIF 的 Make 或 Model 包含这些关键词时，就会自动使用 Canon logo。

如果你想把品牌规则文件放在其他位置，可以设置：

```bash
export WATERMARK_BRANDS_FILE="/path/to/brands.json"
```

## 多张照片合成时 Logo 的规则

多图合成时，品牌 logo 和签名的规则是：

- 单张照片按 EXIF 识别品牌；识别不到时只放签名。
- 多张照片拍摄设备完全一致时，只在最右侧照片添加品牌 logo 和签名。
- 多张照片拍摄设备不一致时，每张可识别照片都添加自己的品牌 logo。
- 签名永远只添加在最右侧照片的品牌 logo 上方。

这样可以避免多图合成时因为不同设备混选导致贴错 logo，同时保持签名只出现一次。

## 资源目录

默认资源目录是项目里的 `assets/`。如果你的 logo 和签名放在其他位置，可以设置：

```bash
export WATERMARK_ASSETS_DIR="/path/to/assets"
```

这个目录里至少需要包含签名文件和 `brands.json`；品牌 logo 是否存在取决于照片 EXIF 能否匹配到对应品牌。
