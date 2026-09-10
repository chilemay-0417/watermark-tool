# 签名与品牌定制

[返回 README](../README.md) · [使用指南](usage.md)

右键操作与 `watermark-tool` 命令共用项目中的配置、签名和 Logo。修改并保存后，下次运行即生效，无需重新安装。

## 更换或隐藏签名

用自己的签名图片替换 `assets/signature_400.jpg` 即可。推荐使用透明 PNG；换了文件名时，在 [config.py](../src/watermark_tool/config.py) 中同步修改：

```python
SIGNATURE_FILE = "my_signature.png"
```

也可以在同一文件中改用文字签名，或完全隐藏签名：

```python
SHOW_SIGNATURE = False
SIGNATURE_TEXT = "Shot by You"  # 改为 "" 即可隐藏签名
```

文字签名默认使用日期字体，含中文时使用黑体-简，整体旋转后放在照片右侧。也可在终端临时更改文字或字号，仅对这次运行生效：

```bash
watermark-tool photo.jpg --show-signature false --signature-text "Shot by You" --signature-font-size 42
```

## 更换或添加品牌 Logo

更换已有 Logo：直接替换 `assets/` 中对应的图片，保持文件名不变。

添加新品牌：

1. 将 Logo 放进 `assets/`，推荐高度至少 400 像素的透明 PNG，也支持 JPG / WebP。
2. 用文本编辑器打开 `assets/brands.json`，在 `brands` 列表中添加规则。例如：

```json
{
  "display_name": "Canon",
  "logo": "Canon.png",
  "keywords": ["canon", "eos", "powershot"]
}
```

已有 Canon 规则，修改时直接编辑该项即可。新加品牌时替换名称、文件名和关键词；相邻规则之间用逗号分隔，最后一项后不加逗号。

`logo` 必须与图片文件名一致。`keywords` 匹配照片拍摄信息（EXIF）中的厂商或型号，不区分大小写。匹配不到品牌或缺少图片时跳过 Logo，不影响签名。

Logo 会自动缩放到统一高度。SVG 需要 [额外依赖](usage.md#自定义-svg可选)，新手直接使用 PNG 即可。

## 多图合成的显示规则

- 同一设备拍摄的照片：只在最右侧显示 Logo。
- 不同设备拍摄的照片：每张照片分别匹配 Logo。
- 签名只显示一次，位于最右侧照片旁；有 Logo 时放在 Logo 上方。

「批量添加水印」逐张导出，每张照片独立显示 Logo 和签名。

项目移动或改名后，按 [使用指南](usage.md#升级移动与卸载) 重新双击安装，让右键和终端指向新位置。

## 使用其他素材目录（进阶）

在终端中设置后，适用于从该终端启动的命令：

```bash
export WATERMARK_ASSETS_DIR="/完整路径/assets"
export WATERMARK_BRANDS_FILE="/完整路径/brands.json"
```

第一个变量指定素材目录，第二个单独指定品牌规则文件。未指定第二个变量时，从素材目录读取 `brands.json`。
