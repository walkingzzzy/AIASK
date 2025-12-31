# 应用图标

此目录用于存放Tauri应用图标。

## 所需图标文件

请准备以下图标文件：

- `32x32.png` - 32x32像素PNG图标
- `128x128.png` - 128x128像素PNG图标  
- `128x128@2x.png` - 256x256像素PNG图标（Retina显示屏）
- `icon.icns` - macOS应用图标
- `icon.ico` - Windows应用图标

## 生成图标

可以使用以下命令从一个1024x1024的PNG源图标生成所有格式：

```bash
npm run tauri icon path/to/source-icon.png
```

或者使用在线工具如 https://icon.kitchen/ 生成所需图标。
