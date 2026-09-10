# 开发说明

[使用指南](usage.md) · [签名与品牌定制](customization.md) · [更新日志](../CHANGELOG.md)

本文适用于 **2.2.3**，说明模块职责、内部接口、验证方法和性能测量。对外 Python 入口仍为 `watermark_tool.LayoutConfig` 和 `watermark_tool.make_canvas`；命令行入口与根目录的 `layout.py` 保持可用。内部辅助函数按职责从对应模块导入。

## 模块职责

下表中的 `layout.py` 指 `src/watermark_tool/layout.py`；项目根目录同名文件是兼容入口。

| 模块 | 职责 |
| --- | --- |
| `renderer.py` | 校验输入路径，统一准备照片、字体、水印与布局，选择色彩渲染路径并输出摘要 |
| `brands.py` | 品牌规则加载、相机匹配与逐图 Logo 计划 |
| `assets.py` | 字体、Logo、签名的准备与资源缓存调用 |
| `asset_cache.py` | 已处理位图素材的内存与磁盘缓存、内容失效检查 |
| `layout.py` | 参数校验、标记尺寸测量以及 video / adaptive / original 的布局计算 |
| `annotations.py` | 照片位置、横线、日期、参数、Logo 与签名的绘制 |
| `drawing.py` | Pillow 图片头与像素读取、文字绘制、字体加载和 sRGB 编码 |
| `preserved.py` | 使用已准备的输入与布局进行原生精度合成、PNG/JPEG 编码 |
| `annotation_tiles.py` | 只为文字、横线和水印触及的区域分配 Pillow 分块 |
| `location_cache.py` | 有有效期、容量限制的 GPS 地点 SQLite 磁盘缓存 |
| `raster.py` / `color.py` | 原生位深像素读取、高精度色彩转换 / sRGB 归一化与色彩规则 |
| `metadata.py` / `exif_gps.py` | 元数据读取与安全输出策略 / 拍摄参数和 GPS 地点的格式化 |
| `utils.py` | 日志与同目录临时文件原子替换 |
| `scripts/install_finder.py` | 安装、迁移、备份和卸载 Finder「添加水印」「批量添加水印」操作 |
| `scripts/finder_setup.zsh` | 双击安装/卸载入口的 Python 选择与引导 |

## 共享流程与依赖

`make_canvas()` 复制调用者的配置，校验输入和输出路径，准备字体、照片元数据及文字图，选择水印计划，然后调用共享布局计算。保留色域模式先通过 `inspect_raster()` 取得尺寸、色彩与元数据快照；sRGB 模式在延迟准备阶段通过 `read_image_header()` 读取尺寸与快照。

布局计算完成后，sRGB 路径由 `_render_srgb_canvas()` 绘制和编码；保留色域路径由 `render_preserved_canvas()` 使用准备好的输入合成。两者调用 `annotations.py` 中的相同绘制函数，最后由入口统一输出摘要。

布局和标记绘制的修改应放在共享模块中。`preserved.py` 不应导入 `renderer.py`，也不应重新准备字体、水印或布局。原尺寸布局的 `original_metrics()` 位于共享布局模块，不再依赖色彩后端。

## Logo 与可选 SVG 依赖

内置 Logo 已为 PNG，现有素材无需重新转换。新增矢量 Logo 应在维护阶段导出为透明 PNG（建议高度至少 400 像素），在 `assets/brands.json` 中引用 PNG；原 SVG 可作为源素材保留。运行时按 `LOGO_HEIGHT` 缩放，基础安装不依赖 Cairo。

`pyproject.toml` 的基础依赖与 `requirements.txt` / `requirements.lock` 保持一致；CairoSVG 仅放在 `svg` extra 中。`assets.open_logo_image()` 只在读取 SVG 时导入 CairoSVG，导入失败或缺少原生库时给出安装指引；SVG 解析错误仍保留原始异常。安装命令见 [可选 SVG 支持](usage.md#自定义-svg可选)。

macOS 上部分 NumPy wheel 的 Accelerate 批量矩阵运算会导致色彩转换崩溃。`render_rgb_array()` 和 `srgb_to_color()` 将 RGB 数组展平为二维后计算，再恢复形状；保留原有分块和色彩公式。

## 内部接口迁移

| 重构前 | 当前入口或处理方式 |
| --- | --- |
| `renderer.choose_logo_by_camera`、`resolve_logo_path`、`select_logo_paths_for_items` 等品牌函数 | `watermark_tool.brands` |
| `renderer.prepare_fonts`、`prepare_logo_image`、`load_watermark_assets` 等资源函数 | `watermark_tool.assets` |
| `renderer.validate_layout_params`、`calculate_layout_metrics`、`get_annotation_extents` 等布局函数 | `watermark_tool.layout` |
| `preserved.original_metrics` | `watermark_tool.layout.original_metrics` |
| `renderer.draw_photo_item`、`draw_watermark_assets` 等绘制函数 | `watermark_tool.annotations` |
| `preserved.make_preserved_canvas(paths, output_path, config)` | 外部调用统一使用 `watermark_tool.make_canvas()`；内部后端改为 `render_preserved_canvas(paths, output_path, config, items, headers, assets, metrics)` |
| `WatermarkAssets.max_width`、`reserved_right_width`、`internal_reserved_width` | 已删除；构造对象时移除这些参数，水印占用由共享布局根据资源和计划实时测量 |
| `select_logo_path_for_items()` | 已删除；使用返回逐图计划的 `brands.select_logo_paths_for_items()` |
| `get_text_size_with_tracking()` | 已删除；需要文字边界时使用 `drawing.get_text_bbox_with_tracking()`，并处理空文本返回 `None` 的情况 |

根目录 `layout.py` 继续转出迁移后的辅助函数，以保留原有兼容入口；上表已删除的函数和字段不再提供。包内代码和测试直接导入实际负责的模块；例如需要替换绘制函数进行测试时，应替换 `watermark_tool.annotations.draw_photo_item`。

## 实现约定

- **元数据**：`read_source_metadata()` 返回根 EXIF、拍摄参数 IFD、GPS IFD、图片信息和 IPTC 快照。`read_exif_all()` 只负责展开快照；`read_photo_metadata()` 接收已有快照时不重新打开文件。延迟准备 PNG 时，尺寸和参数共用一次快照读取，不触发像素解码；某个 IFD 解析失败不会丢弃其他有效字段。
- **文字绘制**：日期、旋转参数文字和居中文字签名都调用 `draw_text_with_tracking()`，各自保留原来的定位、透明画布和旋转规则。调整字距时应同时检查实际绘制边界。
- **资源尺寸**：`WatermarkAssets` 保留签名、Logo 和逐图水印计划；通过 `get_mark_width()`、`get_annotation_extents()` 计算占用，避免缓存重复尺寸导致布局与实际绘制不同步。
- **原子保存**：通过 `atomic_output_path()` 取得与目标同目录的临时路径，编码成功后才替换目标；异常时清理临时文件。该流程由两条导出路径和素材缓存共用，缓存层单独容忍写入失败，保证仍能返回已准备的素材。
- **默认配置**：命令行默认值来自 `LayoutConfig`。用户自行修改 `config.py` 后，默认值测试应继续验证命令行是否遵循配置，而不是强制某一种输出模式。

## 渲染、编码与缓存

1. **局部色彩转换**：保真后端将背景 RGB 转到输出色域一次，再广播填入输出数组。共享标注函数绘制到 `AnnotationTiles`，只为触及区域创建最多 256 × 256 的 RGB 分块，逐块转换；无需转换照片覆盖的整片背景。相邻图的文字/标志仍按原来的绘制顺序处理，最后写入原生照片样本。
2. **整数直拷贝**：来源与目标色域定义、位深及尺寸均匹配时，照片 RGB 直接复制到输出；PNG 的 alpha 同样直接复制。透明照片导出 JPEG、缩放、混合位深或混合色域时继续使用原有高精度合成路径。JPEG 编码本身仍然有损。
3. **内存分配**：取消完整 Pillow 背景画布和照片尺寸的纯色占位图。`draw_photo_item(..., photo_size=(w, h))` 仅计算位置并绘制标注，不粘贴照片；未传入此参数时保持原有 Pillow 行为。保真路径保留一份完整目标整数数组，并逐张解码/释放来源；输出仍非恒定内存，缩放及色域转换仍需要工作缓冲。
4. **PNG 编码**：`LayoutConfig.png_compression` 及 `--png-compression` 提供 `fast / balanced / small`，映射到 zlib/Pillow 等级 `1 / 6 / 9`。默认保持 6；两条后端都应用相同设置，仅改变编码耗时与压缩体积，保留原子写入和所有色彩/元数据规则。
5. **GPS 与进度**：成功地点查询写入 SQLite，TTL 30 天、容量 2048 条，按到期时间淘汰；查询使用坐标四舍五入到 5 位小数及语言键。失败/空值仅在内存缓存 60 秒，命中不续期。每次操作独立连接并在事务后关闭，锁等待最多 0.2 秒；读写错误忽略，继续正常查询或导出。查询入口保留原有请求间隔与总超时预算。`utils.progress()` 实时写入日志；Finder 脚本启用限频的系统通知，消息作为 AppleScript 参数传递，通知失败不影响导出。

文字绘制分块不能直接把小数坐标减去块原点再交给 Pillow：当局部坐标变成负数时，`int()` 截断可能改变字形位置。本实现用全局整数原点与小数起点生成字体遮罩，再按整数位置贴入分块，确保跨块字形与完整 Pillow 画布一致。

地点缓存路径、禁用和清理方式见 [使用指南](usage.md#缓存与运行速度)。磁盘缓存会保留地名；坐标键哈希不是加密，不应将该数据库视为脱敏文件。默认缓存目录权限为 0700（创建时），数据库权限为 0600。

## 测试与验证

2.2.3 验证（2026-09-10，macOS / Python 3.14.2）：现有环境 163 项测试通过，包含实际 SVG 渲染；不含 CairoSVG / cairocffi 的全新 pip 环境通过 162 项，另 1 项可选 SVG 渲染测试跳过。新环境使用 NumPy 2.5.3、Pillow 12.3.0、pillow-heif 1.7.0，基础安装、wheel 素材读取和单张 / 合成导出通过。24 组色彩转换逐像素一致，另 16 组目标色域数组量化结果一致；Ruff、Shell 语法和文档链接检查通过。

回归测试包含跨块/小数字距及透明标志的逐像素对照、8/16 位 RGBA 原样复制、大画布及占位图分配防回归、两条后端 PNG 压缩档位的像素/元数据一致性、跨进程 GPS 缓存、TTL、容量、失败与不可写降级，以及通知参数传递与限频。GPS 测试使用临时目录及模拟响应，不向真实地理服务发出请求。

双击安装器准备好项目环境后，在项目根目录安装开发依赖并执行常规检查：

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m unittest discover -v
.venv/bin/ruff check .
git diff --check
zsh -n 右键操作安装.command 右键操作卸载.command scripts/finder_setup.zsh
zsh -n watermark_batch_each.sh watermark_combine_selected.sh scripts/finder_common.zsh
.venv/bin/python layout.py --help
.venv/bin/python -m watermark_tool --help
```

2.1.0 的历史渲染验证记录（2026-09-10，2.2.2 安装器验证见下节）：

| 验证 | 结果与范围 |
| --- | --- |
| 自动测试 | 143 项通过，覆盖布局、色彩、位深、透明度、元数据、原子保存、批量处理、缓存及 Finder 模拟入口 |
| 成片对照 | 3 组样张 × 3 种布局 × 2 条色彩路径 × 2 种格式，共 36 组；使用非白背景和 2.5 字距，尺寸、解码像素、非 ICC 元数据及 ICC 色彩定义一致 |
| 重构阶段文字对照 | 5 类文本 × 3 种字距 × 2 种文字图，共 30 组；包括空文本、空格、中英文，尺寸和像素一致 |
| 静态与入口 | Ruff、`git diff --check`、Finder 脚本语法及两个 CLI 帮助入口检查通过 |
| 人工查看 | 查看一张合成样张；Finder 通知以模拟调用验证，未实际触发系统通知 |

成片及文字对照是使用临时脚本完成的额外验证，不计入 143 项自动测试。重构阶段曾通过 135 项测试，性能优化后增加至 143 项。记录代表所覆盖的本机输入，不代表已验证所有 Python 版本、操作系统、字体和照片格式组合；环境版本见 [性能记录](performance-2026-09-10.json)。

调整绘制代码时，应先保留对照输出，再以相同输入、配置、字体和依赖环境比较尺寸、像素及元数据。运行时创建的 ICC 可能带不同时间字段，不宜只比较整个输出文件的哈希。Finder 阶段通知的实际显示还受系统通知权限和专注模式影响。

## 性能测量方法

基准脚本支持自选照片、布局、格式和压缩档位，并记录首次耗时、后续耗时中位数、文件字节数与进程峰值 RSS：

```bash
.venv/bin/python scripts/benchmark_render.py --photos /path/to/photo.jpg \
  --output-mode original --format jpg --iterations 3 --label original-jpeg
.venv/bin/python scripts/benchmark_render.py --photos /path/to/photo.png \
  --output-mode original --format png --png-compression fast --label png-fast
```

峰值 RSS 是整个进程的历史高水位；对比内存请每个场景单独启动进程，避免前一个场景污染数字。速度受图片内容、尺寸、运行环境及系统负载影响，不能直接将某次合成测试的倍数套用到所有照片。

## 本机性能测量

以下为 2.1.0 渲染优化的历史测量。

优化基线是 2026-09-10 完成内部重构、尚未实施五项性能优化时的本地源码快照；该快照包含当时未提交的改动，与 v2.0.0 标签源码不相同。前后使用相同输入、默认水印、保留色域、原尺寸、JPEG 100 / PNG balanced，关闭 GPS 查询。各场景在独立进程串行运行，首次调用单独记录，表内耗时为后续调用中位数；P3 场景测 2 次，RGBA16 拼接测 1 次，属于小样本性能检查。

| 场景 | 优化前耗时 | 优化后耗时 | 优化前峰值 RSS | 优化后峰值 RSS |
| --- | ---: | ---: | ---: | ---: |
| 6000 × 4000 P3 渐变测试图 → 原尺寸 JPEG | 7.443 秒 | 0.377 秒 | 617.5 MiB | 503.4 MiB |
| 两张 3000 × 2000 随机 16 位 RGBA 图 → 原尺寸 PNG 拼接 | 4.307 秒 | 1.984 秒 | 561.6 MiB | 326.5 MiB |

P3 输入是构造的渐变 JPEG，RGBA16 输入是固定随机种子的测试 PNG，不能代表所有真实照片。输入构造方式、环境、逐次耗时、输出体积和 RSS 原始数值保存在 [性能记录](performance-2026-09-10.json)。两种场景前后导出像素一致，RGBA16 的 alpha 也一致；输出文件体积分别保持 2,677,305 和 48,745,828 字节。

## Finder 双击安装器

`右键操作安装.command` / `右键操作卸载.command` 共用 `scripts/finder_setup.zsh`，从显式指定的 Python、项目虚拟环境及常见安装路径中选择 Python 3.10+。忽略 macOS 的 `/usr/bin/python3` 开发工具引导程序，避免触发无关安装；不安装 Homebrew、不调用 sudo。

`scripts/install_finder.py` 只依赖标准库。安装时先创建或验证项目 `.venv`，使用该环境安装 `requirements.txt` 并验证基础模块可导入（不导入 CairoSVG），成功后才修改工作流程。验证失败时给出排错指引。卸载直接处理工作流程，不导入图片处理依赖。

`.venv` 可由默认 venv 或用户创建的 Conda 前缀提供。校验要求解释器的 `sys.prefix` 与项目环境目录一致，并且属于 venv 或含 `conda-meta` 的 Conda 环境；仅有目录标记不能让外部 Python 通过。Conda 方案只需先准备 Python 和 pip，再由 pip 安装 `requirements.txt`，Finder 直接调用该环境的解释器，不依赖终端激活状态。移动 Conda 项目需重建环境，详见 [使用指南](usage.md#方案二conda无需-homebrew)。

生成的 `.workflow` 使用 Automator 的 `Run Shell Script` 动作，接收 Finder 的 `public.image` 路径参数。`plistlib` 生成 XML，`shlex.quote()` 转义项目路径，两个入口复用现有图片处理脚本：

| 快速操作 | 脚本 | 行为 |
| --- | --- | --- |
| 添加水印 | `watermark_combine_selected.sh` | 单张加水印，多张一次性合成 |
| 批量添加水印 | `watermark_batch_each.sh` | 使用 `--batch` 逐张导出 |

安装先暂存两个工作流程，再统一替换，并备份移除可识别的旧入口；失败时回滚。旧入口识别依赖管理标记或唯一的指定脚本调用，不只看名称。非托管同名目录持久备份，已托管目录仅保留事务回滚副本。

2.2.0 的「添加水印」使用 batch 类型，升级为 combine 时继承原始备份路径。重复安装不累积托管旧版，卸载恢复原始同名操作；恢复前校验备份范围和目录类型，同名符号链接不替换。

菜单顺序由 macOS 的 Finder 扩展设置管理，不由 `ACTIONS` 的声明顺序保证。用户可通过「自定…」拖动排序，安装器不修改系统排序偏好。

测试使用临时目录覆盖两个入口的参数传递、三个功能的实际导出、单入口及双入口旧版迁移、重复安装、备份恢复、事务回滚和路径保护。原生 Automator 测试验证生成的工作流程能够接收输入。双击入口另测解释器选择及安装/卸载参数转发。

```bash
.venv/bin/python -m unittest tests.test_finder_install -v
zsh -n 右键操作安装.command 右键操作卸载.command scripts/finder_setup.zsh
```

系统通知、文件访问和下载脚本的打开权限由 macOS 管理，安装器不绕过或自动授予权限。Automator 快速操作与 Finder 的集成说明见 [Apple 使用手册](https://support.apple.com/guide/automator/create-workflows-aut7cac58839/mac)。

### 历史发布验证

2.2.2：macOS 14.8.9 / Python 3.14.2 下 159 项测试通过；另在独立 Conda 环境中验证 SVG、单张、批量和合成导出，PATH 不含 Homebrew。验证平台为 Apple Silicon，Intel Mac 未实机复测。

### 2.2.1 发布验证

157 项测试通过，覆盖三个功能的实际导出、原生 Automator 执行及安装迁移。菜单排序和系统通知的实际显示未纳入自动 UI 测试。

安装器默认使用项目 `.venv`。开发或排错时可通过 `WATERMARK_PYTHON_BIN` 指定用于引导的 Python；该变量不代替安装器对项目虚拟环境的验证。Shell 入口支持 `WATERMARK_FINDER_PROGRESS=0` 关闭阶段通知：临时从终端调用时设置此环境变量，长期设置可调整 `watermark_batch_each.sh` 中同名变量的默认值，完成/失败提示仍保留。无需编辑 Automator 工作流程。

未发布改动记入 CHANGELOG 的「未发布」；发布时更新 `pyproject.toml` 版本和更新日志，核对各文档与实际行为一致。README 只保留概况和基础用法，不列更新清单。Git 标签及 GitHub Release 使用相同的 `vX.Y.Z`；中文 `.command` 入口必须以可执行权限保存到 Git，并在源码下载包中保留。
