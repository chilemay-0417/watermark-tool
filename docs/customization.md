# 背景颜色、签名与品牌定制

[返回 README](../README.md) · [使用指南](usage.md)

右键操作与 `watermark-tool` 命令共用项目中的配置、签名和 Logo。修改并保存后，下次运行即生效，无需重新安装。

## 背景与水印颜色

打开 [config.py](../src/watermark_tool/config.py)，颜色选项在 `OUTPUT_MODE` 下方。
设置适用于 `video`、`adaptive`、`original` 三种布局。内置 12 组搭配，编号与 [README 样张](../README.md#12-组精选配色)一致。
默认启用 01「极简瓷白」。在配置中找到使用 `COLOR_PRESETS` 的赋值行，修改引号中的编号即可切换；如果这一行开头有 `#`，先去掉。以下示例选用 09「蓝钛暮色」：

```python
BACKGROUND_COLOR, WATERMARK_COLOR = COLOR_PRESETS["09"]
```

要使用手动配色，给这一行加上 `#`，再修改下方「手动配色」区域中的两个颜色值。保留该区域的 `if` 条件和缩进；启用预设时，这一区域会自动跳过。
默认使用 video 版式与配色 01；以下是关闭预设后手动设置白底黑字的示例：

```python
BACKGROUND_COLOR = "white"  # 背景颜色
WATERMARK_COLOR = "black"   # 文字、横线、签名的统一颜色
LINE_COLOR = None           # 横线
DATE_COLOR = None           # 日期
INFO_COLOR = None           # 拍摄参数和地点
SIGNATURE_COLOR = None      # 图片签名和文字签名
```

四个单项设为 `None` 时跟随 `WATERMARK_COLOR`，填写颜色则单独覆盖。
例如 `LINE_COLOR = "gold"` 只将横线改为金色。Logo 始终保持原色。

背景和水印分别设置，不会自动反色。深灰底、白色水印只需修改这两行：

```python
BACKGROUND_COLOR = "rgb(40, 40, 40)"
WATERMARK_COLOR = "white"
```

所有颜色选项都支持以下写法，RGB 三个通道均为 **0–255 整数**：

| 写法 | 示例 |
| --- | --- |
| [Matplotlib CSS4 色卡](https://matplotlib.org/stable/gallery/color/named_colors.html#css-colors)中的名称，不区分大小写 | `"midnightblue"`、`"dimgray"` |
| RGB 字符串 | `"rgb(40, 40, 40)"` |
| Python RGB 元组 | `(40, 40, 40)` |
| 十六进制 | `"#282828"`、`"#abc"` |

无需安装 Matplotlib；不支持 `tab:`、`xkcd:`、渐变色图、RGBA 或 0–1 浮点 RGB。
临时覆盖颜色见 [命令行用法](usage.md#命令与参数)，不会修改默认配置。
单项参数为 `--line-color`、`--date-color`、`--info-color`、`--signature-color`。

## 更换或隐藏签名

随附的 [signature_400.jpg](../assets/signature_400.jpg) 是 **1728 × 400 像素的黑字白底 JPEG**，没有透明通道。
对白底不透明图片染色时，程序会把纯白部分转成透明、灰色边缘保留为半透明，并使用设定的签名颜色；透明 PNG 则沿用原有透明度。原始签名文件不会被修改。

准备其他签名图片时，建议：

- **首选透明背景 PNG**：只保留清晰笔迹，使用黑色笔迹即可；导出时应实际保留背景透明度。
- **白底 JPG 也可以**：使用白纸、深色笔迹，拍摄时光线均匀，避免阴影、横线、格子和纸张纹理。这些杂色在染色时也可能被保留下来。
- **没有固定尺寸要求**：裁剪后高度约 300–600 像素通常足够，现有签名的 400 像素高度可作参考；文件名中的 `400` 不是尺寸限制。
- **裁掉多余空白，保留少量边距**，避免笔迹缩得太小或被裁断。按正常阅读方向保存，程序会自动缩放、旋转到照片右侧。

将新图片放入项目的 `assets/` 目录，然后在 [config.py](../src/watermark_tool/config.py) 中填写实际文件名，并开启图片签名：

```python
SIGNATURE_FILE = "my_signature.png"
SHOW_SIGNATURE = True
```

保存后下次运行生效，无需重新安装。签名颜色默认跟随 `WATERMARK_COLOR`，也可以用 `SIGNATURE_COLOR` 单独指定，见上方 [颜色设置](#背景与水印颜色)。

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

## 使用其他素材目录（进阶）

在终端中设置后，适用于从该终端启动的命令：

```bash
export WATERMARK_ASSETS_DIR="/完整路径/assets"
export WATERMARK_BRANDS_FILE="/完整路径/brands.json"
```

第一个变量指定素材目录，第二个单独指定品牌规则文件。未指定第二个变量时，从素材目录读取 `brands.json`。
