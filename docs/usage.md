# 使用指南

[返回 README](../README.md) · [签名与品牌定制](customization.md) · [更新日志与升级说明](../CHANGELOG.md)

本文适用于 **2.2.2**。快速上手见 [README](../README.md#安装与使用)，从旧版升级见 [升级步骤](../CHANGELOG.md#升级到-222)。

## 在 Finder 中右键使用

### 首次使用：准备 Mac 环境

可选 **pip** 或 **Conda**，不用同时安装；已经能正常使用右键操作时无需重配。pip 方案适合已有 Python 和 Cairo 的电脑；不想安装 Homebrew、又没有 Cairo 时，选 Conda。两种方案都由安装器配置右键入口，日常无需激活环境。

#### 方案一：Python + pip

1. 从 [Python 官网](https://www.python.org/downloads/macos/) 下载标准 macOS `.pkg` 安装包（Python 3.10+），双击安装；按安装完成提示运行「Install Certificates.command」。已有可用 Python 时可跳过。步骤见 [Python 官方说明](https://docs.python.org/3/using/mac.html)。
2. 下载并解压完整项目，放到「图片」等固定位置。
3. 双击 **[右键操作安装.command](../右键操作安装.command)**。安装器自动创建专用环境，并用 pip 安装 `requirements.txt` 中的依赖，无需手动输入虚拟环境命令。

**pip 可以装 CairoSVG，但不负责安装它需要的 Cairo 原生库。** 若安装器提示找不到 `cairo`、`libcairo` 或 `libffi`，可改用下方 Conda 方案；单独重装 CairoSVG 不能补齐原生库。依赖说明见 [CairoSVG 文档](https://cairosvg.org/documentation/#installation)。

熟悉终端、只想手动安装 Python 依赖时，在项目目录运行：

```bash
python3 -m pip install -r requirements.txt
```

这条命令只安装到当前 Python，不会注册右键操作。右键安装器使用自己的环境，仍需双击安装文件；普通用户直接用第 3 步即可。

#### 方案二：Conda（无需 Homebrew）

此方案需要 **2.2.2 或更新版本**，旧版安装器不能直接复用 Conda 环境。

1. 安装 [Miniforge](https://conda-forge.org/download/)；Mac 的 M 系列芯片选 **arm64**，Intel 选 **x86_64**。已有 Miniconda、Anaconda 或 Miniforge 时无需再装。下载 `.sh` 文件后，在终端输入 `bash `（末尾留一个空格），将下载的文件拖入终端，按回车并按提示安装；完成初始化后重新打开终端，运行 `conda --version` 确认可用。
2. 下载并解压项目，放到固定位置。打开终端，输入 `cd `（末尾留一个空格），把项目文件夹拖入终端并按回车，然后复制执行：

```bash
conda create --prefix ./.venv --override-channels -c conda-forge python=3.14 pip cairo libffi cairosvg -y
```

3. 回到 Finder，双击 **[右键操作安装.command](../右键操作安装.command)**，等待「安装完成」。安装器复用刚才创建的 Conda 环境，用 pip 补齐其余图片依赖；两个右键操作直接调用该环境，无需每次执行 `conda activate`。

这里的 `.venv` 只是工具约定的本地环境目录名，Conda 会在其中同时安装 Python 和 Cairo。若此目录已被之前的安装占用，先在 Finder 按 `Command + Shift + .` 显示隐藏文件，将 `.venv` 改名备份，再执行创建命令。不要在已有 venv 上叠装 Conda。

Conda 支持使用项目路径创建环境，Cairo 由 conda-forge 提供。参见 [Conda 环境说明](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html) 和 [Cairo 软件包](https://anaconda.org/conda-forge/cairo)。

**已使用 Homebrew 的用户**也可沿用 `brew install python cairo libffi`，然后双击水印安装器，无需再装 Conda。

### 添加水印：单张处理或多张合成

在 Finder 中选中照片 → 右键 →「快速操作」→ **添加水印**。

- 选中一张：给这张照片添加水印，生成一张成片。
- 选中多张：按项目当前布局设置，将照片拼接为一张水印成片。
- 成片保存在第一张输入照片所在目录，文件名组合输入照片名称并加上 `_watermark.jpg`；重名自动追加序号，原图保留。
- 完成后会在 Finder 中定位成片。张数和布局限制沿用项目配置，与命令行合成一致。

### 批量添加水印：逐张导出

在 Finder 中选中多张照片 → 右键 →「快速操作」→ **批量添加水印**。

- 每张照片各自生成成片，保存在各自原图目录，名称为 `原文件名_watermark.jpg`；重名自动追加序号，原图保留。
- 单张失败会继续处理其余照片，并在完成后打开错误日志。
- 单选时也可使用，只处理这张照片。

两个操作运行时均无需打开终端。需要临时选择 PNG 或其他参数时，使用下方 [命令行](#命令与参数)。

### 调整菜单顺序

右键 →「快速操作」→「自定…」，进入 Finder 扩展列表，将「添加水印」拖到「批量添加水印」上方，点击「完成」后重新打开右键菜单。顺序由 macOS 管理，安装器不强制调整。参见 [Finder 快速操作排序说明](https://macosxautomation.com/automator/services/extensions.html)。

### 升级、移动与旧入口迁移

更新完整项目后，重新双击「右键操作安装.command」即可。项目移动或改名后，也应从新位置重新安装，让操作指向新的项目路径。Conda 环境不应直接搬移：移动项目后先将 `.venv` 改名备份，再按 Conda 方案重新创建。

升级后，「添加水印」多选会合成一张；逐张导出请改用「批量添加水印」。安装器会备份移除可识别的旧「照片加水印」「批量加水印」「合成水印照片」，保留两个新入口，重复安装不会生成重复项。

工作流程位于 `~/Library/Services/`，旧操作备份位于 `~/Library/Application Support/watermark-tool/finder-backups`。无法确认属于本工具的旧入口会保留；两个安装目标存在非托管同名操作时，先备份再替换。

### 卸载右键操作

双击 **[右键操作卸载.command](../右键操作卸载.command)**，等待卸载完成后按回车关闭窗口。

卸载移除本工具管理的两个入口，并恢复曾替换的原始同名操作（如有）。迁移时移除的其他旧入口留在备份目录，不自动恢复。照片、项目、Python 环境和其他快速操作均保留；卸载仍需可用的 Python，但不安装图片依赖。

### 环境要求与排错

工具需要 Python 3.10+ 和 Cairo / libffi。首次配置按上方 [pip 或 Conda 方案](#首次使用准备-mac-环境) 操作；水印安装器会自动完成剩余配置，本身不需要管理员权限。

| 情况 | 处理方法 |
| --- | --- |
| 双击脚本被系统拦截 | 根据 macOS 显示的安全提示允许打开可信的项目脚本，再重新双击；安装器不绕过系统权限。 |
| 右键菜单中没有操作 | 确认已选中照片，关闭并重新打开右键菜单；在快速操作的「自定」或系统设置的 Finder 扩展中确认操作已启用，必要时重新登录。 |
| 找不到脚本或项目移动了 | 确认保留完整项目文件夹，从实际项目位置重新双击安装器。 |
| 找不到 Python，或缺少 Cairo / libffi | 按上方环境准备步骤安装基础组件，再双击水印安装器。 |
| 提示 `conda: command not found` | 完成 Miniforge 安装和终端初始化，重新打开终端后运行 `conda --version`。 |
| pip 提示 `externally-managed-environment` | 直接双击水印安装器，让它使用专用环境；不要强行向受管理的系统 Python 安装。 |
| 下载依赖失败 | 检查网络并重新双击安装器；验证失败时不会替换已有右键操作。 |
| `.venv` 无效或不完整 | 将项目中的 `.venv` 文件夹改名备份后重新双击安装，安装器会创建新环境。 |
| 提示没有收到照片 | 先在 Finder 中选中照片，再从右键菜单调用「添加水印」。 |
| 无法访问照片或保存目录 | 按 macOS 提示允许相应目录的访问，并确认照片所在目录可写。 |
| 同名操作不是普通目录或备份不可用 | 查看安装器指出的具体路径；保留备份并检查该路径后重试，避免直接删除其他工具的文件。 |

### 修改默认设置

右键操作使用 [config.py](../src/watermark_tool/config.py) 的默认值，保存后下次运行生效，无需重新安装。例如：

```python
OUTPUT_MODE = "adaptive"      # video / adaptive / original
INCLUDE_GPS_LOCATION = False  # 关闭地点联网查询
```

签名和 Logo 的替换见 [定制说明](customization.md)。

## 命令与参数

本节仅供需要自定义导出参数的进阶用户阅读，日常右键使用可跳过。完成双击安装后，在终端进入项目目录。pip 默认环境可按下面方式激活；Conda 方案改用 `conda activate ./.venv`。以下命令中的 `python3` 将使用项目依赖：

```bash
cd "/完整路径/watermark_tool"
source .venv/bin/activate
```

```bash
# 单张照片：紧凑边框
python3 layout.py photo.jpg --output-mode adaptive

# 两张照片：合成为 16:9 视频素材（按输入顺序排列）
python3 layout.py photo1.jpg photo2.jpg --output-mode video

# 多张照片：合成长图
python3 layout.py photo1.jpg photo2.jpg photo3.jpg --output-mode adaptive

# 保留原始尺寸并导出 PNG
python3 layout.py photo.png --output-mode original -o output.png

# 快速无损 PNG；更看重体积时改为 small
python3 layout.py photo.png --output-mode original --png-compression fast -o output.png

# 逐张批量导出，关闭地点联网查询
python3 layout.py --batch photo1.jpg photo2.jpg --output-mode original --include-gps-location false

# 使用文字签名；文字设为空字符串可完全隐藏签名
python3 layout.py photo.jpg --show-signature false --signature-text "Shot by You"
```

**命令行多张输入默认合成一张，添加 `--batch` 才会逐张导出。** `--batch` 不能与 `-o` 同用，默认导出 JPEG。

默认文件名为 `原文件名_watermark.jpg`；合成时连接各照片文件名，过长时缩短为首张名称加其余张数。文件保存在第一张输入照片的目录，重名时追加序号。`-o` 仅支持 `.jpg`、`.jpeg`、`.png`，会替换同名的已有成片，但拒绝覆盖任何输入原图；编码失败不会损坏已有输出。

| 参数 | 用途 | 默认值 |
| --- | --- | --- |
| `--output-mode` | `video` 固定 4K；`adaptive` 调整宽度；`original` 保留原尺寸 | `adaptive`，跟随 `config.py` 的 `OUTPUT_MODE` |
| `--height` | 照片高度（像素）；不影响 original | `1850` |
| `--jpeg-quality` | JPEG 质量 1～100；不影响 PNG | `100` |
| `--png-compression` | PNG 无损压缩：`fast` 快速、`balanced` 均衡、`small` 较小文件；不影响 JPEG | `balanced` |
| `--include-gps-location` | 是否发送经纬度联网查询地点 | `true` |
| `--color-mode` | `preserve` 保留来源色域；`srgb` 转为 8 位 SDR sRGB | `preserve` |
| `--metadata` | `safe` 保留筛选后的元数据；`none` 删除非色彩元数据 | `safe` |
| `--preserve-gps` | safe 模式下保留单张成片的 EXIF GPS | `false` |
| `--show-signature` | 是否显示签名图片 | `true` |
| `--signature-text` | 关闭签名图片后显示的文字，空字符串表示隐藏 | `哈哈哈` |

日期、字体、线条和间距等参数见 `python3 layout.py --help`；长期默认值在 [config.py](../src/watermark_tool/config.py) 中修改。

## 排版规则

- **video**：固定 3840 × 2160，支持 1～3 张照片，左右留白与图间距相等。空间不足时自动降低照片高度，日期字号和横线长度保持指定值。
- **adaptive**：按指定高度缩放照片，画布宽度随内容增长。单图使用紧凑边框；多图的图间距和左右留白均为上留白的 1.8 倍。
- **original**：保留旋正后的原始像素尺寸，顶部对齐，画布随照片、水印和日期扩展；`--height` 不参与缩放。搭配 PNG 可避免照片重采样和 JPEG 重编码。

## 相机与图片格式

支持 JPEG、PNG、WebP 和 HEIC / HEIF（通过 `pillow-heif` 读取），仅处理 SDR。不支持 RAW、TIFF 或 HDR，请先在照片编辑软件中导出 SDR PNG 或 JPEG。Logo 和签名素材也不支持 TIFF。

工具根据 EXIF 中的厂商和型号匹配 Logo，当前附带以下品牌素材：

| 相机品牌 | 手机品牌 |
| --- | --- |
| Canon、Nikon、Sony、Fujifilm | Apple、Honor、Samsung、OnePlus |
| Leica、Hasselblad、Ricoh、Panasonic Lumix | OPPO、vivo、Xiaomi |
| Olympus / OM System（使用 Olympus 标志） | |

品牌匹配不代表所有机型都经过验证。没有 EXIF、未匹配到品牌或缺少 Logo 时会跳过标志，仍可显示签名。添加品牌及更换签名见 [定制说明](customization.md)。

## 色彩与元数据

默认以 JPEG 100%、4:4:4 色度采样输出，保留来源 RGB 色域。JPEG 仍为有损编码，提高质量不等于按比例提高画质；需要避免照片缩放和 JPEG 重编码时，使用 `--output-mode original -o output.png`。

- **色域**：相同 RGB 色彩定义沿用来源色域；混合 SDR 色域转为 ProPhoto RGB。广色域成片需在支持 ICC 的软件中查看，普通分享可用 `--color-mode srgb`。
- **位深与透明度**：保留色域模式下，高位深来源或混合色域合成导出 PNG 时自动使用 16 位；PNG 保留照片透明度，JPEG 降为 8 位并将透明区域合成到背景上。sRGB 模式输出为 8 位。
- **保真范围**：相同 RGB 定义、无缩放的 PNG 照片区域可保留解码后的原始 RGB 样本；缩放、混合色域转换仍会改变像素。未标记色域的 RGB / 灰度按 sRGB 解释。
- **不支持的输入**：检测到 HDR、损坏或不匹配的 ICC、不支持的色彩标记时会报错。带有效 ICC 的 CMYK / Lab 图片可用 `--color-mode srgb` 转换。
- **单图元数据**：默认保留筛选后的拍摄参数、作者、版权、DPI，以及 XMP / IPTC 中的标题、描述、关键词和评级等；重建尺寸及方向，移除旧缩略图、MakerNote 和设备序列号。
- **损坏字段**：某个 EXIF 子 IFD 无法解析时会发出警告并跳过该部分，其他可读取的相机和拍摄字段继续使用。
- **多图元数据**：仅保留共同的作者、版权及筛选后的共同 XMP，不指定单一相机、日期或位置。`--metadata none` 删除非色彩元数据，仍保留正确显示所需的色彩配置。

GPS 地点查询默认开启：有坐标时会将经纬度发送给 Nominatim（OpenStreetMap）查询地名，照片文件在本地处理。`--include-gps-location false` 关闭联网；`--preserve-gps true` 控制 safe 模式下单图 EXIF GPS 的导出，两者独立。元数据开关不会隐藏已绘制到图片上的文字。

```bash
# 分享为 sRGB JPEG
python3 layout.py photo.jpg --color-mode srgb -o share.jpg

# 保留单图 EXIF GPS，同时关闭地点联网查询
python3 layout.py photo.jpg --preserve-gps true --include-gps-location false

# 不保留非色彩元数据，也不联网查询地点
python3 layout.py photo.jpg --metadata none --include-gps-location false
```

## 使用限制与排错

- **排版拥挤**：减小高度、字号或间距，或将 video 改为 adaptive / original。日期和横线保持指定大小，窄图仍需检查效果；水印超出上下边界时程序会报错。
- **超长图片**：adaptive / original 的实际大小受内存和图片格式限制。JPEG 单边最多 65,500px，超出时使用 PNG；大批量照片宜用 `--batch` 分别导出。
- **拍摄参数**：焦距优先使用有效的 35mm 等效焦距，缺失时用实际焦距。快门按倒数或小数秒显示，如 `1/125s`、`0.8s`。
- **拍摄日期**：仅使用有效的 EXIF `DateTimeOriginal`，显示到秒，不显示小数秒或时区，不转换到电脑时区。缺失或无效时省略，不使用文件修改时间。
- **字体缺失**：默认查找系统字体，可通过 `--font`、`--location-font` 指定字体文件。
- **处理较慢**：耗时取决于尺寸、格式、硬件和网络。无需地点文字时可关闭 GPS 查询；素材缓存和同进程批处理有助于减少重复处理。

## 缓存与运行速度

macOS 素材缓存位于 `~/Library/Caches/watermark-tool/assets`，只保存处理后的位图 Logo 和签名，不保存照片或地点数据。更换素材后自动重新生成；可删除该目录清理缓存，下次运行会重建。GPS 成功查询结果另存于 `~/Library/Caches/watermark-tool/gps/locations.sqlite3`，有效期 30 天，最多保留 2048 条，跨进程及 Finder 再次运行可复用。地点缓存保存地名、有效期和经纬度（四舍五入到 5 位小数）与语言组成的键的哈希，不保存照片；哈希不等于加密。删除 `gps` 目录即可清理磁盘地点缓存，已运行进程的内存缓存会在退出后清除。查询失败或空结果不写入磁盘，仅在当前进程内暂存 60 秒。缓存不可写或损坏时仍可继续查询和导出。

```bash
# 指定缓存目录，或关闭磁盘缓存
WATERMARK_CACHE_DIR=/path/to/cache python3 layout.py photo.jpg
WATERMARK_CACHE_DIR=off python3 layout.py photo.jpg

# 单独关闭 GPS 磁盘缓存（仍允许联网）；也可指定专用目录
WATERMARK_GPS_CACHE_DIR=off python3 layout.py photo.jpg

# 测量本机首次及后续处理耗时，结果保存到指定目录
python3 scripts/benchmark_render.py --output-dir output/benchmark --iterations 3
```

`WATERMARK_CACHE_DIR` 指定素材缓存目录时，GPS 默认位于该目录的 `gps` 子目录；`WATERMARK_GPS_CACHE_DIR` 可单独指定地点目录。`WATERMARK_CACHE_DIR=off` 同时关闭两类磁盘缓存。关闭地点联网查询仍使用 `--include-gps-location false`，该开关也会跳过地点缓存读取。

PNG 三种压缩设置均为无损，解码后的像素、位深、透明度和元数据一致。默认 `balanced` 沿用压缩等级 6，`fast` 使用等级 1，`small` 使用等级 9；体积差异取决于图片内容，不保证每张图都有明显缩小。JPEG 不受此参数影响。

命令行实时显示“正在准备第几张”“正在查询地点”“正在处理第几张”和“正在保存”，批量模式另显示总张数进度。`--quiet` 隐藏这些正常进度及摘要。Finder 脚本默认以 macOS 通知显示阶段提示（最多每 2 秒一次），完整进度同时写入运行日志；较快的阶段可能被合并，通知显示还取决于系统通知权限和专注模式。阶段通知的高级配置见 [开发说明](development.md#finder-双击安装器)。

## 支持与开发

遇到问题可提交 [GitHub Issue](https://github.com/chilemay-0417/watermark-tool/issues)，附上系统和 Python 版本、输入格式、复现步骤及完整报错；Finder 失败时会自动打开错误日志。

内部模块职责、辅助函数导入迁移、安装器及验证记录见 [开发说明](development.md)。升级后重新双击安装器即可更新右键操作。

开发检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover
python3 -m ruff check .
```

README 直接使用 `samples/` 中的展示样张。样张已缩小尺寸并压缩，不用于评估原始画质；工具实际导出仍由所选参数决定。
