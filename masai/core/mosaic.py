"""像素化马赛克算法（纯 numpy，不依赖 Qt）。

核心语义：
* 所有矩形取并集成一张蒙版（允许重叠）。
* 块网格以图像原点为基准全局对齐，全图共用同一套网格。
* 每个单元格只用**蒙版内**的原图像素求均值，再回填到该单元格内的蒙版像素：
  边缘不满一块的单元格因此不会被框外内容污染。
* 回填范围严格限制在蒙版内，框外像素一个都不改（隐私打码的硬要求）。
* 均值全部取自原图，重复处理结果不变（幂等）。

实现按「网格行带」逐条累加，峰值内存只与单条行带相关（数百 KB 级），
因此可以处理几千像素的大图而不会构造整图浮点副本。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

Rect = tuple[int, int, int, int]  # (x0, y0, x1, y1)


def mosaic_array(arr: np.ndarray,
                 rects: Sequence[Rect],
                 block: int,
                 copy: bool = True) -> np.ndarray:
    """把 rects 覆盖的像素化为均值块。

    arr:  (H, W) 或 (H, W, C) 的 numpy 数组。
    block: 块边长（像素），至少 2。
    copy:  True 返回新数组（默认）；False 原地修改。
    """
    if arr.ndim not in (2, 3):
        raise ValueError(f"不支持的数组维度: {arr.ndim}")
    block = max(2, int(block))
    height, width = arr.shape[:2]

    mask = _coverage_mask(rects, height, width)
    if not mask.any():
        return arr.copy() if copy else arr

    out = arr.copy() if copy else arr
    _apply_blocks(out, arr, mask, block)
    return out


def _coverage_mask(rects: Sequence[Rect], height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in rects:
        cx0 = max(0, min(width, int(x0)))
        cy0 = max(0, min(height, int(y0)))
        cx1 = max(0, min(width, int(x1)))
        cy1 = max(0, min(height, int(y1)))
        if cx1 > cx0 and cy1 > cy0:
            mask[cy0:cy1, cx0:cx1] = True
    return mask


def _apply_blocks(out: np.ndarray, src: np.ndarray, mask: np.ndarray,
                  block: int) -> None:
    height, width = mask.shape
    col_starts = np.arange(0, width, block, dtype=np.intp)
    # 每个网格列包含的像素列号（含最后不满一块的列）
    col_index = np.minimum(np.arange(width, dtype=np.intp) // block,
                           len(col_starts) - 1)

    for gy0 in range(0, height, block):
        gy1 = min(gy0 + block, height)
        band_mask = mask[gy0:gy1]
        if not band_mask.any():
            continue

        band = src[gy0:gy1]
        weights = band_mask[..., None] if band.ndim == 3 else band_mask
        # 列方向的像素和与计数（单条行带，内存极小）
        col_sums = np.where(weights, band, 0).sum(axis=0, dtype=np.int64)
        col_counts = band_mask.sum(axis=0).astype(np.int64)

        cell_sums = np.add.reduceat(col_sums, col_starts, axis=0)
        cell_counts = np.add.reduceat(col_counts, col_starts)

        counts = cell_counts.reshape((-1,) + (1,) * (cell_sums.ndim - 1))
        means = np.divide(cell_sums, np.maximum(counts, 1), dtype=np.float64)
        means[cell_counts == 0] = 0.0
        if np.issubdtype(out.dtype, np.integer):
            means = np.rint(means)
        row_values = means[col_index].astype(out.dtype, copy=False)
        tiled = np.broadcast_to(row_values[None], band.shape)

        target = out[gy0:gy1]
        target[band_mask] = tiled[band_mask]
