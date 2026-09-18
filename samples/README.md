# 展示样张

[返回 README](../README.md) · [使用指南](../docs/usage.md)

本目录图片用于查看排版效果和运行示例，已缩小并压缩：

- 根目录：原有照片和布局样张，普通图最长边 1920 像素，超宽拼图最长边 3840 像素。
- `colors/`：12 组配色展示图，统一为 1600 × 900，供 [README 配色画廊](../README.md#12-组精选配色)引用。

安装工具后，可在 Finder 选中样张，通过右键「快速操作」处理；也可在项目目录运行：

```bash
watermark-tool samples/horizontal1.jpg --include-gps-location false
```

成片保存在 `samples/`，重名自动编号，不覆盖已有样张。示例关闭地点联网查询。

根目录原有样张保留拍摄参数、日期、GPS 和已有色彩配置，不适合比较原始画质。实际导出的尺寸和质量由所选参数决定。

## 配色样张

`colors/` 使用根目录的 `horizontal1.jpg`，由工具以 video 版式导出后缩小。文件按 01–12 连续编号，与配置中的 `COLOR_PRESETS` 对应，保留原色 Logo；这些展示图不携带 EXIF / GPS 元数据，画面上仍能看到原有日期与拍摄参数。
配色数值统一维护在 [config.py](../src/watermark_tool/config.py)，适用画面见 README，选用步骤见 [定制说明](../docs/customization.md#背景与水印颜色)。
