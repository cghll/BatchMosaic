"""应用入口。"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from .ui.main_window import MainWindow
from .ui.theme import install_theme


def _report_startup_failure(exc: BaseException) -> None:
    """启动失败时给出可见提示（pythonw 下没有控制台，弹窗是唯一出口）。"""
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(
            None, "MaSai 启动失败",
            f"{type(exc).__name__}: {exc}\n\n"
            "如果提示缺少模块，请先运行：pip install -r requirements.txt")
        _ = app
    except Exception:
        pass
    # pythonw 下 sys.stderr 为 None，不能无条件 print
    try:
        if sys.stderr is not None:
            print(detail, file=sys.stderr)
    except Exception:
        pass


def main() -> int:
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("MaSai")
        app.setApplicationDisplayName("MaSai · 批量图片马赛克")
        # Fusion 让 QSS 子控件（滑块、复选、SpinBox 箭头）在各 Windows 版本上表现一致
        app.setStyle("Fusion")
        install_theme(app)
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:  # 双击 run.bat 时用户看不到 traceback
        _report_startup_failure(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
