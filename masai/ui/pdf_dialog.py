"""PDF 转图片对话框：选源文件、设 DPI/格式/页码、选输出文件夹。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.pdf_convert import (
    DEFAULT_DPI,
    DEFAULT_QUALITY,
    MAX_DPI,
    MIN_DPI,
    PdfConvertError,
    PdfRenderOptions,
    collect_pdfs,
)
from .icons import icon, pixmap
from .theme import SPACE, theme_manager


class PdfDialog(QDialog):
    """转换完成后只导出图片文件夹，不自动导入到打码流程。"""

    def __init__(self, last_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("pdfDialog")
        self.setWindowTitle("PDF 转图片")
        self.setMinimumWidth(560)
        self._last_dir = Path(last_dir) if last_dir else Path.home()
        self._sources: list[Path] = []
        self._out_manual = False
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
        title = QLabel("PDF 转图片", titles)
        title.setObjectName("emptyTitle")
        lead = QLabel("把 PDF 的每一页渲染成独立图片，导出到一个新文件夹。", titles)
        lead.setObjectName("emptyBody")
        title_col.addWidget(title)
        title_col.addWidget(lead)
        heading.addWidget(titles, 1)
        layout.addLayout(heading)

        source_label = QLabel("PDF 来源", self)
        source_label.setObjectName("fieldLabel")
        layout.addWidget(source_label)

        self.btn_add_files = QPushButton("添加文件…", self)
        self.btn_add_folder = QPushButton("添加文件夹…", self)
        self.btn_remove = QPushButton("移除", self)
        source_row = QHBoxLayout()
        source_row.setSpacing(SPACE["sm"])
        source_row.addWidget(self.btn_add_files)
        source_row.addWidget(self.btn_add_folder)
        source_row.addWidget(self.btn_remove)
        source_row.addStretch(1)
        layout.addLayout(source_row)

        self.list_sources = QListWidget(self)
        self.list_sources.setObjectName("pdfSourceList")
        self.list_sources.setMaximumHeight(112)
        self.list_sources.setToolTip("可添加多个 PDF 或文件夹；文件夹只扫描一层")
        layout.addWidget(self.list_sources)
        self.lbl_source_count = QLabel("尚未选择 PDF", self)
        self.lbl_source_count.setObjectName("metaLabel")
        layout.addWidget(self.lbl_source_count)

        layout.addSpacing(SPACE["xs"])
        options_row = QHBoxLayout()
        options_row.setSpacing(SPACE["md"])

        dpi_col = QVBoxLayout()
        dpi_label = QLabel("分辨率（DPI）", self)
        dpi_label.setObjectName("fieldLabel")
        self.spin_dpi = QSpinBox(self)
        self.spin_dpi.setRange(MIN_DPI, MAX_DPI)
        self.spin_dpi.setValue(DEFAULT_DPI)
        self.spin_dpi.setSuffix(" dpi")
        dpi_col.addWidget(dpi_label)
        dpi_col.addWidget(self.spin_dpi)
        options_row.addLayout(dpi_col, 1)

        fmt_col = QVBoxLayout()
        fmt_label = QLabel("图片格式", self)
        fmt_label.setObjectName("fieldLabel")
        self.combo_format = QComboBox(self)
        self.combo_format.addItems(["PNG", "JPEG"])
        fmt_col.addWidget(fmt_label)
        fmt_col.addWidget(self.combo_format)
        options_row.addLayout(fmt_col, 1)

        quality_col = QVBoxLayout()
        quality_label = QLabel("JPEG 质量", self)
        quality_label.setObjectName("fieldLabel")
        self.spin_quality = QSpinBox(self)
        self.spin_quality.setRange(1, 100)
        self.spin_quality.setValue(DEFAULT_QUALITY)
        self.spin_quality.setSuffix(" %")
        quality_col.addWidget(quality_label)
        quality_col.addWidget(self.spin_quality)
        options_row.addLayout(quality_col, 1)
        layout.addLayout(options_row)

        pages_row = QHBoxLayout()
        pages_row.setSpacing(SPACE["md"])
        pages_title = QLabel("页码", self)
        pages_title.setObjectName("fieldLabel")
        self.edit_pages = QLineEdit(self)
        self.edit_pages.setPlaceholderText("全部，或 1-3,5,8")
        pages_row.addWidget(pages_title)
        pages_row.addWidget(self.edit_pages, 1)
        layout.addLayout(pages_row)

        folder_label = QLabel("输出文件夹", self)
        folder_label.setObjectName("fieldLabel")
        layout.addWidget(folder_label)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("选择一个用于存放结果的文件夹")
        self.btn_browse = QPushButton("浏览…", self)
        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        row.addWidget(self.edit, 1)
        row.addWidget(self.btn_browse)
        layout.addLayout(row)

        info = QLabel(
            "图片命名为「原名_p001.png」，不会修改原 PDF，也不会自动进入打码流程。\n"
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
        buttons.button(QDialogButtonBox.Ok).setText("开始转换")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addSpacing(SPACE["sm"])
        layout.addWidget(buttons)

        self.btn_add_files.clicked.connect(self._add_files)
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_browse.clicked.connect(self._browse)
        self.spin_dpi.valueChanged.connect(self._validate)
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        self.spin_quality.valueChanged.connect(self._validate)
        self.edit_pages.textChanged.connect(self._validate)
        self.edit.textChanged.connect(self._validate)
        self.edit.textEdited.connect(self._on_out_edited)
        self.list_sources.itemSelectionChanged.connect(self._sync_remove)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._buttons = buttons

        self._theme.changed.connect(self._on_theme_changed)
        self._on_theme_changed(self._theme.palette)
        self._on_format_changed(self.combo_format.currentText())
        self._validate()

    # ---------- 结果 ----------
    def sources(self) -> list[Path]:
        return collect_pdfs(self._sources)

    def options(self) -> PdfRenderOptions:
        return PdfRenderOptions(
            dpi=self.spin_dpi.value(),
            image_format=self.combo_format.currentText(),
            quality=self.spin_quality.value(),
            pages=self.edit_pages.text().strip() or "all",
        )

    def out_dir(self) -> Path:
        return Path(self.edit.text().strip())

    def open_when_done(self) -> bool:
        return self.chk_open.isChecked()

    # ---------- 内部 ----------
    def _on_theme_changed(self, palette) -> None:
        self._head_icon.setPixmap(pixmap("pdf", palette.accent, 28))
        self._warn_icon.setPixmap(pixmap("warning", palette.danger, 16))
        self.btn_add_files.setIcon(
            icon("image", palette.text_sub, 16, palette.text_muted))
        self.btn_add_folder.setIcon(
            icon("folder_open", palette.text_sub, 16, palette.text_muted))
        self.btn_remove.setIcon(
            icon("trash", palette.text_sub, 16, palette.text_muted))
        self.btn_browse.setIcon(
            icon("folder_open", palette.text_sub, 16, palette.text_muted))
        ok = self._buttons.button(QDialogButtonBox.Ok)
        if ok is not None:
            ok.setIcon(icon("export", palette.accent_text, 16, palette.text_muted))

    def _on_format_changed(self, text: str) -> None:
        self.spin_quality.setEnabled(text.upper() == "JPEG")
        self._validate()

    def _on_out_edited(self, _text: str) -> None:
        self._out_manual = True
        self._validate()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", str(self._start_dir()), "PDF 文件 (*.pdf)")
        if paths:
            self._add_sources([Path(p) for p in paths])
            self._last_dir = Path(paths[0]).parent

    def _add_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "选择包含 PDF 的文件夹", str(self._start_dir()))
        if chosen:
            self._add_sources([Path(chosen)])
            self._last_dir = Path(chosen).parent

    def _add_sources(self, paths: list[Path]) -> None:
        existing = {p.resolve() for p in self._sources}
        for path in paths:
            resolved = path.resolve()
            if resolved not in existing:
                self._sources.append(path)
                existing.add(resolved)
        self._refresh_sources()
        if not self._out_manual:
            self.edit.setText(str(self._default_out_dir()))
        self._validate()

    def _remove_selected(self) -> None:
        rows = {index.row() for index in self.list_sources.selectedIndexes()}
        if not rows:
            return
        self._sources = [p for i, p in enumerate(self._sources) if i not in rows]
        self._refresh_sources()
        self._validate()

    def _refresh_sources(self) -> None:
        self.list_sources.blockSignals(True)
        self.list_sources.clear()
        for path in self._sources:
            suffix = "（文件夹）" if path.is_dir() else ""
            self.list_sources.addItem(path.name + suffix)
            self.list_sources.item(self.list_sources.count() - 1).setToolTip(str(path))
        self.list_sources.blockSignals(False)
        count = len(self.sources())
        self.lbl_source_count.setText(
            f"已选 {count} 份 PDF" if count else "尚未选择 PDF")
        self._sync_remove()

    def _sync_remove(self) -> None:
        self.btn_remove.setEnabled(bool(self.list_sources.selectedIndexes()))

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "选择输出文件夹", str(self._start_dir()))
        if chosen:
            self.edit.setText(str(Path(chosen) / self._default_out_dir().name))
            self._out_manual = True
            self._validate()

    def _default_out_dir(self) -> Path:
        if not self._sources:
            return self._last_dir / "pdf_images"
        first = Path(self._sources[0])
        if first.is_dir():
            return first.parent / f"{first.name}_images"
        return first.parent / f"{first.stem}_images"

    def _start_dir(self) -> Path:
        current = self.out_dir()
        for candidate in (current, current.parent, self._last_dir, Path.home()):
            try:
                if candidate.is_dir():
                    return candidate
            except OSError:
                continue
        return Path.home()

    def _validate(self) -> None:
        problem = ""
        if not self.sources():
            problem = "请至少添加一个 PDF 文件或文件夹。"
        else:
            try:
                self.options().validate()
            except PdfConvertError as exc:
                problem = str(exc)
            else:
                text = self.edit.text().strip()
                if not text:
                    problem = "请填写输出文件夹。"
                else:
                    target = Path(text)
                    if target.is_file():
                        problem = "这个路径是一个文件，请选择文件夹。"
                    elif any(p.is_dir() and target.resolve() == p.resolve()
                             for p in self._sources):
                        problem = "输出文件夹不能与所选 PDF 文件夹相同。"
                    elif not _writable(target):
                        problem = "该位置无法写入，请换一个文件夹。"

        self.lbl_warn.setText(problem)
        self.lbl_warn.setVisible(bool(problem))
        self._warn_row.setVisible(bool(problem))
        ok = self._buttons.button(QDialogButtonBox.Ok)
        if ok is not None:
            ok.setEnabled(not problem)


def _writable(target: Path) -> bool:
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
