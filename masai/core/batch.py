"""批量调度：线程池并行、进度回调、可取消。不依赖 Qt。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .pipeline import ImageResult, output_path_for, process_image
from .regions import MosaicPlan

ProgressCb = Callable[[int, int, ImageResult], None]


@dataclass
class BatchReport:
    out_dir: Path
    total: int = 0
    succeeded: int = 0
    failed: list[ImageResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def processed(self) -> int:
        return self.succeeded + len(self.failed)


def run_batch(sources: Sequence[Path],
              out_dir: Path,
              plan: MosaicPlan,
              on_progress: ProgressCb | None = None,
              cancel_event: threading.Event | None = None,
              max_workers: int = 4) -> BatchReport:
    """并发处理 sources，逐张回调进度。取消时当前张处理完即停止。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = list(sources)
    report = BatchReport(out_dir=out_dir, total=len(sources))
    if not sources:
        return report

    def work(src: Path) -> ImageResult:
        if cancel_event is not None and cancel_event.is_set():
            return ImageResult(src, None, False, "已取消")
        return process_image(Path(src), output_path_for(src, out_dir), plan)

    workers = max(1, int(max_workers))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, src) for src in sources]
        for fut in as_completed(futures):
            try:
                result = fut.result()
            except Exception as exc:  # 理论上 process_image 不抛，兜底
                result = ImageResult(Path("?"), None, False, f"{type(exc).__name__}: {exc}")
            done += 1
            if result.ok:
                report.succeeded += 1
            else:
                report.failed.append(result)
                if result.error == "已取消":
                    report.cancelled = True
            if on_progress is not None:
                on_progress(done, report.total, result)
            if cancel_event is not None and cancel_event.is_set():
                # 取消后不再等待剩余任务结果，直接收尾
                for f in futures:
                    f.cancel()
                report.cancelled = True
                break
    return report