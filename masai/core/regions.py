"""归一化马赛克区域模型。

区域坐标以图像宽高的 0~1 相对比例存储，因此同一套区域可以套用到
任意尺寸的图片上；块大小同样以「相对图像宽度」的比例存储。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

MIN_BLOCK_PX = 2
DEFAULT_BLOCK_PX = 16
MAX_BLOCK_PX = 256
ASPECT_TOLERANCE = 0.02  # 宽高比差异超过 2% 视为可能错位


@dataclass(frozen=True)
class Region:
    """0~1 相对坐标，x/y 为左上角，w/h 为宽高。"""

    x: float
    y: float
    w: float
    h: float

    def clamped(self) -> "Region":
        x0 = min(max(self.x, 0.0), 1.0)
        y0 = min(max(self.y, 0.0), 1.0)
        x1 = min(max(self.x + self.w, 0.0), 1.0)
        y1 = min(max(self.y + self.h, 0.0), 1.0)
        return Region(x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))

    def is_empty(self) -> bool:
        r = self.clamped()
        return r.w <= 0.0 or r.h <= 0.0


def region_from_pixels(x0: float, y0: float, x1: float, y1: float,
                       width: int, height: int) -> Region:
    """像素框 -> 归一化区域（自动处理反向框并裁剪到图像内）。"""
    if width <= 0 or height <= 0:
        raise ValueError("图像尺寸必须为正")
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    return Region(x0 / width, y0 / height,
                  (x1 - x0) / width, (y1 - y0) / height).clamped()


def region_to_pixels(region: Region, width: int, height: int):
    """归一化区域 -> 图像像素框 (x0, y0, x1, y1)。

    结果已被裁剪到图像内且保证至少 1px 宽高；区域为空时返回 None。
    """
    if width <= 0 or height <= 0:
        return None
    r = region.clamped()
    if r.w <= 0.0 or r.h <= 0.0:
        return None
    x0 = int(round(r.x * width))
    y0 = int(round(r.y * height))
    x1 = int(round((r.x + r.w) * width))
    y1 = int(round((r.y + r.h) * height))
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    x1 = max(x0 + 1, min(width, x1))
    y1 = max(y0 + 1, min(height, y1))
    return (x0, y0, x1, y1)


def block_pixels(block_fraction: float, width: int) -> int:
    """相对块大小 -> 该宽度下的像素块大小（下限 2px）。"""
    if width <= 0:
        return MIN_BLOCK_PX
    return max(MIN_BLOCK_PX, int(round(block_fraction * width)))


def block_fraction_from_pixels(block_px: int, ref_width: int) -> float:
    """参考图宽度下的像素块大小 -> 相对比例。"""
    if ref_width <= 0:
        return 0.0
    return max(1.0, float(block_px)) / ref_width


def aspects_differ(ref_size: tuple[int, int], size: tuple[int, int],
                   tolerance: float = ASPECT_TOLERANCE) -> bool:
    """宽高比是否与参考图差异超过 tolerance（相对差异）。"""
    rw, rh = ref_size
    w, h = size
    if rw <= 0 or rh <= 0 or w <= 0 or h <= 0:
        return True
    a1 = rw / rh
    a2 = w / h
    return abs(a1 - a2) / a1 > tolerance


@dataclass
class MosaicPlan:
    """一次批量处理所需的全部区域信息。"""

    regions: list[Region] = field(default_factory=list)
    block_fraction: float = DEFAULT_BLOCK_PX / 800.0  # 16px @ 800px 宽的默认值

    def rects_for(self, width: int, height: int) -> list[tuple[int, int, int, int]]:
        rects = []
        for r in self.regions:
            px = region_to_pixels(r, width, height)
            if px is not None:
                rects.append(px)
        return rects

    def block_for(self, width: int) -> int:
        return block_pixels(self.block_fraction, width)

    def is_empty(self) -> bool:
        return all(r.is_empty() for r in self.regions)

    def copy(self) -> "MosaicPlan":
        return MosaicPlan(list(self.regions), self.block_fraction)