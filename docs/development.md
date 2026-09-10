# 开发说明

[使用指南](usage.md) · [定制说明](customization.md) · [更新日志](../CHANGELOG.md)

本页供维护者查阅。对外入口为 `watermark_tool.LayoutConfig`、`watermark_tool.make_canvas`；根目录 `layout.py` 保留兼容入口。

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

`make_canvas()` 复制配置、校验路径，准备照片元数据、字体和水印，再统一计算布局。sRGB 路径调用 `_render_srgb_canvas()`，保留色域路径调用 `render_preserved_canvas()`；两者共用布局和 `annotations.py` 的绘制函数。

布局和标记修改应放在共享模块。`preserved.py` 不导入 `renderer.py`，也不重新准备字体、水印或布局。

基础依赖在 `pyproject.toml`、`requirements.txt` 和 `requirements.lock` 中保持一致。内置 Logo 使用 PNG，新增素材建议导出为高度至少 400 像素的透明 PNG。CairoSVG 仅用于可选 SVG，读取时才导入；安装方法见 [SVG 支持](usage.md#自定义-svg可选)。

部分 macOS NumPy wheel 的批量矩阵运算会导致色彩转换崩溃。`render_rgb_array()` 和 `srgb_to_color()` 将 RGB 数组展平为二维运算后恢复形状，保留原分块和公式。

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

- **元数据**：复用 `read_source_metadata()` 快照，避免重复打开文件；单个 EXIF 子 IFD 损坏时保留其他有效字段。延迟准备 PNG 不触发像素解码。
- **文字**：日期、旋转参数和文字签名统一使用 `draw_text_with_tracking()`。修改字距需核对实际绘制边界。
- **尺寸**：水印占用由 `get_mark_width()`、`get_annotation_extents()` 实时计算，避免重复状态失配。
- **保存**：通过 `atomic_output_path()` 写入同目录临时文件，编码成功才替换目标；失败清理临时文件，保留原输出。
- **默认值**：命令行默认值来自 `LayoutConfig`，测试应验证其遵循配置，允许用户修改 `config.py`。

## 渲染与缓存

保真后端只转换一次背景色，再填入目标数组。`AnnotationTiles` 为文字和标志触及的区域分配最多 256 × 256 的分块，避免全画布转换。字形先按全局整数原点和小数起点生成遮罩，再贴入分块，避免局部负坐标截断导致偏移。

来源与目标色域、位深及尺寸一致时直接复制 RGB，PNG 同时复制 alpha。缩放、混合色域和透明照片导出 JPEG 使用高精度合成。逐张解码并释放来源，但仍保留完整目标数组及必要的转换缓冲，并非恒定内存。

PNG 的 `fast / balanced / small` 对应压缩等级 `1 / 6 / 9`，只改变编码耗时与体积。两条后端都保留像素、透明度、色彩和元数据规则。

GPS 成功结果写入 SQLite：有效期 30 天、最多 2048 条，键由坐标保留 5 位小数和语言组成；失败或空值仅在内存缓存 60 秒。连接按次关闭，锁等待最多 0.2 秒，异常不阻断导出。目录创建权限为 0700，数据库为 0600；哈希不是加密。路径和开关见 [缓存说明](usage.md#缓存与运行速度)。

## Finder 双击安装器

两个 `.command` 文件共用 `scripts/finder_setup.zsh`。显式设置 `WATERMARK_PYTHON_BIN` 时只使用该解释器；否则依次查找 `/usr/local/bin/python3`、PATH 中的 `python3`、`/opt/homebrew/bin/python3`，要求 Python 3.10+。跳过 `/usr/bin/python3`，避免触发系统开发工具安装。

`scripts/install_finder.py` 直接用所选 `sys.executable` 安装 `requirements.txt` 并验证基础模块，不创建或激活环境，不自动修改已有 `.venv`。pip 或导入验证失败时不修改工作流程，不使用 sudo 或绕过受管理 Python 的限制。卸载仅依赖标准库。

生成的工作流程将安装时的 Python 绝对路径写入 `WATERMARK_PYTHON_BIN`，路径用 `shlex.quote()` 转义。右键运行时不再依赖终端的激活状态；解释器失效时提示重新安装，不静默切换其他 Python。

| 快速操作 | 脚本 | 行为 |
| --- | --- | --- |
| 添加水印 | `watermark_combine_selected.sh` | 单张加水印，多张合成 |
| 批量添加水印 | `watermark_batch_each.sh` | `--batch` 逐张导出 |

工作流程由 `plistlib` 生成，使用 Automator 的 `Run Shell Script` 动作接收 `public.image` 参数。先暂存两个入口再统一替换，失败回滚；可识别的旧入口备份移除。识别依赖管理标记或明确的旧脚本调用，不只看名称。

非托管同名目录持久备份，托管目录仅保留事务回滚副本。升级继承原始备份关系；卸载恢复原始同名操作前校验备份范围和目录类型，不替换同名符号链接。菜单排序、系统通知和文件访问权限由 macOS 管理。

阶段进度写入日志，Finder 通知最多每 2 秒一次。`WATERMARK_FINDER_PROGRESS=0` 可关闭阶段通知，完成/失败提示仍保留；长期设置可修改两个入口脚本中的同名默认值。

## 测试与验证

在项目目录用已有 Python 安装开发依赖并检查：

```bash
python3 -m pip install -e ".[dev]"
python3 -m unittest discover -v
python3 -m ruff check .
git diff --check
for script in *.command *.sh scripts/*.zsh; do zsh -n "$script" || break; done
python3 layout.py --help
python3 -m watermark_tool --help
```

安装器测试使用临时目录，不安装真实依赖或修改用户快速操作；原生 Automator 用临时工作流程验证参数传递。GPS 测试使用模拟响应，不请求真实地点服务。可单独运行 `python3 -m unittest tests.test_finder_install -v`。

调整绘制时，用相同输入、配置、字体和依赖对照尺寸、像素及元数据。ICC 可能包含不同时间字段，不宜只比较文件哈希。系统通知的显示和菜单排序需另做 UI 检查。

### 历史发布验证

以下为发布时记录，不代表本次重新执行或覆盖所有系统：

| 版本 | 验证范围 |
| --- | --- |
| 2.2.4 | 166 项通过，含已有 Python 安装路径、失败保护、实际导出、原生 Automator 和迁移恢复；Ruff、Shell 语法及文档链接检查通过。 |
| 2.2.3 | macOS / Python 3.14.2：163 项通过；无 CairoSVG 环境 162 项通过、1 项跳过；安装、wheel 素材、单张与合成导出通过。24 组色彩转换像素、16 组目标色域量化一致。 |
| 2.2.2 | macOS 14.8.9 / Python 3.14.2：159 项通过；独立 Conda 环境验证 SVG 及三种导出，PATH 不含 Homebrew。Intel Mac 未实机复测。 |
| 2.2.1 | 157 项通过，含实际导出、原生 Automator、安装迁移和卸载恢复。 |
| 2.1.0 | 143 项通过；36 组成片和 30 组文字对照的尺寸、像素及相关元数据一致。额外对照脚本不计入自动测试数。 |

2.2.3 独立 pip 验证使用 NumPy 2.5.3、Pillow 12.3.0、pillow-heif 1.7.0；Ruff、Shell 语法和文档链接检查通过。

## 性能测量方法

```bash
python3 scripts/benchmark_render.py --photos /完整路径/photo.jpg \
  --output-mode original --format jpg --iterations 3 --label original-jpeg
python3 scripts/benchmark_render.py --photos /完整路径/photo.png \
  --output-mode original --format png --png-compression fast --label png-fast
```

脚本记录首次耗时、后续中位数、文件大小及进程峰值 RSS。对比内存时每个场景单独启动进程；耗时受图片、硬件和系统负载影响。

## 本机性能测量

2.1.0 历史测量，基线为 2026-09-10 已完成重构、尚未优化的本地源码快照，含当时未提交的改动，并非 v2.0.0 标签。前后使用相同测试图、默认水印、保留色域、original、JPEG 100 / PNG balanced，关闭 GPS。各场景独立进程串行运行，下表为首次调用之后的耗时。

| 构造测试图 | 耗时：优化前 → 后 | 峰值 RSS：前 → 后 |
| --- | --- | --- |
| 6000 × 4000 P3 渐变图 → JPEG | 7.443 → 0.377 秒 | 617.5 → 503.4 MiB |
| 两张 3000 × 2000 随机 16 位 RGBA → PNG | 4.307 → 1.984 秒 | 561.6 → 326.5 MiB |

P3 后续测 2 次，RGBA16 测 1 次，仅为小样本检查。前后像素和文件体积一致，RGBA16 的 alpha 一致；结果不代表所有真实照片。输入构造、依赖版本和原始数值见 [性能记录](performance-2026-09-10.json)。

## 发布维护

未发布改动记入 CHANGELOG；发布时同步 `pyproject.toml`、更新日志、下载链接及 `vX.Y.Z` 标签。核对文档与实际行为，中文 `.command` 文件须保留可执行权限。README 保留上手入口和效果展示，开发细节放在本页。
