# 展示样张

[返回 README](../README.md) · [使用指南](../docs/usage.md)

本目录图片用于查看排版效果和运行示例，已缩小并压缩：普通图最长边 1920 像素，超宽拼图最长边 3840 像素。

安装工具后，可在 Finder 选中样张，通过右键「快速操作」处理；也可在项目目录运行：

```bash
watermark-tool samples/horizontal1.jpg --include-gps-location false
```

成片保存在 `samples/`，重名自动编号，不覆盖已有样张。示例关闭地点联网查询。

样张保留拍摄参数、日期、GPS 和已有色彩配置，不适合比较原始画质。实际导出的尺寸和质量由所选参数决定。
