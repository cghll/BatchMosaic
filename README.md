<div align="center">

# MaSai

**一个自己用的小工具：在一张图上框好位置，一键给整个文件夹的图片打上马赛克。**

<br>

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PySide6 / Qt 6](https://img.shields.io/badge/PySide6-Qt%206-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Pillow](https://img.shields.io/badge/Pillow-10%2B-8A6FBE?style=for-the-badge&logo=pypi&logoColor=white)](https://python-pillow.org/)
[![NumPy](https://img.shields.io/badge/NumPy-1.24%2B-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org/)
[![47 tests](https://img.shields.io/badge/Tests-47%20passed-6B4FBB?style=for-the-badge&logo=pytest&logoColor=white)]()
[![MIT](https://img.shields.io/badge/License-MIT-2EA44F?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](LICENSE)

</div>

## 这是什么

平时要给一批截图、素材图遮住同一个固定位置（账号、水印、头像、地址），
一张张打开图画方框实在太慢。所以我写了这个桌面小工具：**只框一次**，
区域按 0~1 的相对坐标记下来，整批图片按各自尺寸换算后批量导出，
原文件名、原格式、ICC / EXIF 都保留。

个人自用，不是通用图像编辑器：只做像素化马赛克，只扫一层文件夹，不记住上次的设置。
Windows + Python 3.10+，界面是 PySide6，工具栏右上角可以切深色 / 浅色主题。

## 快速开始

```bat
pip install -r requirements.txt
run.bat
```

或者 `python -m masai`。双击 `run.bat` 没反应时用 `run.bat debug` 看完整报错
（脚本会自动检查并安装缺失依赖）。

## 怎么用

1. 点「导入文件夹」，或把文件夹直接拖进窗口
2. 在参考图上按住左键拖出要遮住的矩形，可以框多个
3. 右侧滑块调马赛克颗粒度
4. 点右上角「导出…」，确认输出目录，等它跑完

画布支持滚轮缩放、中键平移、拖四角改范围、`Delete` 删除选中区域。
输出目录默认是 `原文件夹名_mosaic`，不能选原文件夹，**从不动原图**。

## 几个实现上的点

- 区域和块大小都按图像比例保存，不同尺寸自动换算；宽高比差太多会在列表里提示
- 块网格全局对齐，只统计并只改写框内像素，**框外逐字节不变**；重复处理幂等
- 先按 EXIF 方向摆正，导出保留原格式与 ICC / EXIF（方向标记归正为 1）
- 4 线程并行、可随时取消；动图 GIF、损坏文件跳过并在结束时列出原因
- `masai/core` 完全不依赖 Qt，算法可单独测试

算法取舍见 [设计稿](docs/superpowers/specs/2026-11-10-masai-mosaic-batch-design.md)，
界面设计与双主题 token 见 [DESIGN.md](DESIGN.md)。

## 测试

```bat
python -m pytest tests -q
```

47 个测试覆盖马赛克边界与不外溢、EXIF、导出格式、批量取消和界面冒烟。

## 许可证

[MIT](LICENSE) © 2026 cghll — 随便用，出问题别找我。
