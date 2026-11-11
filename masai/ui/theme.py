"""设计 token 与双主题样式表。

Operate 模式采用 Restrained 色彩策略：三级中性表面（shell / panel / canvas）
构成明度阶梯，唯一的青蓝强调色只用于主操作、当前选中、状态指示和画布区域框。
所有颜色集中在此文件，界面代码不再出现硬编码色值。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

FONT_STACK = ('"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", '
              '"PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", '
              'DengXian, sans-serif')

# 4 单位基的间距刻度
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32}
CONTROL_H = 32
RADIUS = 6
APP_BAR_H = 52
STATUS_BAR_H = 38
LEFT_W = 248
RIGHT_W = 288


@dataclass(frozen=True)
class Palette:
    key: str
    shell: str            # 应用栏 / 窗口底
    panel: str            # 左右面板
    panel_alt: str        # 输入框、次级表面、tooltip
    canvas: str           # 画布底（深色主题里最暗，让图片成为主角）
    border: str           # 1px 分隔线
    border_strong: str    # 控件描边
    hover: str
    pressed: str
    text: str
    text_sub: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_press: str
    accent_soft: str      # 选中态底色（不透明，已与 panel 混合）
    accent_text: str      # 强调色按钮上的文字
    region: str           # 画布上的区域框
    region_fill: str
    handle: str           # 区域角控制点
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    success: str
    disabled_bg: str
    scroll_handle: str
    scroll_hover: str


DARK = Palette(
    key="dark",
    shell="#12161C", panel="#191E26", panel_alt="#222833", canvas="#0C1016",
    border="#2A313C", border_strong="#3A4351",
    hover="#262D38", pressed="#2E3643",
    text="#EAEFF6", text_sub="#A9B4C4", text_muted="#8B97A9",
    accent="#43B0F8", accent_hover="#63C0FA", accent_press="#2F98DE",
    accent_soft="#1C3346", accent_text="#07131E",
    region="#4CB8FA", region_fill="#142B39", handle="#F2F7FC",
    warning="#E4AC55", warning_soft="#382D1C",
    danger="#E87272", danger_soft="#3A2226",
    success="#57C792", disabled_bg="#1C222B",
    scroll_handle="#3A4351", scroll_hover="#4D5868",
)

LIGHT = Palette(
    key="light",
    shell="#F6F8FB", panel="#FFFFFF", panel_alt="#F1F4F8", canvas="#E7EBF1",
    border="#DCE2EA", border_strong="#C6CFDA",
    hover="#EDF1F6", pressed="#E3E9F0",
    text="#1B2532", text_sub="#4F5D6E", text_muted="#5D6B7E",
    accent="#0B76CC", accent_hover="#0964AE", accent_press="#085493",
    accent_soft="#E1EFFB", accent_text="#FFFFFF",
    region="#0B84E0", region_fill="#DCEEFB", handle="#FFFFFF",
    # 8A5805 对白底 6.04:1；旧值 A86A08 只有 4.44:1，低于正文底线。
    warning="#8A5805", warning_soft="#FBF1DE",
    danger="#BE3B34", danger_soft="#FBEAE9",
    success="#187A50", disabled_bg="#F1F4F8",
    scroll_handle="#C6CFDA", scroll_hover="#AAB7C6",
)

PALETTES = {"dark": DARK, "light": LIGHT}


def mix(foreground: str, background: str, ratio: float) -> str:
    """把前景色按 ratio 混到背景上，返回不透明 hex（避免 QSS 的 alpha 差异）。"""
    a, b = QColor(foreground), QColor(background)
    r = round(a.red() * ratio + b.red() * (1 - ratio))
    g = round(a.green() * ratio + b.green() * (1 - ratio))
    bl = round(a.blue() * ratio + b.blue() * (1 - ratio))
    return f"#{r:02x}{g:02x}{bl:02x}"


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 对比度，供验证阶段检查文本可读性。"""
    def lum(color: str) -> float:
        c = QColor(color)
        channels = []
        for v in (c.red(), c.green(), c.blue()):
            s = v / 255.0
            channels.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def build_stylesheet(p: Palette) -> str:
    """从 token 生成整窗 QSS。控件状态（hover/focus/pressed/disabled/selected）齐全。"""
    from .icons import qss_assets  # 延迟导入，避免 theme <-> icons 模块循环

    focus = mix(p.accent, p.panel, 0.55)
    a = qss_assets(p)
    return f"""
* {{
    font-family: {FONT_STACK};
}}
QWidget {{
    font-size: 13px;
    color: {p.text};
}}
QMainWindow, QDialog, QDialog#exportDialog {{
    background: {p.shell};
}}

/* ---------- 顶部应用栏 ---------- */
QToolBar#appBar {{
    background: {p.shell};
    border-bottom: 1px solid {p.border};
    padding: {SPACE['sm']}px {SPACE['md']}px;
    spacing: {SPACE['xs']}px;
}}
QToolBar#appBar::separator {{
    width: 1px; height: 20px;
    background: {p.border};
    margin: 0 {SPACE['sm']}px;
}}
QToolBar#appBar QToolButton {{
    min-height: {CONTROL_H}px;
    max-height: {CONTROL_H}px;
    padding: 0 {SPACE['md']}px;
    border: 1px solid transparent;
    border-radius: {RADIUS}px;
    background: transparent;
    color: {p.text_sub};
    font-size: 13px;
    font-weight: 500;
}}
QToolBar#appBar QToolButton:hover {{ background: {p.hover}; color: {p.text}; }}
QToolBar#appBar QToolButton:pressed {{ background: {p.pressed}; }}
QToolBar#appBar QToolButton:disabled {{ color: {p.text_muted}; background: transparent; }}
QToolBar#appBar QToolButton#iconAction {{
    min-width: {CONTROL_H}px; max-width: {CONTROL_H}px; padding: 0;
}}
QToolBar#appBar QToolButton#frameAction {{
    min-width: {CONTROL_H}px; max-width: {CONTROL_H}px; padding: 0;
    border-color: {p.border}; background: {p.panel};
}}
QToolBar#appBar QToolButton#frameAction:hover {{
    border-color: {p.border_strong}; background: {p.hover}; color: {p.text};
}}
QToolBar#appBar QToolButton#textAction {{
    border-color: {p.border}; background: {p.panel};
}}
QToolBar#appBar QToolButton#textAction:hover {{
    border-color: {p.border_strong}; background: {p.hover}; color: {p.text};
}}
QToolBar#appBar QToolButton#primaryAction {{
    background: {p.accent};
    border: 1px solid {p.accent};
    color: {p.accent_text};
    font-weight: 600;
    padding: 0 {SPACE['lg']}px;
}}
QToolBar#appBar QToolButton#primaryAction:hover {{
    background: {p.accent_hover}; border-color: {p.accent_hover};
}}
QToolBar#appBar QToolButton#primaryAction:pressed {{
    background: {p.accent_press}; border-color: {p.accent_press};
}}
QToolBar#appBar QToolButton#primaryAction:disabled {{
    background: {p.disabled_bg}; border-color: {p.border}; color: {p.text_muted};
}}
QToolBar#appBar QToolButton:focus {{
    border: 1px solid {focus};
}}

/* ---------- 面板 ---------- */
QWidget#leftPanel, QWidget#rightPanel {{
    background: {p.panel};
}}
QWidget#centerPanel, QWidget#canvasHost {{
    background: {p.canvas};
}}
QFrame#sectionRule {{
    background: {p.border};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLabel#brandTitle {{ font-size: 14px; font-weight: 600; color: {p.text}; }}
QLabel#brandSub {{ font-size: 11px; color: {p.text_muted}; }}
QLabel#sectionTitle {{
    font-size: 11px; font-weight: 600; color: {p.text_muted};
    padding: 0; margin: 0;
}}
QLabel#countBadge {{
    font-size: 11px; color: {p.text_sub};
    background: {p.panel_alt}; border: 1px solid {p.border};
    border-radius: 9px; padding: 1px 7px;
}}
QLabel#metaLabel, QLabel#hintLabel {{
    font-size: 11px; color: {p.text_muted};
}}
QLabel#shortcutLabel {{ font-size: 11px; color: {p.text_sub}; }}
QLabel#fieldLabel {{ font-size: 12px; color: {p.text_sub}; }}
QLabel#emptyTitle {{ font-size: 16px; font-weight: 600; color: {p.text}; }}
QLabel#emptyBody {{ font-size: 12px; color: {p.text_sub}; }}
QLabel#zoomBadge {{
    font-size: 11px; color: {p.text_sub};
    background: {p.panel_alt}; border: 1px solid {p.border};
    border-radius: 5px; padding: 5px 9px;
}}
QLabel#warnText {{ font-size: 11px; color: {p.danger}; }}
QLabel#okText {{ font-size: 11px; color: {p.success}; }}
QWidget#brandMark {{
    background: {p.accent_soft}; border: 1px solid {p.accent};
    border-radius: {RADIUS}px;
}}
QWidget#emptyGuide, QWidget#emptyList {{
    background: {p.panel}; border: 1px dashed {p.border_strong};
    border-radius: {RADIUS + 2}px;
}}
QWidget#overlayChip {{
    background: {p.panel}; border: 1px solid {p.border_strong};
    border-radius: {RADIUS}px;
}}
QWidget#statusDot {{
    background: {p.text_muted}; border-radius: 4px;
    min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px;
}}
QToolButton#rowDelete {{
    background: transparent; border: none; border-radius: 4px; padding: 0;
}}
QToolButton#rowDelete:hover {{ background: {p.danger_soft}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    min-height: {CONTROL_H}px;
    padding: 0 {SPACE['md']}px;
    border: 1px solid {p.border_strong};
    border-radius: {RADIUS}px;
    background: {p.panel_alt};
    color: {p.text};
    font-size: 13px;
}}
QPushButton:hover {{ background: {p.hover}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background: {p.pressed}; }}
QPushButton:disabled {{
    color: {p.text_muted}; background: {p.disabled_bg}; border-color: {p.border};
}}
QPushButton:focus {{ border: 1px solid {focus}; }}
QPushButton#ghostButton {{
    background: transparent; border-color: transparent; color: {p.text_sub};
}}
QPushButton#ghostButton:hover {{ background: {p.hover}; color: {p.text}; }}
QPushButton#ghostButton:disabled {{ background: transparent; color: {p.text_muted}; }}
QPushButton#primaryButton {{
    background: {p.accent}; border-color: {p.accent};
    color: {p.accent_text}; font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#primaryButton:pressed {{ background: {p.accent_press}; border-color: {p.accent_press}; }}
QPushButton#primaryButton:disabled {{
    background: {p.disabled_bg}; border-color: {p.border}; color: {p.text_muted};
}}
QPushButton#dangerButton:hover {{ color: {p.danger}; border-color: {p.danger}; }}

/* ---------- 列表 ---------- */
QListWidget {{
    background: {p.panel};
    border: 1px solid {p.border};
    border-radius: {RADIUS}px;
    padding: {SPACE['xs']}px;
    outline: none;
}}
QListWidget::item {{
    min-height: 30px;
    padding: 5px {SPACE['sm']}px;
    border-radius: 5px;
    color: {p.text_sub};
    border: none;
}}
QListWidget::item:hover {{ background: {p.hover}; color: {p.text}; }}
QListWidget::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QListWidget::item:disabled {{ color: {p.text_muted}; }}
QListWidget#regionList::item {{ min-height: 36px; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QSpinBox {{
    min-height: {CONTROL_H}px;
    padding: 0 {SPACE['sm']}px;
    background: {p.panel_alt};
    border: 1px solid {p.border};
    border-radius: {RADIUS}px;
    color: {p.text};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QLineEdit:hover, QSpinBox:hover {{ border-color: {p.border_strong}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled, QSpinBox:disabled {{
    color: {p.text_muted}; background: {p.disabled_bg};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px; background: transparent; border: none;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {p.hover};
}}
QSpinBox::up-arrow {{
    image: {a['up']}; width: 9px; height: 9px;
}}
QSpinBox::down-arrow {{
    image: {a['down']}; width: 9px; height: 9px;
}}
QSpinBox:disabled::up-arrow, QSpinBox:disabled::down-arrow {{
    image: none;
}}

/* ---------- 滑块 ---------- */
QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{
    height: 4px; background: {p.border}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::add-page:horizontal {{ background: {p.border}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0;
    background: {p.accent}; border: 2px solid {p.panel}; border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hover}; }}
QSlider::handle:horizontal:disabled {{ background: {p.border_strong}; }}
QSlider:disabled {{ background: transparent; }}

/* ---------- 复选框 ---------- */
QCheckBox {{ spacing: {SPACE['sm']}px; color: {p.text_sub}; font-size: 12px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p.border_strong}; border-radius: 4px;
    background: {p.panel_alt};
}}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{
    background: {p.accent}; border: 1px solid {p.accent};
    image: {a['check']};
}}
QCheckBox::indicator:checked:disabled {{
    background: {p.disabled_bg}; border-color: {p.border};
    image: {a['check_disabled']};
}}
QCheckBox::indicator:disabled {{ background: {p.disabled_bg}; border-color: {p.border}; }}

/* ---------- 进度 / 状态栏 ---------- */
QProgressBar {{
    min-height: 6px; max-height: 6px;
    background: {p.border}; border: none; border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QWidget#statusBar {{
    background: {p.shell}; border-top: 1px solid {p.border};
}}
QLabel#statusLabel {{ font-size: 12px; color: {p.text_sub}; }}

/* ---------- 滚动条 / 分隔条 / 提示 ---------- */
QScrollBar:vertical {{
    width: 10px; background: transparent; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.scroll_handle}; border-radius: 5px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.scroll_hover}; }}
QScrollBar:horizontal {{
    height: 10px; background: transparent; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p.scroll_handle}; border-radius: 5px; min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.scroll_hover}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:hover {{ background: {p.accent}; }}
QToolTip {{
    background: {p.panel_alt}; color: {p.text};
    border: 1px solid {p.border_strong};
    padding: 5px {SPACE['sm']}px; border-radius: 5px; font-size: 12px;
}}
QDialogButtonBox QPushButton {{ min-width: 92px; }}
"""


class ThemeManager(QObject):
    """全局主题：切换时重建 QSS 与 QPalette，并通知画布等自绘部件。"""

    changed = Signal(object)  # Palette

    def __init__(self, app: QApplication, key: str = "dark"):
        # 不把 QApplication 设为 QObject 父对象：测试里 QApplication 可能被销毁重建，
        # 有父对象时 Python wrapper 会随 C++ 对象一起失效。
        super().__init__()
        self._app = app
        self._key = key if key in PALETTES else "dark"

    @property
    def key(self) -> str:
        return self._key

    @property
    def palette(self) -> Palette:
        return PALETTES[self._key]

    def set_theme(self, key: str) -> None:
        if key not in PALETTES or key == self._key:
            return
        self._key = key
        self.apply()

    def toggle(self) -> str:
        self.set_theme("light" if self._key == "dark" else "dark")
        return self._key

    def apply(self) -> None:
        p = self.palette
        self._app.setPalette(self._build_qpalette(p))
        self._app.setStyleSheet(build_stylesheet(p))
        self.changed.emit(p)

    @staticmethod
    def _build_qpalette(p: Palette) -> QPalette:
        pal = QPalette()
        q = lambda value: QColor(value)  # noqa: E731
        pal.setColor(QPalette.Window, q(p.shell))
        pal.setColor(QPalette.Base, q(p.panel_alt))
        pal.setColor(QPalette.AlternateBase, q(p.panel))
        pal.setColor(QPalette.WindowText, q(p.text))
        pal.setColor(QPalette.Text, q(p.text))
        pal.setColor(QPalette.Button, q(p.panel_alt))
        pal.setColor(QPalette.ButtonText, q(p.text))
        pal.setColor(QPalette.Highlight, q(p.accent))
        pal.setColor(QPalette.HighlightedText, q(p.accent_text))
        pal.setColor(QPalette.ToolTipBase, q(p.panel_alt))
        pal.setColor(QPalette.ToolTipText, q(p.text))
        pal.setColor(QPalette.Disabled, QPalette.Text, q(p.text_muted))
        pal.setColor(QPalette.Disabled, QPalette.ButtonText, q(p.text_muted))
        pal.setColor(QPalette.Disabled, QPalette.WindowText, q(p.text_muted))
        pal.setColor(QPalette.Disabled, QPalette.Highlight, q(p.border_strong))
        return pal


_manager: ThemeManager | None = None


def install_theme(app: QApplication, key: str = "dark") -> ThemeManager:
    """应用入口显式安装；重复调用只更新主题。"""
    global _manager
    try:
        same = _manager is not None and _manager._app is app
    except RuntimeError:  # 旧 wrapper 的 C++ 对象已销毁
        same = False
    if not same:
        _manager = ThemeManager(app, key)
    else:
        _manager._key = key if key in PALETTES else "dark"
    _manager.apply()
    return _manager


def theme_manager() -> ThemeManager:
    """懒加载：offscreen 测试直接构造 MainWindow 时也能拿到主题。"""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("ThemeManager 需要 QApplication 实例")
    try:
        same = _manager is not None and _manager._app is app
    except RuntimeError:
        same = False
    if not same:
        install_theme(app)
    return _manager  # type: ignore[return-value]
