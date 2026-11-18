"""PDF 转图片：把 PDF 页渲染为 PNG/JPEG，不依赖 Qt。

只负责「转换到文件夹」，不接手批量打码流程。转换后的图片路径、命名和格式
都是普通图片，可直接交给 pipeline.scan_images() 再次导入。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_DPI = 200
MIN_DPI = 50
MAX_DPI = 600
DEFAULT_QUALITY = 95
MAX_RENDER_PIXELS = 100_000_000

_FORMAT_EXT = {"PNG": ".png", "JPEG": ".jpg"}


class PdfConvertError(Exception):
    """单份 PDF 或单个页面无法转换，可安全跳过并报告给用户。"""


@dataclass(frozen=True)
class PdfRenderOptions:
    """渲染选项。pages 支持 all / 1,3-5 这类写法（页码从 1 开始）。"""

    dpi: int = DEFAULT_DPI
    image_format: str = "PNG"
    quality: int = DEFAULT_QUALITY
    pages: str = "all"

    def validate(self) -> None:
        if not MIN_DPI <= int(self.dpi) <= MAX_DPI:
            raise PdfConvertError(f"DPI 需在 {MIN_DPI} ~ {MAX_DPI} 之间")
        if self.image_format.upper() not in _FORMAT_EXT:
            raise PdfConvertError("仅支持 PNG 或 JPEG")
        if not 1 <= int(self.quality) <= 100:
            raise PdfConvertError("JPEG 质量需在 1 ~ 100 之间")
        self.page_indices(1, allow_empty=True)  # 只校验语法，不校验页数边界

    @property
    def fmt(self) -> str:
        return self.image_format.upper()

    @property
    def ext(self) -> str:
        return _FORMAT_EXT[self.fmt]

    def page_indices(self, total: int, *, allow_empty: bool = False) -> list[int]:
        """把页码表达式转换成 0 基索引，越界会被裁掉。

        allow_empty=True 只用于选项语法校验；真正转换时选中 0 页要报错。
        """
        text = self.pages.strip().lower()
        if text in ("", "all", "全部"):
            return list(range(total))
        indices: set[int] = set()
        for part in text.replace("，", ",").replace("－", "-").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                left, _, right = part.partition("-")
                try:
                    start, end = int(left), int(right)
                except ValueError as exc:
                    raise PdfConvertError(f"页码范围无效：{part}") from exc
                if start < 1 or end < start:
                    raise PdfConvertError(f"页码范围无效：{part}")
                indices.update(range(start - 1, min(end, total)))
            else:
                try:
                    number = int(part)
                except ValueError as exc:
                    raise PdfConvertError(f"页码无效：{part}") from exc
                if number < 1:
                    raise PdfConvertError(f"页码无效：{part}")
                if number <= total:
                    indices.add(number - 1)
        if not indices and not allow_empty:
            raise PdfConvertError("没有选中任何页面")
        return sorted(indices)


@dataclass
class PageResult:
    src: Path
    page: int                       # 1 基页码；0 表示整份文件失败
    dst: Path | None
    ok: bool
    error: str | None = None

    @property
    def label(self) -> str:
        return f"{self.src.name} p{self.page}" if self.page else self.src.name


@dataclass
class PdfReport:
    out_dir: Path
    total: int = 0
    succeeded: int = 0
    failed: list[PageResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def processed(self) -> int:
        return self.succeeded + len(self.failed)


ProgressCb = Callable[[int, int, PageResult], None]


def collect_pdfs(paths: Sequence[Path]) -> list[Path]:
    """接收文件或文件夹，返回去重、按文件名排序的 PDF 列表（只扫一层）。"""
    found: dict[Path, None] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in path.iterdir():
                if child.is_file() and child.suffix.lower() == ".pdf":
                    found[child.resolve()] = None
        elif path.is_file() and path.suffix.lower() == ".pdf":
            found[path.resolve()] = None
    return sorted(found, key=lambda p: p.name.lower())


def pdf_page_count(path: Path) -> int:
    """读取页数。加密或损坏的 PDF 会抛 PdfConvertError。"""
    pdfium = _pdfium()
    try:
        with pdfium.PdfDocument(str(path)) as doc:
            return len(doc)
    except Exception as exc:
        raise PdfConvertError(_error_text(exc)) from exc


def convert_pdfs(sources: Sequence[Path],
                 out_dir: Path,
                 options: PdfRenderOptions | None = None,
                 on_progress: ProgressCb | None = None,
                 cancel_event: threading.Event | None = None) -> PdfReport:
    """把 sources 里的 PDF 渲染到 out_dir，逐页回调进度，可取消。"""
    options = options or PdfRenderOptions()
    options.validate()
    pdfs = collect_pdfs(sources)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = PdfReport(out_dir=out_dir)

    # 先规划全部页，进度条总数从一开始就准确；无法打开的 PDF 也算一项失败。
    plan: list[tuple[Path, list[int]]] = []
    used_stems: set[str] = set()
    for pdf in pdfs:
        try:
            total_pages = pdf_page_count(pdf)
            indices = options.page_indices(total_pages)
            plan.append((pdf, indices))
            report.total += len(indices)
        except Exception as exc:
            report.failed.append(PageResult(pdf, 0, None, False, _error_text(exc)))
            report.total += 1

    done = 0
    stems: dict[Path, str] = {}
    for pdf, indices in plan:
        if _cancelled(cancel_event):
            report.cancelled = True
            break
        stem = _unique_stem(pdf, used_stems)
        stems[pdf] = stem
        try:
            pdfium = _pdfium()
            with pdfium.PdfDocument(str(pdf)) as doc:
                for index in indices:
                    if _cancelled(cancel_event):
                        report.cancelled = True
                        break
                    result = _render_one(doc, pdf, index, stem, out_dir, options)
                    report.succeeded += int(result.ok)
                    if not result.ok:
                        report.failed.append(result)
                    done += 1
                    if on_progress is not None:
                        on_progress(done, report.total, result)
        except Exception as exc:
            message = _error_text(exc)
            for index in indices:
                result = PageResult(pdf, index + 1, None, False, message)
                report.failed.append(result)
                done += 1
                if on_progress is not None:
                    on_progress(done, report.total, result)
        if report.cancelled:
            break
    return report


def output_path_for_page(pdf: Path, page_no: int, out_dir: Path,
                         options: PdfRenderOptions, stem: str | None = None) -> Path:
    """输出名：原名_p001.png，避免直接用缓存名或覆盖原 PDF。"""
    base = stem or pdf.stem
    return Path(out_dir) / f"{base}_p{page_no:03d}{options.ext}"


def _pdfium():
    try:
        import pypdfium2
    except ImportError as exc:  # 延迟报错：不装依赖也能继续用打码功能
        raise PdfConvertError(
            "缺少 PDF 渲染组件 pypdfium2，请运行 pip install -r requirements.txt"
        ) from exc
    return pypdfium2


def _render_one(doc, pdf: Path, index: int, stem: str, out_dir: Path,
                options: PdfRenderOptions) -> PageResult:
    page_no = index + 1
    dst = output_path_for_page(pdf, page_no, out_dir, options, stem)
    try:
        page = doc[index]
        try:
            width_pt, height_pt = page.get_size()
            scale = int(options.dpi) / 72.0
            if width_pt * height_pt * scale * scale > MAX_RENDER_PIXELS:
                raise PdfConvertError("页面像素过大，已跳过")
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
        finally:
            page.close()

        if options.fmt == "JPEG":
            from PIL import Image
            if image.mode != "RGB":
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            kwargs = {"quality": int(options.quality), "optimize": True}
        else:
            kwargs = {"optimize": True}

        dst.parent.mkdir(parents=True, exist_ok=True)
        image.save(dst, format=options.fmt, **kwargs)
        return PageResult(pdf, page_no, dst, True)
    except Exception as exc:
        return PageResult(pdf, page_no, None, False, _error_text(exc))


def _unique_stem(pdf: Path, used: set[str]) -> str:
    stem = pdf.stem
    if stem.lower() in used:
        stem = f"{pdf.parent.name}_{stem}"
    candidate = stem
    suffix = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{suffix}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _cancelled(event: threading.Event | None) -> bool:
    return event is not None and event.is_set()


def _error_text(exc: Exception) -> str:
    text = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {text}" if type(exc).__name__ not in text else text
