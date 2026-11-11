# MaSai 界面设计约定

本文件是这次 UI 改造的 finish review 与交付记录。设计流程使用 `impeccable` skill v4.8.2
的 **Operate / redesign / code-led** 路径；产品事实与方向契约属于本地设计流程产物，
保留在本机，不纳入版本库。

---

## 1. 方向

**Thesis：窗口是照片的相框，不是旁边的仪表盘。**

旧界面把所有动作排成一行等权重的文字按钮，「导出」和「放大」看起来一样重要，
画布、面板、窗口底色几乎没有层级。这次保留三栏信息架构，重做视觉与交互层级：

- 三级中性表面构成明度阶梯：`shell`（应用栏/状态栏）→ `panel`（左右栏）→
  `canvas`（画布）。深色主题里画布最暗，让照片成为唯一的高亮内容。
- 唯一强调色（青蓝）只出现在四处：主操作「导出…」、当前选中项、画布区域框、
  进行中的进度/状态点。琥珀/红/绿只在真实状态出现。
- 顶部 52px 应用栏：左侧品牌 + 「导入文件夹」，中间三个纯图标视图控件，
  弹性留白，右侧主题切换 + 唯一的实心主操作。主操作永久可见，不随滚动或折叠消失。
- 切换主题时整套 chrome 一起换色，照片本身的光与色不变——这条「相框/主体」分界
  是这次设计的 signature move。

**用户方向（已确认）：** 保留三栏但「视觉+交互层级重做」；深浅两套主题都做，
在界面里放可切换按钮，不跟随系统。主题选择只在本次会话内有效，不持久化。

---

## 2. Token

所有颜色集中在 `masai/ui/theme.py`，界面代码里没有硬编码色值
（`grep '#[0-9a-fA-F]{6}'` 只会命中 theme.py）。

| 类别 | 值 |
| --- | --- |
| 字体 | 单一无衬线族 `"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", DengXian, sans-serif`，不引入展示字体 |
| 字号角色 | 11 / 12 / 13 / 14 / 16 px，分别对应徽标与元信息、字段标签、正文、品牌标题、空状态标题；角色固定，不按组件临时调整 |
| 间距 | 4 单位刻度：`xs 4 / sm 8 / md 12 / lg 16 / xl 24 / 2xl 32` |
| 控件 | 高 32px，圆角 6px，1px 分隔线；列表行 30 / 36 / 44px |
| 结构 | 应用栏 52px，状态栏 38px，左栏 248px，右栏 288px，画布弹性 |
| 图标 | 24×24 视框、1.6 描边、圆角端点、单一线性家族，颜色由当前 Palette 注入 |

### 双主题色板（关键 token）

| token | 深色 | 浅色 | 用途 |
| --- | --- | --- | --- |
| `shell` | `#12161C` | `#F6F8FB` | 应用栏、状态栏、窗口底 |
| `panel` | `#191E26` | `#FFFFFF` | 左右面板、浮层 |
| `canvas` | `#0C1016` | `#E7EBF1` | 画布底 |
| `text` | `#EAEFF6` | `#1B2532` | 主文本 |
| `text_sub` | `#A9B4C4` | `#4F5D6E` | 次文本、快捷键提示 |
| `text_muted` | `#8B97A9` | `#5D6B7E` | 元信息、禁用态 |
| `accent` | `#43B0F8` | `#0B76CC` | 主操作、选中、区域框、进度 |
| `warning` | `#E4AC55` | `#8A5805` | 宽高比警告 |
| `danger` | `#E87272` | `#BE3B34` | 校验错误、失败状态 |
| `success` | `#57C792` | `#187A50` | 导出成功状态点 |

浅色 `warning` 从初版 `#A86A08`（4.44:1，低于正文底线）调深到 `#8A5805`（6.04:1）；
`text_muted` 也从 `#67758A` 调深到 `#5D6B7E`，保证在 `panel_alt` 上仍达标。

---

## 3. 结构与状态

**First viewport**：48px 级应用栏 → 三栏（图片列表 / 参考图画布 / 区域与块大小）
→ 36px 级状态栏。画布上有右上缩放读数、左下操作提示、首次进入的空状态引导。

| 状态 | 表现 |
| --- | --- |
| 空 | 左栏「还没有图片」、右栏「还没有区域」、画布「框出要打码的位置」，三处都给下一步动作 |
| hover / focus / pressed | 按钮、工具按钮、列表行、滑块手柄、复选框均有独立态；焦点用强调色 1px 描边，不移除 |
| 选中 | 列表行强调色软底；画布区域实线 2px + 四角控制点 + 编号徽标；未选中区域虚线 1.6px |
| 禁用 | 主操作失去实心填充；导入、视图、右栏、画布在导出中整体禁用 |
| 进行中 | 状态点转强调色、进度条出现、取消按钮出现、状态文案给出 `处理中 2/3 · 文件名` |
| 完成 / 失败 / 取消 | 状态点绿 / 红 / 中性，文案给出张数与输出目录，失败清单列出文件名与原因 |
| 警告 | 宽高比不同的图片行：线性三角图标 **+** 琥珀色「宽高比不同」文字 + 完整 tooltip（图标与文字同时存在，不再用 `⚠` 字形顶替图标） |

**图标**：`masai/ui/icons.py` 用同一组 SVG 路径按主题色渲染 `QIcon` / `QPixmap`
（QtSvg）。QSS 无法内嵌动态颜色的子控件（复选框勾、SpinBox 箭头）由
`qss_assets()` 按主题生成 PNG 并写入临时目录后以 `url()` 引用。**没有 emoji 或
Unicode 字形充当图标。**

**主题机制**：`install_theme(app)` 在 `app.py` 创建 `QApplication` 后调用；
`ThemeManager.set_theme/toggle()` 重建 `QPalette` 与整窗 QSS，并发出 `changed(Palette)`。
`MainWindow` 监听它重刷所有图标与列表项，`ImageCanvas` 监听它重刷画布底、区域框、
控制点与拖拽临时框，`ExportDialog` 监听它重刷图标。测试直接构造窗口时
`theme_manager()` 懒加载兜底。

---

## 4. 保持不变的约束

- `masai/core/*` 仍完全不依赖 Qt；马赛克算法、导出规则、EXIF 处理、批量调度一行未改。
- 快捷键 `Ctrl+O` / `Ctrl+E` / `Delete`、拖放、取消语义、4 线程导出不变。
- 测试依赖的控件属性与方法名全部保留：`canvas`、`list_images`、`list_regions`、
  `slider_block`、`spin_block`、`act_export`、`lbl_regions`、`load_folder()`、
  `canvas._add_item()` / `_emit_regions()` 等。
- 主题是会话内的，不写入配置文件，符合产品「不记住上次设置」的约定。
- 视觉上新增了「每行删除区域」按钮、缩放读数、空状态、操作提示，但没有改变
  区域模型的归一化语义。

---

## 5. Finish review：检查过什么、修了什么

按 `craft-floor` 逐条核对，实际发现并修复的问题：

| # | 发现 | 修复 |
| --- | --- | --- |
| 1 | 浅色 `warning` 对白底 4.44:1，低于 4.5:1 | 调深到 `#8A5805`；`text_muted` 同步调深 |
| 2 | 三个图标按钮沿用「图标+文字」布局，文字被挤成 `…` | 设为 `ToolButtonIconOnly` |
| 3 | 图片列表的警告文字在 248px 栏里被截断，只剩图标 | 改成两行自绘列表项（文件名 / 尺寸+状态），图标与文字都在 |
| 4 | 自绘列表项与 item 原生文字双层叠字 | `item.setText("")`，语义信息移到 tooltip 与 `UserRole` |
| 5 | 选区用深色蒙版，把马赛克预览压灰 | 改为强调色薄染（alpha 22/10），主要靠边框、控制点、编号表意 |
| 6 | 浅色主题下画布提示条几乎看不见 | 浮层改 `panel` 底 + `border_strong` 描边，提示文字改用 `text_sub` |
| 7 | offscreen 截图全是豆腐块，且栏宽被撑成 439px | 验证脚本指定 `QT_QPA_FONTDIR`；字体栈补 `Noto Sans SC` / `DengXian`；面板补最小宽度 |
| 8 | 「空状态」截图其实是清空列表后的残留画布 | 验证脚本改为新建窗口截取真实空状态 |

### 对比度验证（WCAG，全部 ≥ 4.5:1）

对两套主题的 6 种文本/状态色 × 3 种表面（panel / panel_alt / shell）共 36 组计算，
加主操作按钮文字：

| 主题 | 最低组合 | 比值 | 主操作文字 |
| --- | --- | --- | --- |
| 深色 | 危险色 / 次级面 | 4.99:1 | 7.85:1 |
| 浅色 | 成功色 / 次级面 | 4.83:1 | 4.69:1 |

计算入口：`theme.contrast_ratio(fg, bg)`。

### 其它 craft-floor 项

- 没有 gradient text、glass、kicker、装饰性硬阴影、装饰性动画；状态切换靠颜色与
  边框，符合 Operate 模式的克制要求。
- 标准控件语义保留（按钮、滑块、复选框、列表、对话框按钮盒），没有陌生化改造。
- 焦点态在 QSS 里明确存在；禁用态不只变灰，主操作还会失去实心填充。
- 文案使用真实信息：真实文件名、真实像素尺寸、真实区域数、真实进度与失败原因。
- 没有 Unicode 字形当图标。

### 验证命令与结果

```
python -m pytest tests -q                     → 47 passed in 1.58s
python -m masai (offscreen 启动冒烟)          → 2.5s 后仍存活，stdout/stderr 为空
theme_manager().toggle() × 2                 → QSS 改变并恢复、画布底色 #0c1016 ↔ #e7ebf1、按钮文案 浅色 ↔ 深色
```

**Verdict：通过。** 功能回归、双主题切换、多状态渲染、对比度与图标状态都达到可交付标准。

---

## 6. 截图来源（provenance）

下表是 finish review 实际检查过的状态清单。截图由本地离屏脚本在
`QT_QPA_PLATFORM=offscreen`、`QT_QPA_FONTDIR=C:/Windows/Fonts`、Qt `Fusion` 样式下
用 `QWidget.grab()` 生成，全部 1280×840（对话框 540×290/318）；样例图由固定随机种子
`np.random.default_rng(7)` 生成，非用户数据。**截图与验证脚本是本地验证产物，未纳入版本库。**

| 文件 | 状态 |
| --- | --- |
| `dark-empty.png` | 深色，全新窗口，三处空状态、主操作禁用 |
| `dark-populated.png` | 深色，已导入 3 张、无区域 |
| `dark-selected.png` | 深色，1 个选中区域 + 马赛克预览 |
| `dark-busy.png` | 深色，导出中：进度条、取消按钮、面板禁用 |
| `dark-export-dialog.png` | 深色，导出对话框常态（主操作实心） |
| `dark-export-dialog-warning.png` | 深色，路径等于原目录，图标+文字警告、主操作禁用 |
| `light-populated.png` / `light-selected.png` | 浅色对应状态 |
| `light-export-dialog.png` | 浅色，导出对话框 |
| `light-empty.png` | 浅色，全新窗口空状态 |

`crop-*.png` 是 review 过程中为放大检查工具栏按钮与禁用态生成的临时裁切，不属于交付面。

---

## 7. 已知取舍

- 平台是 Windows 原生桌面，Impeccable 的 web decision page / comp pipeline 不适用；
  build-phase gate 由 offscreen Qt 截图 + 本文件内的 finish review 替代。`seed: none (unavailable)`。
- 不捆绑字体，依赖系统 UI 字体栈；Qt 的 offscreen 插件需要显式 `QT_QPA_FONTDIR`
  才能截到文字，真实 Windows 会话由系统字体数据库提供，无需该变量。
- 主题不持久化；重启回到深色。这是产品约定，不是遗漏。
- `QSS` 子控件图片按主题写入 `tempfile.gettempdir()/masai-qss/<key>/`；这是 Qt
  stylesheet 无法内嵌动态颜色的限制，文件很小且随主题覆盖更新。
