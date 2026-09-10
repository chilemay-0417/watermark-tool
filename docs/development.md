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
| `png_decoder.py` | 16 位 PNG 原生解码与无编译器的 PyPNG 后备解码 |
| `raster.py` / `color.py` | 原生位深像素读取、高精度色彩转换 / sRGB 归一化与色彩规则 |
| `metadata.py` / `exif_gps.py` | 元数据读取与安全输出策略 / 拍摄参数和 GPS 地点的格式化 |
| `utils.py` | 日志与同目录临时文件原子替换 |
| `scripts/install_finder.py` | 安装、迁移、备份和卸载 Finder「添加水印」「批量添加水印」操作 |
| `scripts/finder_setup.zsh` | 查找本机 Python 与 Conda，检查版本和 pip，引导安装/卸载 |
| `scripts/install_runtime.py` | 将依赖安装到项目目录，注册终端命令并维护 zsh 搜索路径 |
| `scripts/python_runtime.py` | 选择匹配 Python ABI 的依赖目录，优先加载项目源码 |

## 共享流程与依赖

`make_canvas()` 复制配置、校验路径，准备照片元数据、字体和水印，再统一计算布局。sRGB 路径调用 `_render_srgb_canvas()`，保留色域路径调用 `render_preserved_canvas()`；两者共用布局和 `annotations.py` 的绘制函数。

`pyproject.toml` 将 `watermark-tool` 注册到 `watermark_tool.cli:run`。常规 pip 安装仍可注册此入口。双击安装生成调用项目 `layout.py` 的终端启动脚本，终端与 Finder 共用源码、配置和素材。

布局和标记修改应放在共享模块。`preserved.py` 不导入 `renderer.py`，也不重新准备字体、水印或布局。

基础依赖在 `pyproject.toml`、`requirements.txt` 和 `requirements.lock` 中保持一致。安装器使用 `pyproject.toml` 中的兼容版本范围；`requirements.lock` 是可选的固定版本复现清单，不是安装器的默认输入。Intel macOS 不强制安装缺少 wheel 的 pyspng，使用 PyPNG 逐行解码 16 位 PNG；其他平台优先使用 pyspng，无法导入时仍可回退。8 位 PNG 继续使用 Pillow。内置 Logo 使用 PNG，新增素材建议导出为高度至少 400 像素的透明 PNG。CairoSVG 仅用于可选 SVG，读取时才导入；安装方法见 [SVG 支持](usage.md#自定义-svg可选)。

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

两个 `.command` 文件共用 `scripts/finder_setup.zsh`。显式设置 `WATERMARK_PYTHON_BIN` 时只使用该解释器；否则先查找 PATH 中的 `python3`，再查找 Conda 环境变量、本机常见 Python 路径、官网 `/Library/Frameworks/Python.framework/Versions/` 目录、PATH 中的 conda 所属目录、常见 Conda 安装位置及 `~/.conda/environments.txt`，要求 Python 3.10+。安装时同时检查 pip，卸载不要求 pip；全程不新建或激活 Conda 环境。跳过 `/usr/bin/python3`，避免触发系统开发工具安装。

`scripts/install_runtime.py` 用现有 Python 执行 `pip install --target`，将工具依赖安装到项目 `.watermark-deps/`，按 Python ABI 和 CPU 架构区分。不新建解释器环境，不向 Homebrew 的全局包目录写入，也不使用 `--break-system-packages`。覆盖用户 pip 配置中的 `user`、`prefix`、`root` 和 `require-virtualenv`，保留软件源、代理与证书设置，避免已有 pip 偏好改变安装目标。采用 pip 官方支持的 [目标目录安装](https://pip.pypa.io/en/stable/cli/pip_install/#cmdoption-t)。

先在临时目录安装并验证依赖，再替换本工具的旧依赖；下载或验证失败时保留旧安装。依赖清单与 Python 版本未变且验证通过时直接复用。`scripts/python_runtime.py` 让 `layout.py` 和 Finder 子进程优先加载项目源码及对应依赖目录，项目移动后源码与素材仍保持相对路径。

安装器生成 `~/.local/bin/watermark-tool`，并向 zsh 配置文件追加带标记的 PATH 设置，原文件首次修改前备份。重复安装更新启动路径，不重复追加；遇到其他工具的同名命令时保留并报错。默认配置文件为 `~/.zshrc`，已有 `ZDOTDIR` 时遵循其位置，原配置备份在同目录的 `.watermark-backup` 文件中。`--cli-only` 仅安装命令，`--svg` 同时安装可选 SVG 支持。

双击卸载及 `--uninstall` 同时移除托管工作流和终端启动脚本；`--uninstall-finder-only` 保留终端入口。两种卸载均只依赖标准库，不调用 pip。终端脚本需与安装器生成的结构完整匹配才删除；符号链接和用户改写的脚本保留。只清理精确匹配的连续 PATH 标记/设置行，保留其余配置、文件权限、配置文件符号链接及备份；若 `.local/bin` 还有其他文件，则保留共用 PATH。配置清理失败时保留启动脚本，启动脚本删除失败时回滚配置。源码、个人素材、照片和项目依赖不自动删除。

安装后总是打印首次启用指引。双击入口传入 `--open-settings`，仅在安装前缺少任一托管操作时尝试打开设置。macOS 15 及以上打开“登录项与扩展”，旧系统尝试 `Extensions.prefPane`，失败时退回系统设置主界面；所有打开操作均有超时且失败不改变安装结果。安装器不会把服务刷新等同于 Finder 已启用；手动路径为“选中照片 → 快速操作 → 自定义 → 勾选两项”。

生成的工作流程将安装时的 Python 绝对路径写入 `WATERMARK_PYTHON_BIN`，路径用 `shlex.quote()` 转义。右键运行时不再依赖终端的激活状态；解释器失效时提示重新安装，不静默切换其他 Python。

| 快速操作 | 脚本 | 行为 |
| --- | --- | --- |
| 添加水印 | `watermark_combine_selected.sh` | 单张加水印，多张合成 |
| 批量添加水印 | `watermark_batch_each.sh` | `--batch` 逐张导出 |

工作流程由 `plistlib` 生成，使用 Automator 的 `Run Shell Script` 动作接收 `public.image` 参数。先暂存两个入口再统一替换，失败回滚；可识别的旧入口备份移除。识别依赖管理标记或明确的旧脚本调用，不只看名称。

非托管同名目录持久备份，托管目录仅保留事务回滚副本。升级继承原始备份关系；卸载恢复原始同名操作前校验备份范围和目录类型，不替换同名符号链接。菜单排序、系统通知和文件访问权限由 macOS 管理。

阶段进度写入日志，Finder 通知最多每 2 秒一次。`WATERMARK_FINDER_PROGRESS=0` 可关闭阶段通知，完成/失败提示仍保留；长期设置可修改两个入口脚本中的同名默认值。

## 测试与验证

在项目目录用已有 Python 将开发依赖安装到本地目录后检查：

```bash
python3 -m pip install --target .dev-packages ".[dev]"
PYTHONPATH="src:.dev-packages" python3 -m unittest discover -v
PYTHONPATH="src:.dev-packages" python3 -m ruff check .
git diff --check
for script in *.command *.sh scripts/*.zsh; do zsh -n "$script" || break; done
watermark-tool --help
PYTHONPATH="src:.dev-packages" python3 -m watermark_tool --help
```

自动测试中的安装器使用临时目录和模拟下载，不安装真实依赖或修改用户快速操作；发布前另做真实依赖安装与临时用户目录验收。原生 Automator 用临时工作流程验证参数传递。GPS 测试使用模拟响应，不请求真实地点服务。可单独运行 `PYTHONPATH="src:.dev-packages" python3 -m unittest tests.test_finder_setup tests.test_finder_install tests.test_install_runtime -v`。

首次安装回归必须使用无托管工作流、无终端命令的临时用户目录，覆盖引导、重复安装、仅移除 Finder 和完整移除入口，并验证卸载后 shell 无法找到命令。首次 Finder 勾选的实际显示需在全新 macOS 用户中验收；已有用户的卸载重装不能替代该检查。macOS 15.7.7 的设置分支通过模拟系统版本测试，实际显示仍需对应系统验证。

调整绘制时，用相同输入、配置、字体和依赖对照尺寸、像素及元数据。ICC 可能包含不同时间字段，不宜只比较文件哈希。系统通知的显示和菜单排序需另做 UI 检查。

### 2.2.6 发布验证

2026-09-10，在 macOS 14.8.9 / Apple Silicon / Python 3.14.2 上验证本次安装与卸载修复。完整测试在临时项目副本中执行，200 项全部通过（17.645 秒），包含原生 Automator 参数传递。为允许 macOS 执行临时工作流，本次完整测试在沙箱外运行；没有安装或卸载真实用户的工具入口。

- 在无托管工作流、无终端启动脚本的临时用户目录中，验证首次安装引导、重复安装不重复打开设置、仅卸载 Finder、重新安装、默认卸载全部入口及重复卸载。卸载后独立 zsh 进程无法找到工具命令。
- 验证非托管命令、已修改启动脚本、二进制文件、符号链接、用户修改过的 PATH 及共用 `.local/bin` 的保留；覆盖 `ZDOTDIR`、配置文件权限、符号链接、换行和失败回滚。
- 模拟 macOS 15.7.7，验证“登录项与扩展”设置入口及勾选说明；设置无法打开时保留手动指引，不影响安装结果。
- 源码、脚本和测试的 Ruff 检查、全部 Shell 入口语法、安装器参数帮助及本地 Markdown 链接/锚点检查通过。

本次没有在 macOS 15.7.7 或全新系统用户中验收实际勾选界面，也没有重新执行多 Python / Intel / 依赖安装矩阵。首次启用仍可能需要手动勾选，不应以本版测试推断自动启用或跨平台实机兼容性。照片渲染模块、依赖范围和 README 未改动。机器可读记录见 [2.2.6 验证记录](release-2.2.6-validation.json)。

### 2.2.5 发布验证

2026-09-10，在 macOS 14.8.9 / Apple Silicon 上对比 `v2.2.4`，审阅全部 6 份 Markdown、LICENSE、性能记录、依赖清单与安装/运行入口。

| 实际解释器 | 依赖安装与完整自动测试 |
| --- | --- |
| Homebrew Python 3.14.2 | 186 项通过 |
| Miniconda Python 3.13.11 | 185 项通过，1 项可选 SVG 测试因未安装而跳过 |
| Conda Python 3.11.11 | 185 项通过，1 项可选 SVG 测试因未安装而跳过 |
| Conda Python 3.10.20 | 185 项通过，1 项可选 SVG 测试因未安装而跳过 |

四种解释器均实际安装到独立 ABI 依赖目录，在临时用户目录验证重复安装、命令帮助、目录外 PNG 导出、两种快速操作注册和卸载；调用命令时清除 Conda 激活变量，PATH 仅含系统目录。完整自动测试还覆盖 Finder 单张/批量/合成实际导出、原生 Automator 参数传递、失败回滚、特殊路径和旧入口迁移。

- Python 3.10–3.14 × Apple Silicon / Intel 共 10 组依赖矩阵，按目标环境计算依赖标记后执行 pip 二进制包解析，全部通过；不要求编译依赖。
- 强制禁用 pyspng 后运行完整测试，并单独对照 16 位灰度、灰度透明、RGB、RGBA 和颜色键透明的原始样本，验证后备解码保留精度。
- `v2.2.4` 与本版对照 18 组输出（三种布局 × JPEG/PNG × 单横图/单竖图/双图）；尺寸、解码像素、EXIF 和 ICC 色彩定义一致，比较 ICC 时忽略生成时间。
- 启用 `PIP_USER=1`、`PIP_REQUIRE_VIRTUALENV=1` 和其他 `PIP_PREFIX` 时，实际安装仍限制在项目目录；新增 SVG 安装与原生 Cairo 渲染验证通过。
- 全部本地文档链接/锚点、代码块、11 条命令行示例、Ruff、Shell 语法与 Git 差异检查通过。

Intel Mac 和 Python 官网安装版未实机运行；Python 3.12 仅验证依赖包解析，未运行全套功能测试。官网安装目录、未激活 Conda、缺少 pip 和不支持的 Python 使用模拟测试验证发现与提示逻辑。上述结果不等于所有系统版本、网络、权限与自定义 Python 配置均已验证。机器可读依赖矩阵见 [发布验证记录](release-2.2.5-validation.json)。

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
