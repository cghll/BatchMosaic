"""python -m masai 入口。

双击 run.bat 时走的是 pythonw（没有控制台），任何启动异常——包括
`from .app import main` 这一步的导入失败——都会静默消失，表现为
「双击没反应」。这里在最外层兜底：写日志 + 用 Win32 MessageBox 弹窗，
后者不依赖 Qt，即使 PySide6 完全装不上也能显示。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

LOG_NAME = "masai_startup_error.log"


def _emergency_report(exc: BaseException) -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # pythonw 没有控制台，日志是唯一可追溯的证据，写到项目根目录
    try:
        root = Path(__file__).resolve().parent.parent
        (root / LOG_NAME).write_text(detail, encoding="utf-8")
    except Exception:
        pass
    # Win32 弹窗不依赖 Qt；MB_ICONERROR = 0x10
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            f"MaSai 启动失败：{type(exc).__name__}: {exc}\n\n"
            f"详细信息已写入 {LOG_NAME}\n"
            "若提示缺少模块，请运行：pip install -r requirements.txt",
            "MaSai 启动失败",
            0x10,
        )
    except Exception:
        pass
    # pythonw 下 sys.stderr 可能是 None，直接 print 会自己再抛一次
    try:
        if sys.stderr is not None:
            print(detail, file=sys.stderr)
    except Exception:
        pass


try:
    from .app import main
except BaseException as exc:
    _emergency_report(exc)
    raise SystemExit(1) from None

try:
    raise SystemExit(main())
except SystemExit:
    raise
except BaseException as exc:
    _emergency_report(exc)
    raise SystemExit(1) from None