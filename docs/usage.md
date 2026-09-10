# 使用指南

[返回 README](../README.md) · [签名与品牌定制](customization.md) · [更新日志](../CHANGELOG.md)

## 安装与首次使用

1. 安装 [Python 3.10 或更新版本](https://www.python.org/downloads/macos/) 的 macOS `.pkg` 安装包；已有可用版本可跳过。
2. 下载并解压完整项目，放到「图片」等固定位置。
3. 双击 **[右键操作安装.command](../右键操作安装.command)**，等待“安装完成”，按回车关闭窗口。首次安装依赖需要联网。
4. 在 Finder 中选中照片 → 右键 → **快速操作**，选择所需功能。

安装器直接使用已有 Python 安装依赖，不新建环境，也无需激活环境。内置 Logo 可直接使用，无需安装 Conda、Homebrew 或 Cairo。

## 右键添加水印

| 需要做什么 | 选择方式 | 快速操作 |
| --- | --- | --- |
| 单张加水印 | 选一张照片 | **添加水印** |
| 多张拼成一张 | 选多张照片 | **添加水印** |
| 多张分别导出 | 选多张照片 | **批量添加水印** |

成片保存在原图目录，合成时使用第一张输入照片的目录。文件名以 `_watermark.jpg` 结尾，重名自动追加序号，原图保留。添加水印完成后会定位成片；批量处理中某张失败时继续处理其余照片，最后打开错误日志。

默认使用贴合照片的 `adaptive` 布局。要修改布局、签名或地点显示，见 [默认设置](#修改默认设置)；临时导出 PNG 等需求见 [命令行](#命令与参数)。

## 升级、移动与卸载

- **升级**：备份自己的配置、签名、Logo 和品牌规则，更新完整项目并迁移个人设置，再双击安装文件。不要直接用旧 `config.py` 覆盖新配置。
- **移动或改名**：从项目的新位置重新双击安装文件。
- **卸载**：双击 [右键操作卸载.command](../右键操作卸载.command)。照片、项目和 Python 保留。
- **菜单排序**：在快速操作的「自定…」中调整；顺序由 macOS 管理。

重复安装不会增加重复入口。安装器会备份可识别的旧操作；卸载时恢复曾替换的原始同名操作，其他已迁移的旧入口不自动恢复。备份保存在 `~/Library/Application Support/watermark-tool/finder-backups`。

## 安装排错

| 情况 | 处理方法 |
| --- | --- |
| 双击文件被系统拦截 | 按 macOS 的安全提示允许打开可信的项目脚本。 |
| 找不到 Python | 安装上方链接中的 Python 3.10+，再双击安装文件。 |
| pip 提示 `externally-managed-environment` 或没有写入权限 | 改用 Python 官网的 macOS 安装包，再重新安装右键操作；有多个 Python 时，按下方方法指定。 |
| 下载依赖失败 | 检查网络后重试。 |
| 提示证书验证失败（`CERTIFICATE_VERIFY_FAILED`） | 使用 Python 官网安装包时，打开「应用程序 → Python 3.x」，双击 `Install Certificates.command`，完成后重试。 |
| 右键菜单没有操作 | 先选中照片，在快速操作「自定…」或系统设置的 Finder 扩展中启用；仍未显示时重新登录。 |
| 项目或 Python 路径失效 | 保留完整项目，重新双击安装文件。 |
| 无法读取照片或保存 | 按 macOS 提示允许访问，确认照片目录可写。 |
| 提示备份或同名路径异常 | 查看报错中的路径，保留备份，勿直接删除其他工具的文件。 |

依赖安装或验证失败时，已有右键操作保持不变。电脑有多个 Python 时，可在项目目录指定安装所用的解释器；已有 Conda 用户也可指定现成的 Python：

```bash
WATERMARK_PYTHON_BIN="/完整路径/python3" /bin/zsh 右键操作安装.command
```

安装窗口会显示所用 Python 的路径，右键操作会记住该路径。

## 修改默认设置

用文本编辑器打开 [config.py](../src/watermark_tool/config.py)，修改并保存，下次右键处理即生效：

```python
OUTPUT_MODE = "adaptive"      # 贴合照片；video 为固定 4K；original 保留原尺寸
INCLUDE_GPS_LOCATION = False  # 关闭地点联网查询
```

更换签名、文字签名和品牌 Logo 见 [定制说明](customization.md)。

## 命令与参数

日常右键使用可跳过本节。打开终端，输入 `cd `（末尾有空格），将项目文件夹拖入终端，再按回车。

只用命令行时，在项目目录安装依赖一次即可：

```bash
python3 -m pip install -r requirements.txt
```

下列 `python3` 应使用安装依赖时的同一个 Python；有多个版本时，可替换为安装窗口显示的完整路径。将 `photo.jpg` 等示例名称换成自己的照片路径，路径含空格时加双引号。

```bash
# 单张加水印，默认贴合照片
python3 layout.py photo.jpg

# 多张合成为 16:9 视频素材（按输入顺序排列）
python3 layout.py photo1.jpg photo2.jpg --output-mode video

# 多张分别导出
python3 layout.py --batch photo1.jpg photo2.jpg

# 保留照片原始尺寸，导出 PNG
python3 layout.py photo.png --output-mode original -o output.png
```

**多张输入默认合成一张；加 `--batch` 才会逐张导出。** `--batch` 不能与 `-o` 同用。

自动命名的成片不会覆盖已有文件。`-o` 可指定 `.jpg`、`.jpeg` 或 `.png`，会替换同名成片，但不能覆盖输入原图；保存失败时保留已有输出。

| 参数 | 用途 | 默认值 |
| --- | --- | --- |
| `--output-mode` | `adaptive` 贴合照片；`video` 固定 4K；`original` 保留原尺寸 | `adaptive` |
| `--height` | 照片高度，单位为像素；不影响 original | `1850` |
| `--jpeg-quality` | JPEG 质量，1～100 | `100` |
| `--png-compression` | PNG 无损压缩：`fast` 快、`balanced` 均衡、`small` 体积较小 | `balanced` |
| `--include-gps-location` | 是否联网查询照片地点 | `true` |
| `--color-mode` | `preserve` 保留来源色域；`srgb` 便于普通分享 | `preserve` |
| `--metadata` | `safe` 保留筛选后的拍摄信息；`none` 删除非色彩元数据 | `safe` |
| `--preserve-gps` | 是否在 safe 模式下保留单图 EXIF GPS | `false` |
| `--show-signature` | 是否显示签名图片 | `true` |
| `--signature-text` | 关闭签名图片后的替代文字；`""` 表示隐藏 | `哈哈哈` |

以上为随附默认值，修改 `config.py` 后命令行也会使用新值。完整参数见 `python3 layout.py --help`。

## 布局与格式

- **adaptive**：按指定高度缩放，画布宽度随照片调整。适合单图分享和多图长拼接。
- **video**：固定 3840 × 2160，支持 1～3 张，左右留白与图间距相等。水印空间不足时自动降低照片高度。
- **original**：保留旋正后的原始像素尺寸，照片顶部对齐，画布随内容扩展。搭配 PNG 可避免缩放和 JPEG 重编码。

支持 JPEG、PNG、WebP、HEIC / HEIF，仅处理 SDR。RAW、TIFF、HDR 请先在照片编辑软件中转为 SDR PNG 或 JPEG；Logo 和签名也不支持 TIFF。

内置品牌：Canon、Nikon、Sony、Fujifilm、Leica、Hasselblad、Ricoh、Lumix、Olympus、Apple、Honor、Samsung、OnePlus、OPPO、vivo、Xiaomi。按拍摄信息匹配，缺少信息或素材时跳过 Logo。

## 画质、拍摄信息与地点

默认导出 JPEG 100%，保留来源 RGB 色域。JPEG 仍是有损格式；需要保留细节时用 `original` 加 PNG，缩放和色彩转换仍可能改变像素。

- **普通分享**：`--color-mode srgb` 转为常见的 8 位 sRGB；广色域成片需在支持 ICC 的软件中查看。
- **高位深与透明度**：保留色域模式下，高位深来源或混合色域导出 PNG 自动使用 16 位。PNG 保留透明度；JPEG 为 8 位，透明区域合成到背景上。
- **拍摄信息**：单图默认保留筛选后的参数、作者和版权等信息，去除旧缩略图与设备序列号；多图仅保留共同信息。`--metadata none` 删除非色彩元数据。
- **地点隐私**：默认将照片中的经纬度发送给 Nominatim 查询地名，照片在本地处理。用 `--include-gps-location false` 关闭查询；成片默认不保留 EXIF GPS，需单独用 `--preserve-gps true` 开启。

元数据开关不会隐藏已绘制到成片上的日期、参数或地点文字。

<details>
<summary>色彩与元数据的详细规则</summary>

相同 RGB 色彩定义沿用来源色域；混合 SDR 色域转为 ProPhoto RGB。未标记色域的 RGB / 灰度按 sRGB 解释。相同 RGB 定义、无缩放的 PNG 照片区域可保留解码后的原始 RGB 样本。

HDR、损坏或不匹配的 ICC、不支持的色彩标记会报错。带有效 ICC 的 CMYK / Lab 图片可用 `--color-mode srgb` 转换。

单图保留筛选后的 EXIF、DPI 及 XMP / IPTC 标题、描述、关键词、评级等，重建尺寸与方向，移除 MakerNote；某个 EXIF 子 IFD 损坏时警告并跳过该部分。多图仅保留共同作者、版权和筛选后的共同 XMP，不指定单一相机、日期或位置。色彩配置不受 `--metadata none` 影响。

</details>

## 处理问题与速度

- **没有日期或参数**：检查原图是否保留拍摄信息。日期只取有效的 EXIF 拍摄时间，不使用文件修改时间；焦距优先显示 35mm 等效值。
- **文字拥挤**：减小字号或间距，或将 video 改为 adaptive / original。字体缺失时用 `--font`、`--location-font` 指定字体文件。
- **图片过大**：多图合成受内存限制。JPEG 单边最多 65,500 像素，超出请用 PNG；大量照片可用 `--batch` 分别导出。
- **处理较慢**：无需地点文字时关闭联网查询；PNG 可选 `--png-compression fast`，只改变压缩速度和体积，不降低画质。

命令行显示处理进度，`--quiet` 可隐藏。Finder 使用系统通知提示进度；是否显示取决于通知权限和专注模式。

### 缓存与运行速度

素材缓存位于 `~/Library/Caches/watermark-tool/assets`，地点缓存位于同级 `gps` 目录，均不保存照片。更换素材后自动刷新。地点结果保留 30 天、最多 2048 条；坐标键的哈希不等于加密。删除对应目录即可清理，缓存损坏或不可写不影响继续处理。

```bash
# 关闭所有磁盘缓存
WATERMARK_CACHE_DIR=off python3 layout.py photo.jpg

# 只关闭地点磁盘缓存；仍允许联网查询
WATERMARK_GPS_CACHE_DIR=off python3 layout.py photo.jpg
```

这两个变量也可设为完整目录路径。关闭联网查询仍用 `--include-gps-location false`，同时跳过地点缓存读取。

## 自定义 SVG（可选）

新手建议使用透明 PNG。确需 SVG 时，用运行工具的同一个 Python 安装：

```bash
python3 -m pip install ".[svg]"
```

还需安装原生 Cairo 库；已有 Homebrew 可运行 `brew install cairo libffi`，已有 Conda 可在当前使用的环境运行 `conda install -c conda-forge cairo libffi`。具体要求见 [CairoSVG 文档](https://cairosvg.org/documentation/#installation)。

用 `python3 -c "import cairosvg"` 检查依赖是否可用。若仍报错，可将 SVG 转为 PNG，并更新 `assets/brands.json` 的文件名。

## 获取帮助

提交 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues) 时，附上系统、Python 版本、复现步骤及完整报错。Finder 处理失败时会打开错误日志。开发和测试方法见 [开发说明](development.md)。
