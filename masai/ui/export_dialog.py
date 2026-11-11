"""导出设置对话框：选输出文件夹（允许尚不存在）+ 完成后打开。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import icon, pixmap
from .theme import SPACE, theme_manager


class ExportDialog(QDialog):
    """让用户确认输出目录。默认是「原文件夹名_mosaic」，可直接创建。"""

    def __init__(self, source_dir: Path, default_dir: Path,
                 image_count: int, region_count: int, parent=None):
        super().__init__(parent)
        self.setObjectName("exportDialog")
        self.setWindowTitle("导出")
        self.setMinimumWidth(540)
        self._source = Path(source_dir)
        self._theme = theme_manager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE["xl"], SPACE["xl"], SPACE["xl"], SPACE["lg"])
        layout.setSpacing(SPACE["md"])

        heading = QHBoxLayout()
        heading.setSpacing(SPACE["md"])
        self._head_icon = QLabel(self)
        self._head_icon.setAlignment(Qt.AlignTop)
        heading.addWidget(self._head_icon)
        titles = QWidget(self)
        title_col = QVBoxLayout(titles)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel("导出这批图片", titles)
        title.setObjectName("emptyTitle")
        lead = QLabel(
            f"将处理 {image_count} 张图片，套用 {region_count} 个区域。", titles)
        lead.setObjectName("emptyBody")
        title_col.addWidget(title)
        title_col.addWidget(lead)
        heading.addWidget(titles, 1)
        layout.addLayout(heading)
        layout.addSpacing(SPACE["xs"])

        folder_label = QLabel("输出文件夹", self)
        folder_label.setObjectName("fieldLabel")
        layout.addWidget(folder_label)

        self.edit = QLineEdit(str(default_dir), self)
        self.edit.setMinimumWidth(420)
        self.edit.setPlaceholderText("选择一个用于存放结果的文件夹")
        self.btn_browse = QPushButton("浏览…", self)
        self.btn_browse.setToolTip("选择输出位置（会自动追加结果文件夹名）")
        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        row.addWidget(self.edit, 1)
        row.addWidget(self.btn_browse)
        layout.addLayout(row)

        info = QLabel(
            "保持原文件名与原格式，输出到上面的文件夹。\n"
            "目标文件夹不存在时会自动创建。", self)
        info.setObjectName("hintLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.chk_open = QCheckBox("完成后打开输出文件夹", self)
        self.chk_open.setChecked(True)
        layout.addWidget(self.chk_open)

        warn_row = QWidget(self)
        warn_layout = QHBoxLayout(warn_row)
        warn_layout.setContentsMargins(0, 0, 0, 0)
        warn_layout.setSpacing(SPACE["sm"])
        self._warn_icon = QLabel(warn_row)
        warn_layout.addWidget(self._warn_icon)
        self.lbl_warn = QLabel("", warn_row)
        self.lbl_warn.setObjectName("warnText")
        self.lbl_warn.setWordWrap(True)
        warn_layout.addWidget(self.lbl_warn, 1)
        warn_row.setVisible(False)
        self._warn_row = warn_row
        layout.addWidget(warn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("开始导出")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addSpacing(SPACE["sm"])
        layout.addWidget(buttons)

        self.btn_browse.clicked.connect(self._browse)
        self.edit.textChanged.connect(self._validate)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._buttons = buttons
        self._theme.changed.connect(self._on_theme_changed)
        self._on_theme_changed(self._theme.palette)
        self._validate()

    def _on_theme_changed(self, palette) -> None:
        self._head_icon.setPixmap(pixmap("download", palette.accent, 28))
        self._warn_icon.setPixmap(pixmap("warning", palette.danger, 16))
        self.btn_browse.setIcon(
            icon("folder_open", palette.text_sub, 16, palette.text_muted))
        ok = self._buttons.button(QDialogButtonBox.Ok)
        if ok is not None:
            ok.setIcon(icon("export", palette.accent_text, 16, palette.text_muted))

    # ---------- 结果 ----------
    def out_dir(self) -> Path:
        return Path(self.edit.text().strip())

    def open_when_done(self) -> bool:
        return self.chk_open.isChecked()

    # ---------- 内部 ----------
    def _browse(self) -> None:
        start = self._start_dir()
        chosen = QFileDialog.getExistingDirectory(self, "选择输出文件夹", str(start))
        if chosen:
            self.edit.setText(str(Path(chosen) / self._default_name()))

    def _default_name(self) -> str:
        return f"{self._source.name}_mosaic"

    def _start_dir(self) -> Path:
        current = self.out_dir()
        for candidate in (current, current.parent, self._source.parent):
            try:
                if candidate.is_dir():
                    return candidate
            except OSError:
                continue
        return Path.home()

    def _validate(self) -> None:
        text = self.edit.text().strip()
        problem = ""
        if not text:
            problem = "请填写输出文件夹。"
        else:
            target = Path(text)
            try:
                same = target.resolve() == self._source.resolve()
            except OSError:
                same = False
            if same:
                problem = "不能导出到原文件夹，否则会覆盖原图。"
            elif target.is_file():
                problem = "这个路径是一个文件，请选择文件夹。"
            elif not self._writable(target):
                problem = "该位置无法写入，请换一个文件夹。"

        self.lbl_warn.setText(problem)
        self.lbl_warn.setVisible(bool(problem))
        self._warn_row.setVisible(bool(problem))
        ok = self._buttons.button(QDialogButtonBox.Ok)
        if ok is not None:
            ok.setEnabled(not problem)

    @staticmethod
    def _writable(target: Path) -> bool:
        """目标已存在则检查其可写；不存在则回退到最近的已存在祖先目录。"""
        probe = target
        while True:
            try:
                if probe.exists():
                    return probe.is_dir() and _can_write(probe)
            except OSError:
                return False
            if probe.parent == probe:
                return False
            probe = probe.parent


def _can_write(folder: Path) -> bool:
    try:
        probe = folder / ".masai_write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False
