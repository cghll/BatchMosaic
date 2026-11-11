"""画布：显示参考图、拖拽框选/编辑区域、实时预览马赛克。"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..core.mosaic import mosaic_array
from ..core.regions import (
    Region,
    block_pixels,
    region_from_pixels,
    region_to_pixels,
)
from .theme import Palette, theme_manager

MIN_DRAW_PX = 3.0
HANDLE_SIZE = 9
MIN_ZOOM = 0.02
MAX_ZOOM = 32.0


def _arr_to_qimage(arr: np.ndarray, fmt: QImage.Format) -> QImage:
    arr = np.ascontiguousarray(arr)
    height, width = arr.shape[:2]
    buf = arr.tobytes()
    return QImage(buf, width, height, arr.strides[0], fmt).copy()


def array_to_qimage(arr: np.ndarray) -> QImage:
    """按数组维度/通道数选择正确的 QImage 格式。"""
    if arr.ndim == 2:
        return _arr_to_qimage(arr, QImage.Format_Grayscale8)
    if arr.shape[2] == 4:
        return _arr_to_qimage(arr, QImage.Format_RGBA8888)
    return _arr_to_qimage(arr, QImage.Format_RGB888)


def pil_to_qimage(img: Image.Image) -> QImage:
    mode = img.mode
    if mode == "RGBA":
        return _arr_to_qimage(np.array(img), QImage.Format_RGBA8888)
    if mode == "L":
        return _arr_to_qimage(np.array(img), QImage.Format_Grayscale8)
    if mode == "RGB":
        return _arr_to_qimage(np.array(img), QImage.Format_RGB888)
    if mode in ("LA", "P", "PA"):
        return pil_to_qimage(img.convert("RGBA"))
    return pil_to_qimage(img.convert("RGB"))


def display_image(img: Image.Image) -> Image.Image:
    """转成画布可显示的模式。"""
    if img.mode in ("RGB", "RGBA", "L"):
        return img
    if img.mode in ("LA", "P", "PA"):
        return img.convert("RGBA")
    return img.convert("RGB")


class _HandleItem(QGraphicsRectItem):
    """角上的缩放控制点（尺寸不随缩放变化）。"""

    def __init__(self, corner: int, parent: "RegionItem", palette: Palette):
        half = HANDLE_SIZE / 2.0
        super().__init__(-half, -half, HANDLE_SIZE, HANDLE_SIZE, parent)
        self.corner = corner
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(20)
        self.setCursor(Qt.SizeFDiagCursor if corner in (0, 3) else Qt.SizeBDiagCursor)
        self.setVisible(False)
        self.set_palette(palette)

    def set_palette(self, palette: Palette) -> None:
        pen = QPen(QColor(palette.accent), 1.6)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(palette.handle)))
        self.update()


class RegionItem(QGraphicsRectItem):
    """一个可移动、可缩放的马赛克区域。"""

    def __init__(self, index: int, rect: QRectF, bounds: QRectF,
                 palette: Palette):
        super().__init__(QRectF(0, 0, rect.width(), rect.height()))
        self.setPos(rect.topLeft())
        self._bounds = QRectF(bounds)
        self._palette = palette
        self.index = index
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(10)
        self.handles = [_HandleItem(i, self, palette) for i in range(4)]
        self._layout_handles()
        self._refresh_style()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._refresh_style()
        for handle in self.handles:
            handle.set_palette(palette)
        self.update()

    def _refresh_style(self) -> None:
        """选中态与常态用实线/虚线 + 填充深浅区分，不只靠四个控制点。"""
        p = self._palette
        selected = self.isSelected()
        pen = QPen(QColor(p.accent if selected else p.region),
                   2.0 if selected else 1.6,
                   Qt.SolidLine if selected else Qt.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        # 用强调色薄染而不是深色蒙版，避免把马赛克预览压灰
        fill = QColor(p.region)
        fill.setAlpha(22 if selected else 10)
        self.setBrush(QBrush(fill))

    # ---- 几何 ----
    def scene_rect(self) -> QRectF:
        return QRectF(self.pos().x(), self.pos().y(),
                      self.rect().width(), self.rect().height())

    def set_scene_rect(self, rect: QRectF) -> None:
        r = self._clamp(rect)
        self.prepareGeometryChange()
        self.setRect(QRectF(0, 0, r.width(), r.height()))
        self.setPos(r.topLeft())
        self._layout_handles()

    def _clamp(self, rect: QRectF) -> QRectF:
        b = self._bounds
        w = min(max(rect.width(), 1.0), b.width())
        h = min(max(rect.height(), 1.0), b.height())
        x = min(max(rect.x(), b.left()), b.right() - w)
        y = min(max(rect.y(), b.top()), b.bottom() - h)
        return QRectF(x, y, w, h)

    def _layout_handles(self) -> None:
        r = self.rect()
        for handle, point in zip(self.handles, (r.topLeft(), r.topRight(),
                                                r.bottomLeft(), r.bottomRight())):
            handle.setPos(point)

    def _set_handles_visible(self, visible: bool) -> None:
        for handle in self.handles:
            handle.setVisible(visible)

    # ---- 交互 ----
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            b = self._bounds
            point = QPointF(value)
            point.setX(min(max(point.x(), b.left()), b.right() - self.rect().width()))
            point.setY(min(max(point.y(), b.top()), b.bottom() - self.rect().height()))
            return point
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._set_handles_visible(bool(value))
            self._refresh_style()
            self.update()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(self.rect())
        label = str(self.index)
        metrics = painter.fontMetrics()
        box = metrics.boundingRect(label).adjusted(-5, -2, 5, 2)
        box.moveTopLeft(self.rect().topLeft().toPoint() + QPoint(5, 5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(self._palette.accent)))
        painter.drawRoundedRect(QRectF(box), 3, 3)
        painter.setPen(QPen(QColor(self._palette.accent_text)))
        painter.drawText(box, Qt.AlignCenter, label)


class ImageCanvas(QGraphicsView):
    """参考图画布。区域以归一化坐标对外交流。"""

    regionsEdited = Signal(list)      # list[Region]
    regionSelected = Signal(int)      # 选中区域序号（-1 表示无）
    zoomChanged = Signal(float)       # 当前缩放倍率，1.0 = 100%

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = theme_manager().palette
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(self._palette.canvas)))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        theme_manager().changed.connect(self.apply_palette)

        self._pix = QGraphicsPixmapItem()
        self._pix.setZValue(-10)
        self._pix.setTransformationMode(Qt.SmoothTransformation)
        self._scene.addItem(self._pix)

        self._pil: Image.Image | None = None
        self._arr: np.ndarray | None = None
        self._size: tuple[int, int] = (0, 0)
        self._block_fraction = 0.02
        self._items: list[RegionItem] = []
        self._temp: QGraphicsRectItem | None = None
        self._draw_start: QPointF | None = None
        self._resize: tuple[RegionItem, QPointF] | None = None
        self._panning = False
        self._pan_last = QPointF()

    # ---------- 主题 ----------
    def apply_palette(self, palette: Palette) -> None:
        """主题切换时重刷画布底、区域框、控制点与正在拖拽的临时框。"""
        self._palette = palette
        self.setBackgroundBrush(QBrush(QColor(palette.canvas)))
        for item in self._items:
            item.set_palette(palette)
        if self._temp is not None:
            pen = QPen(QColor(palette.region), 1.6, Qt.DashLine)
            pen.setCosmetic(True)
            self._temp.setPen(pen)
            fill = QColor(palette.region_fill)
            fill.setAlpha(48)
            self._temp.setBrush(QBrush(fill))
        self.viewport().update()

    # ---------- 图像 ----------
    def set_image(self, image: Image.Image, regions: Sequence[Region],
                  block_fraction: float) -> None:
        self._block_fraction = block_fraction
        shown = display_image(image)
        self._pil = shown
        self._arr = np.array(shown)
        self._size = shown.size
        self._pix.setPixmap(QPixmap.fromImage(pil_to_qimage(shown)))
        self._scene.setSceneRect(QRectF(0, 0, shown.size[0], shown.size[1]))
        self._clear_items()
        for region in regions:
            px = region_to_pixels(region, *shown.size)
            if px is None:
                continue
            self._add_item(QRectF(px[0], px[1], px[2] - px[0], px[3] - px[1]))
        self._renumber()
        self.refresh_preview()
        self.fit_view()

    def has_image(self) -> bool:
        return self._pil is not None

    def image_size(self) -> tuple[int, int]:
        return self._size

    def current_image(self) -> Image.Image | None:
        return self._pil

    # ---------- 区域 ----------
    def regions(self) -> list[Region]:
        width, height = self._size
        if width <= 0 or height <= 0:
            return []
        out = []
        for item in self._items:
            r = item.scene_rect()
            out.append(region_from_pixels(r.left(), r.top(), r.right(), r.bottom(),
                                          width, height))
        return out

    def clear_regions(self, emit: bool = True) -> None:
        self._clear_items()
        self.refresh_preview()
        if emit and self._size[0] > 0:
            self.regionsEdited.emit(self.regions())

    def remove_selected(self) -> None:
        selected = [it for it in self._items if it.isSelected()]
        if not selected:
            return
        for item in selected:
            self._scene.removeItem(item)
            self._items.remove(item)
        self._renumber()
        self.refresh_preview()
        self.regionsEdited.emit(self.regions())

    def select_region(self, index: int) -> None:
        for i, item in enumerate(self._items):
            item.setSelected(i == index)

    def set_block_fraction(self, fraction: float) -> None:
        self._block_fraction = fraction
        self.refresh_preview()

    def refresh_preview(self) -> None:
        if self._pil is None or self._arr is None:
            return
        width, _ = self._size
        rects = []
        for item in self._items:
            r = item.scene_rect()
            rects.append((int(round(r.left())), int(round(r.top())),
                          int(round(r.right())), int(round(r.bottom()))))
        if rects:
            block = block_pixels(self._block_fraction, width)
            out = mosaic_array(self._arr, rects, block, copy=True)
            self._pix.setPixmap(QPixmap.fromImage(array_to_qimage(out)))
        else:
            self._pix.setPixmap(QPixmap.fromImage(pil_to_qimage(self._pil)))

    # ---------- 视图 ----------
    def fit_view(self) -> None:
        if self._size[0] <= 0:
            return
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        if self.transform().m11() > 1.0:
            self.resetTransform()
            self.centerOn(self._scene.sceneRect().center())
        self.zoomChanged.emit(self.transform().m11())

    def zoom_by(self, factor: float) -> None:
        current = self.transform().m11()
        target = current * factor
        if target < MIN_ZOOM or target > MAX_ZOOM:
            return
        self.scale(factor, factor)
        self.zoomChanged.emit(self.transform().m11())

    def wheelEvent(self, event) -> None:
        if not self.has_image():
            return
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

    # ---------- 内部 ----------
    def _bounds_rect(self) -> QRectF:
        return QRectF(0, 0, self._size[0], self._size[1])

    def _add_item(self, rect: QRectF) -> RegionItem:
        item = RegionItem(len(self._items) + 1, rect, self._bounds_rect(),
                          self._palette)
        self._scene.addItem(item)
        self._items.append(item)
        return item

    def _clear_items(self) -> None:
        for item in self._items:
            self._scene.removeItem(item)
        self._items.clear()

    def _renumber(self) -> None:
        for i, item in enumerate(self._items, 1):
            item.index = i
            item.update()

    def _scale(self) -> float:
        return max(self.transform().m11(), 1e-6)

    def _clamp_point(self, point: QPointF) -> QPointF:
        b = self._bounds_rect()
        return QPointF(min(max(point.x(), b.left()), b.right()),
                       min(max(point.y(), b.top()), b.bottom()))

    def _region_item_at(self, point: QPointF) -> RegionItem | None:
        for item in reversed(self._items):
            if item.contains(item.mapFromScene(point)):
                return item
        return None

    def _handle_at(self, point: QPointF):
        tolerance = (HANDLE_SIZE + 6) / self._scale()
        for item in reversed(self._items):
            if not item.isSelected():
                continue
            for handle in item.handles:
                if not handle.isVisible():
                    continue
                if (handle.scenePos() - point).manhattanLength() <= tolerance:
                    return item, handle.scenePos()
        return None

    def _emit_regions(self) -> None:
        self._renumber()
        self.refresh_preview()
        self.regionsEdited.emit(self.regions())

    # ---------- 鼠标 ----------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self.has_image():
            self._panning = True
            self._pan_last = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self.has_image():
            point = self.mapToScene(event.position().toPoint())
            hit = self._handle_at(point)
            if hit is not None:
                item, anchor = hit
                self._resize = (item, anchor)
                event.accept()
                return
            item = self._region_item_at(point)
            if item is not None:
                super().mousePressEvent(event)
                self.regionSelected.emit(self._items.index(item))
                return
            if self._bounds_rect().contains(point):
                self._draw_start = self._clamp_point(point)
                self._temp = QGraphicsRectItem(QRectF(self._draw_start, self._draw_start))
                pen = QPen(QColor(self._palette.region), 1.6, Qt.DashLine)
                pen.setCosmetic(True)
                self._temp.setPen(pen)
                fill = QColor(self._palette.region_fill)
                fill.setAlpha(48)
                self._temp.setBrush(QBrush(fill))
                self._temp.setZValue(30)
                self._scene.addItem(self._temp)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return

        if self._temp is not None and self._draw_start is not None:
            point = self._clamp_point(self.mapToScene(event.position().toPoint()))
            self._temp.setRect(QRectF(self._draw_start, point).normalized())
            event.accept()
            return

        if self._resize is not None:
            item, anchor = self._resize
            point = self._clamp_point(self.mapToScene(event.position().toPoint()))
            item.set_scene_rect(QRectF(anchor, point).normalized())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if self._temp is not None:
            rect = self._temp.rect().normalized()
            self._scene.removeItem(self._temp)
            self._temp = None
            self._draw_start = None
            if rect.width() >= MIN_DRAW_PX and rect.height() >= MIN_DRAW_PX:
                item = self._add_item(rect)
                item.setSelected(True)
                self._emit_regions()
            event.accept()
            return

        if self._resize is not None:
            self._resize = None
            self._emit_regions()
            event.accept()
            return

        super().mouseReleaseEvent(event)
        self.regionSelected.emit(
            next((i for i, it in enumerate(self._items) if it.isSelected()), -1))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_selected()
            event.accept()
            return
        super().keyPressEvent(event)