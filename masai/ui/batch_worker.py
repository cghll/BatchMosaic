"""把 core.run_batch 包装成 QThread，便于界面更新进度。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QThread, Signal

from ..core.batch import BatchReport, run_batch
from ..core.regions import MosaicPlan


class BatchWorker(QThread):
    progressed = Signal(int, int, str)   # done, total, 当前文件名
    completed = Signal(object)           # BatchReport

    def __init__(self, sources: Sequence[Path], out_dir: Path,
                 plan: MosaicPlan, parent=None):
        super().__init__(parent)
        self._sources = list(sources)
        self._out_dir = Path(out_dir)
        self._plan = plan
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            report = run_batch(
                self._sources,
                self._out_dir,
                self._plan,
                on_progress=lambda done, total, res: self.progressed.emit(
                    done, total, res.src.name),
                cancel_event=self.cancel_event,
            )
        except Exception as exc:  # 兜底，保证界面不会永远卡住
            report = BatchReport(out_dir=self._out_dir,
                                 total=len(self._sources))
            report.failed.append(_fake_failure(exc))
        self.completed.emit(report)

    def cancel(self) -> None:
        self.cancel_event.set()


def _fake_failure(exc: Exception):
    from ..core.pipeline import ImageResult
    return ImageResult(Path("?"), None, False, f"{type(exc).__name__}: {exc}")