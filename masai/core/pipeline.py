"""单图处理：读图 -> 归正方向 -> 打码 -> 按原格式保存。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .mosaic import mosaic_array
from .regions import MosaicPlan

# 可导入的扩展名（导出时沿用原扩展名与原格式）
SUPPORTED_SUFFIXES = frozenset({
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif",
})

# 直接保留的 PIL 模式，其余转换为 RGB/RGBA
_KEEP_MODES = ("RGB", "RGBA", "L", "LA", "CMYK")

JPEG_QUALITY = 95


class ProcessingError(Exception):
    """表示该图片无法处理，可安全跳过并报告给用户。"""


@dataclass
class ImageResult:
    src: Path
    dst: Path | None
    ok: bool
    error: str | None = None


def scan_images(folder: Path) -> list[Path]:
    """列出文件夹下（不递归）受支持的图片，按文件名自然序排序。"""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=lambda p: p.name.lower())


def _prepare_mode(im: Image.Image) -> Image.Image:
    """把调色板/二值等模式转成可安全做均值运算的模式。"""
    mode = im.mode
    if mode in _KEEP_MODES:
        return im
    if mode in ("P", "PA"):
        has_alpha = "transparency" in im.info or mode == "PA"
        return im.convert("RGBA" if has_alpha else "RGB")
    if mode == "1":
        return im.convert("L")
    if mode in ("I", "I;16", "I;16B", "I;16L", "F"):
        conv = im.convert("L")
        return conv
    return im.convert("RGB")


def _exif_bytes(im: Image.Image) -> bytes | None:
    """取出 EXIF，并把方向标记归正为 1（像素已物理旋转）。"""
    try:
        exif = im.getexif()
    except Exception:
        return None
    if not exif:
        return None
    try:
        exif[0x0112] = 1
        data = exif.tobytes()
    except Exception:
        return None
    return data or None


def _save_kwargs(fmt: str, exif: bytes | None, icc: bytes | None) -> dict:
    kwargs: dict = {}
    if icc:
        kwargs["icc_profile"] = icc
    if fmt == "JPEG":
        kwargs.update(quality=JPEG_QUALITY, subsampling=0, optimize=True)
    elif fmt == "PNG":
        kwargs.update(optimize=True)
    elif fmt == "WEBP":
        kwargs.update(quality=JPEG_QUALITY, method=4)
    if exif and fmt in ("JPEG", "PNG", "WEBP", "TIFF"):
        kwargs["exif"] = exif
    return kwargs


def process_image(src: Path, dst: Path, plan: MosaicPlan) -> ImageResult:
    """处理单张图片并保存到 dst。失败返回 ok=False 的结果，不抛异常。"""
    src = Path(src)
    dst = Path(dst)
    try:
        with Image.open(src) as im:
            fmt = im.format or _format_from_suffix(src)
            if fmt == "GIF" and getattr(im, "n_frames", 1) > 1:
                raise ProcessingError("动图暂不支持")
            if fmt is None:
                raise ProcessingError("无法识别的图片格式")

            icc = im.info.get("icc_profile")
            oriented = ImageOps.exif_transpose(im)
            exif = _exif_bytes(oriented)
            work = _prepare_mode(oriented)
            width, height = work.size
            if width <= 0 or height <= 0:
                raise ProcessingError("图像尺寸异常")

            rects = plan.rects_for(width, height)
            if rects:
                block = plan.block_for(width)
                arr = np.array(work)
                out = mosaic_array(arr, rects, block, copy=True)
                work = Image.frombytes(work.mode, work.size, out.tobytes())

            dst.parent.mkdir(parents=True, exist_ok=True)
            work.save(dst, format=fmt, **_save_kwargs(fmt, exif, icc))
        return ImageResult(src, dst, True)
    except ProcessingError as exc:
        return ImageResult(src, None, False, str(exc))
    except UnidentifiedImageError:
        return ImageResult(src, None, False, "无法识别的图片")
    except Image.DecompressionBombError:
        return ImageResult(src, None, False, "图片像素过大，已跳过")
    except Exception as exc:  # 单张失败不应中断整批
        return ImageResult(src, None, False, f"{type(exc).__name__}: {exc}")


def _format_from_suffix(path: Path) -> str | None:
    """从扩展名推断 PIL 格式名（仅在 im.format 缺失时使用）。"""
    mapping = {
        ".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG",
        ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP",
        ".tif": "TIFF", ".tiff": "TIFF", ".gif": "GIF",
    }
    return mapping.get(path.suffix.lower())


def output_path_for(src: Path, out_dir: Path) -> Path:
    """输出文件路径：保留原文件名。"""
    return Path(out_dir) / Path(src).name


def probe_size(path: Path) -> tuple[int, int] | None:
    """读取图片「摆正后」的尺寸；读不出时返回 None。

    只读文件头，不解析像素，因此可以快速列出一整个文件夹。
    """
    try:
        with Image.open(path) as im:
            width, height = im.size
            try:
                orientation = im.getexif().get(0x0112, 1)
            except Exception:
                orientation = 1
    except Exception:
        return None
    if orientation in (5, 6, 7, 8):  # 旋转 90°，宽高互换
        width, height = height, width
    return width, height


def expected_workers() -> int:
    return max(1, min(4, (getattr(math, "cpu_count", None) and math.cpu_count()) or 4))