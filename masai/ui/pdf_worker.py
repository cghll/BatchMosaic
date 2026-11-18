"""把 core.convert_pdfs 包装成 QThread，便于界面更新进度。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QThread, Signal

from ..core.pdf_convert import (
    PdfRenderOptions,
    PdfReport,
    PageResult,
    convert_pdfs,
)


class PdfWorker(QThread):
    progressed = Signal(int, int, str)   # done, total, 当前页
    completed = Signal(object)           # PdfReport

    def __init__(self, sources: Sequence[Path], out_dir: Path,
                 options: PdfRenderOptions, parent=None):
        super().__init__(parent)
        self._sources = list(sources)
        self._out_dir = Path(out_dir)
        self._options = options
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            report = convert_pdfs(
                self._sources,
                self._out_dir,
                self._options,
                on_progress=lambda done, total, result: self.progressed.emit(
                    done, total, result.label),
                cancel_event=self.cancel_event,
            )
        except Exception as exc:  # 兜底，保证界面不会永远卡住
            report = PdfReport(out_dir=self._out_dir, total=len(self._sources))
            report.failed.append(PageResult(
                Path("?"), 0, None, False, f"{type(exc).__name__}: {exc}"))
        self.completed.emit(report)

    def cancel(self) -> None:
        self.cancel_event.set()
