"""统一线性图标：单一来源的 SVG 路径，按当前主题着色后渲染成 QIcon / QPixmap。

Operate 模式不使用 emoji 或 Unicode 字形充当图标。所有图标 24×24 视框、
1.6 描边、圆角端点，笔画颜色由 Palette 注入，因此主题切换后图标同步变色。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 每个值都是 <svg> 的内部内容；坐标基于 24×24。
_PATHS: dict[str, str] = {
    "folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5'
        'a2 2 0 0 1-2-2z"/>'
    ),
    "folder_open": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"/>'
        '<path d="M2.6 10.2A2 2 0 0 1 4.5 9h16.8l-2.4 8.6A2 2 0 0 1 17 19H5'
        'a2 2 0 0 1-2-2z"/>'
    ),
    "fit": (
        '<path d="M9 3H5a2 2 0 0 0-2 2v4"/>'
        '<path d="M15 3h4a2 2 0 0 1 2 2v4"/>'
        '<path d="M9 21H5a2 2 0 0 1-2-2v-4"/>'
        '<path d="M15 21h4a2 2 0 0 0 2-2v-4"/>'
    ),
    "zoom_in": (
        '<circle cx="10.5" cy="10.5" r="6.5"/>'
        '<path d="M15.4 15.4 20.5 20.5"/>'
        '<path d="M10.5 7.5v6M7.5 10.5h6"/>'
    ),
    "zoom_out": (
        '<circle cx="10.5" cy="10.5" r="6.5"/>'
        '<path d="M15.4 15.4 20.5 20.5"/>'
        '<path d="M7.5 10.5h6"/>'
    ),
    "export": (
        '<path d="M12 15.5V3"/>'
        '<path d="m7 8 5-5 5 5"/>'
        '<path d="M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
        'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'
    ),
    "moon": (
        '<path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/>'
    ),
    "image": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<circle cx="8.5" cy="9.5" r="1.5"/>'
        '<path d="m3.5 17 4.7-4.7a1.5 1.5 0 0 1 2.1 0l2.2 2.2 2.3-2.3'
        'a1.5 1.5 0 0 1 2.1 0l3.6 3.6"/>'
    ),
    "trash": (
        '<path d="M4 7h16M9 7V4h6v3"/>'
        '<path d="M6.5 7 7.4 20h9.2L17.5 7"/>'
        '<path d="M10 11v5.5M14 11v5.5"/>'
    ),
    "clear": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="m9 9 6 6M15 9l-6 6"/>'
    ),
    "warning": (
        '<path d="M10.3 3.9 2.2 18a1.6 1.6 0 0 0 1.4 2.4h16.8a1.6 1.6 0 0 0 1.4-2.4'
        'L13.7 3.9a1.9 1.9 0 0 0-3.4 0z"/>'
        '<path d="M12 9v4.5"/>'
        '<path d="M12 17.1h.01"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M12 11v5.5M12 7.8h.01"/>'
    ),
    "grid": (
        '<rect x="3.5" y="3.5" width="7" height="7" rx="1"/>'
        '<rect x="13.5" y="3.5" width="7" height="7" rx="1"/>'
        '<rect x="3.5" y="13.5" width="7" height="7" rx="1"/>'
        '<rect x="13.5" y="13.5" width="7" height="7" rx="1"/>'
    ),
    "region": (
        '<rect x="3.5" y="3.5" width="17" height="17" rx="1.5"'
        ' stroke-dasharray="3 2.5"/>'
        '<path d="M12 9v6M9 12h6"/>'
    ),
    "check": '<path d="m4.5 12.5 5 5 10-11"/>',
    "chevron_up": '<path d="m6 14.5 6-6 6 6"/>',
    "chevron_down": '<path d="m6 9.5 6 6 6-6"/>',
    "layers": (
        '<path d="m12 3 9 5-9 5-9-5z"/>'
        '<path d="m3 12.5 9 5 9-5"/>'
    ),
    "download": (
        '<path d="M12 3v11.5M7.5 10.5 12 15l4.5-4.5"/>'
        '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>'
    ),
}

_STROKE_WIDTH = 1.6


def svg_source(name: str, color: str) -> str:
    """生成带主题色的独立 SVG 文档。"""
    body = _PATHS.get(name, _PATHS["info"])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{_STROKE_WIDTH}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{body}</svg>'
    )


def render_pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    """渲染为透明底像素图，尺寸即逻辑像素（高分屏由调用方按需传入）。"""
    renderer = QSvgRenderer(QByteArray(svg_source(name, color).encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


def icon(name: str, color: str, size: int = 18,
         disabled_color: str | None = None) -> QIcon:
    """构造带正常 / 禁用两种状态的 QIcon。"""
    result = QIcon()
    normal = render_pixmap(name, color, size)
    disabled = (render_pixmap(name, disabled_color, size)
                if disabled_color else None)
    for state in (QIcon.State.Off, QIcon.State.On):
        result.addPixmap(normal, QIcon.Mode.Normal, state)
        result.addPixmap(normal, QIcon.Mode.Active, state)
        result.addPixmap(normal, QIcon.Mode.Selected, state)
        if disabled is not None:
            result.addPixmap(disabled, QIcon.Mode.Disabled, state)
    return result


def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    """给 QLabel 之类直接用的位图。"""
    return render_pixmap(name, color, size)


# --------------------------------------------------------------------------
# QSS 里不能内嵌动态颜色，复选框勾、SpinBox 箭头这类子控件需要真实图片。
# 按主题写到临时目录，生成稳定 URL 供 build_stylesheet 引用。
# --------------------------------------------------------------------------
_ASSET_ROOT = Path(tempfile.gettempdir()) / "masai-qss"


def qss_assets(palette, size: int = 12) -> dict[str, str]:
    """返回 {名称: QSS url(...)}，同时把 PNG 落到磁盘。"""
    folder = _ASSET_ROOT / palette.key
    folder.mkdir(parents=True, exist_ok=True)
    specs = {
        "check": ("check", palette.accent_text, 12),
        "check_disabled": ("check", palette.text_muted, 12),
        "up": ("chevron_up", palette.text_sub, 9),
        "down": ("chevron_down", palette.text_sub, 9),
    }
    out: dict[str, str] = {}
    for key, (name, color, px) in specs.items():
        target = folder / f"{key}.png"
        render_pixmap(name, color, px).save(str(target), "PNG")
        out[key] = f'url("{target.as_posix()}")'
    return out
