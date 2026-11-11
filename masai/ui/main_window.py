"""主窗口：编排导入、区域编辑、预览与批量导出。

视觉层按 Impeccable Operate 模式组织：应用栏只放一条主操作，三栏是安静的中性
阶梯，唯一的强调色留给「导出」、当前选中和画布上的区域框。业务方法与测试依赖的
控件属性名保持不变。
"""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.pipeline import probe_size, scan_images
from ..core.regions import (
    ASPECT_TOLERANCE,
    DEFAULT_BLOCK_PX,
    MAX_BLOCK_PX,
    MosaicPlan,
    Region,
    aspects_differ,
    block_fraction_from_pixels,
    block_pixels,
)
from .batch_worker import BatchWorker
from .export_dialog import ExportDialog
from .icons import icon, pixmap
from .image_canvas import ImageCanvas
from .theme import (
    APP_BAR_H,
    LEFT_W,
    RIGHT_W,
    SPACE,
    STATUS_BAR_H,
    theme_manager,
)


def _rule() -> QFrame:
    line = QFrame()
    line.setObjectName("sectionRule")
    line.setFrameShape(QFrame.HLine)
    return line


def _section(title: str, badge: QLabel | None = None) -> tuple[QWidget, QHBoxLayout]:
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACE["sm"])
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    row.addWidget(label)
    row.addStretch(1)
    if badge is not None:
        row.addWidget(badge)
    return host, row


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MaSai · 批量图片马赛克")
        self.resize(1280, 840)
        self.setMinimumSize(1040, 660)
        self.setAcceptDrops(True)

        self._folder: Path | None = None
        self._images: list[Path] = []
        self._sizes: dict[Path, tuple[int, int] | None] = {}
        self._regions: list[Region] = []
        self._ref_index = -1
        self._ref_size: tuple[int, int] = (0, 0)
        self._block_fraction = block_fraction_from_pixels(DEFAULT_BLOCK_PX, 1000)
        self._reset_block = False
        self._last_dir: Path | None = None
        self._last_out: Path | None = None
        self._open_after = True
        self._worker: BatchWorker | None = None
        self._cancel: threading.Event | None = None
        self._theme = theme_manager()

        # 滑块拖动时每移动一格都会发 valueChanged；累积到上一次刷新之后再做，
        # 避免在大图上每移动一像素就重算整张预览。
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(60)
        self._preview_timer.timeout.connect(self._apply_block_preview)

        self._build_ui()
        self._connect()
        # objectName 是在创建控件后设置的，重新应用一次 QSS 让选择器生效
        self._theme.apply()
        self._on_theme_changed(self._theme.palette)
        self._update_state()

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setObjectName("appBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setFixedHeight(APP_BAR_H)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        toolbar.addWidget(self._build_brand())
        toolbar.addSeparator()

        self.act_import = QAction("导入文件夹", self)
        self.act_import.setShortcut(QKeySequence.Open)
        self.act_import.setToolTip("选择一个图片文件夹（Ctrl+O）")
        self.act_fit = QAction("适应窗口", self)
        self.act_fit.setToolTip("适应窗口")
        self.act_zoom_in = QAction("放大", self)
        self.act_zoom_in.setToolTip("放大（滚轮向上）")
        self.act_zoom_out = QAction("缩小", self)
        self.act_zoom_out.setToolTip("缩小（滚轮向下）")
        self.act_export = QAction("导出…", self)
        self.act_export.setShortcut("Ctrl+E")
        self.act_export.setToolTip("把当前区域套用到整批图片（Ctrl+E）")
        self.act_theme = QAction("浅色", self)

        toolbar.addAction(self.act_import)
        toolbar.addSeparator()
        toolbar.addAction(self.act_fit)
        toolbar.addAction(self.act_zoom_out)
        toolbar.addAction(self.act_zoom_in)

        spacer = QWidget(toolbar)
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        toolbar.addAction(self.act_theme)
        toolbar.addAction(self.act_export)

        self._tag_action(self.act_import, "textAction")
        self._tag_action(self.act_fit, "frameAction")
        self._tag_action(self.act_zoom_out, "frameAction")
        self._tag_action(self.act_zoom_in, "frameAction")
        self._tag_action(self.act_theme, "textAction")
        self._tag_action(self.act_export, "primaryAction")

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        for index, minimum in enumerate((200, 360, 240)):
            splitter.widget(index).setMinimumWidth(minimum)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([LEFT_W, 744, RIGHT_W])
        self.splitter = splitter

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(splitter, 1)
        outer.addWidget(self._build_bottom_bar())
        self.setCentralWidget(central)

    def _tag_action(self, action: QAction, name: str) -> None:
        button = self.toolbar.widgetForAction(action)
        if button is not None:
            button.setObjectName(name)
            button.setCursor(Qt.PointingHandCursor)
            if name == "frameAction":
                # 32px 方按钮只放图标；否则 TextBesideIcon 会把文字挤成「…」
                button.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def _build_brand(self) -> QWidget:
        brand = QWidget(self.toolbar)
        row = QHBoxLayout(brand)
        row.setContentsMargins(0, 0, SPACE["lg"], 0)
        row.setSpacing(SPACE["sm"])

        mark = QWidget(brand)
        mark.setObjectName("brandMark")
        mark.setFixedSize(28, 28)
        mark_row = QHBoxLayout(mark)
        mark_row.setContentsMargins(0, 0, 0, 0)
        self._brand_icon = QLabel(mark)
        self._brand_icon.setAlignment(Qt.AlignCenter)
        self._brand_icon.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        mark_row.addWidget(self._brand_icon)
        row.addWidget(mark)

        titles = QWidget(brand)
        col = QVBoxLayout(titles)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        title = QLabel("MaSai", titles)
        title.setObjectName("brandTitle")
        sub = QLabel("批量图片马赛克", titles)
        sub.setObjectName("brandSub")
        col.addWidget(title)
        col.addWidget(sub)
        row.addWidget(titles)
        return brand

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SPACE["lg"], SPACE["md"], SPACE["lg"], SPACE["md"])
        layout.setSpacing(SPACE["sm"])

        self.lbl_count_images = QLabel("0")
        self.lbl_count_images.setObjectName("countBadge")
        header, _ = _section("图片", self.lbl_count_images)
        layout.addWidget(header)

        self.lbl_images = QLabel("图片")
        self.lbl_images.setVisible(False)  # 保留属性名，标题已由 section 承担

        self.list_images = QListWidget(panel)
        self.list_images.setObjectName("imageList")
        self.list_images.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_images.setUniformItemSizes(True)
        self.list_images.setIconSize(QSize(16, 16))

        self.image_stack = QStackedWidget(panel)
        self.image_stack.addWidget(self._build_empty_list())
        self.image_stack.addWidget(self.list_images)
        layout.addWidget(self.image_stack, 1)

        self.lbl_folder = QLabel("尚未导入")
        self.lbl_folder.setObjectName("metaLabel")
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setToolTip("当前导入的文件夹")
        layout.addWidget(self.lbl_folder)

        # 导入之后必须能显式清空当前会话，否则只能覆盖、无法回到空状态；
        # 这里是唯一直接操作「当前文件夹」的入口，与顶部导入动作区分开。
        self.btn_reset = QPushButton("重置工作区", panel)
        self.btn_reset.setIconSize(QSize(16, 16))
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setToolTip("清空当前导入的文件夹、图片与区域，返回初始状态")
        layout.addWidget(self.btn_reset)
        return panel

    def _build_empty_list(self) -> QWidget:
        host = QWidget()
        host.setObjectName("emptyList")
        col = QVBoxLayout(host)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(SPACE["md"])
        col.setContentsMargins(SPACE["lg"], SPACE["lg"], SPACE["lg"], SPACE["lg"])
        self._empty_list_icon = QLabel(host)
        self._empty_list_icon.setAlignment(Qt.AlignCenter)
        col.addWidget(self._empty_list_icon)
        title = QLabel("还没有图片", host)
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title)
        body = QLabel("把文件夹拖进窗口，或点击上方的「导入文件夹」", host)
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        col.addWidget(body)
        return host

    def _build_center_panel(self) -> QWidget:
        host = QWidget(self)
        host.setObjectName("centerPanel")
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.canvas = ImageCanvas(self)
        grid.addWidget(self.canvas, 0, 0)

        self.zoom_holder = QWidget(host)
        zoom_row = QHBoxLayout(self.zoom_holder)
        zoom_row.setContentsMargins(SPACE["md"], SPACE["md"], SPACE["md"], 0)
        zoom_row.setSpacing(0)
        self.lbl_zoom = QLabel("100%", self.zoom_holder)
        self.lbl_zoom.setObjectName("zoomBadge")
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        zoom_row.addWidget(self.lbl_zoom)
        self.zoom_holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        grid.addWidget(self.zoom_holder, 0, 0, Qt.AlignTop | Qt.AlignRight)

        self.shortcut_chip = QWidget(host)
        self.shortcut_chip.setObjectName("overlayChip")
        chip_row = QHBoxLayout(self.shortcut_chip)
        chip_row.setContentsMargins(SPACE["md"], SPACE["sm"], SPACE["md"], SPACE["sm"])
        hint = QLabel("拖拽框选 · 中键平移 · 滚轮缩放 · Delete 删除选中",
                      self.shortcut_chip)
        hint.setObjectName("shortcutLabel")
        hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        chip_row.addWidget(hint)
        self.shortcut_chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        grid.addWidget(self.shortcut_chip, 0, 0, Qt.AlignBottom | Qt.AlignLeft)

        self.empty_guide = QWidget(host)
        self.empty_guide.setObjectName("emptyGuide")
        self.empty_guide.setFixedWidth(340)
        guide = QVBoxLayout(self.empty_guide)
        guide.setAlignment(Qt.AlignCenter)
        guide.setSpacing(SPACE["md"])
        guide.setContentsMargins(SPACE["xl"], SPACE["xl"], SPACE["xl"], SPACE["xl"])
        self._empty_guide_icon = QLabel(self.empty_guide)
        self._empty_guide_icon.setAlignment(Qt.AlignCenter)
        guide.addWidget(self._empty_guide_icon)
        title = QLabel("框出要打码的位置", self.empty_guide)
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignCenter)
        guide.addWidget(title)
        body = QLabel(
            "导入文件夹后，在图片上按住左键拖出矩形。\n"
            "区域按相对坐标保存，会等比例套用到整批不同尺寸的图片。",
            self.empty_guide)
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        guide.addWidget(body)
        self.empty_guide.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        grid.addWidget(self.empty_guide, 0, 0, Qt.AlignCenter)
        return host

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("rightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SPACE["lg"], SPACE["md"], SPACE["lg"], SPACE["md"])
        layout.setSpacing(SPACE["sm"])

        self.lbl_count_regions = QLabel("0")
        self.lbl_count_regions.setObjectName("countBadge")
        header, _ = _section("区域", self.lbl_count_regions)
        layout.addWidget(header)

        self.lbl_regions = QLabel("区域")
        self.lbl_regions.setVisible(False)  # 保留属性名，计数移到徽标

        self.list_regions = QListWidget(panel)
        self.list_regions.setObjectName("regionList")
        self.list_regions.setSelectionMode(QAbstractItemView.SingleSelection)
        self.region_stack = QStackedWidget(panel)
        self.region_stack.addWidget(self._build_empty_regions())
        self.region_stack.addWidget(self.list_regions)
        layout.addWidget(self.region_stack, 1)

        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        self.btn_delete = QPushButton("删除选中", panel)
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.setToolTip("删除当前选中的区域（Delete）")
        self.btn_clear = QPushButton("清空", panel)
        self.btn_clear.setToolTip("删除全部区域")
        row.addWidget(self.btn_delete, 1)
        row.addWidget(self.btn_clear, 1)
        layout.addLayout(row)

        layout.addSpacing(SPACE["sm"])
        layout.addWidget(_rule())
        header2, _ = _section("马赛克")
        layout.addWidget(header2)

        self.lbl_block = QLabel("块大小", panel)
        self.lbl_block.setObjectName("fieldLabel")
        self.slider_block = QSlider(Qt.Horizontal, panel)
        self.slider_block.setRange(2, MAX_BLOCK_PX)
        self.slider_block.setValue(DEFAULT_BLOCK_PX)
        self.spin_block = QSpinBox(panel)
        self.spin_block.setRange(2, MAX_BLOCK_PX)
        self.spin_block.setValue(DEFAULT_BLOCK_PX)
        self.spin_block.setSuffix(" px")
        self.spin_block.setFixedWidth(88)

        block_row = QHBoxLayout()
        block_row.setSpacing(SPACE["md"])
        block_row.addWidget(self.slider_block, 1)
        block_row.addWidget(self.spin_block)
        layout.addWidget(self.lbl_block)
        layout.addLayout(block_row)

        hint = QLabel("数值按参考图宽度换算；导出时按每张图的宽度等比缩放。", panel)
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addSpacing(SPACE["sm"])
        layout.addWidget(_rule())
        tips = QLabel("拖动区域的四角可调整范围 · 选中后按 Delete 删除", panel)
        tips.setObjectName("shortcutLabel")
        tips.setWordWrap(True)
        layout.addWidget(tips)
        layout.addStretch(1)
        return panel

    def _build_empty_regions(self) -> QWidget:
        host = QWidget()
        host.setObjectName("emptyList")
        col = QVBoxLayout(host)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(SPACE["sm"])
        col.setContentsMargins(SPACE["md"], SPACE["md"], SPACE["md"], SPACE["md"])
        self._empty_region_icon = QLabel(host)
        self._empty_region_icon.setAlignment(Qt.AlignCenter)
        col.addWidget(self._empty_region_icon)
        title = QLabel("还没有区域", host)
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title)
        body = QLabel("在画布上拖拽框出第一处要打码的位置", host)
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        col.addWidget(body)
        return host

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setObjectName("statusBar")
        bar.setFixedHeight(STATUS_BAR_H)
        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE["lg"], 0, SPACE["lg"], 0)
        row.setSpacing(SPACE["sm"])

        self.status_dot = QWidget(bar)
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(8, 8)
        row.addWidget(self.status_dot)

        self.lbl_status = QLabel("请导入图片文件夹", bar)
        self.lbl_status.setObjectName("statusLabel")
        row.addWidget(self.lbl_status, 1)

        self.progress = QProgressBar(bar)
        self.progress.setMinimum(0)
        self.progress.setMaximum(1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        row.addWidget(self.progress)

        self.btn_cancel = QPushButton("取消", bar)
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setVisible(False)
        row.addWidget(self.btn_cancel)
        return bar

    # ---------------- 主题 ----------------
    def _toggle_theme(self) -> None:
        self._theme.toggle()

    def _on_theme_changed(self, palette) -> None:
        sub, muted, text = palette.text_sub, palette.text_muted, palette.text
        self.act_import.setIcon(icon("folder_open", text, 18, muted))
        self.act_fit.setIcon(icon("fit", sub, 18, muted))
        self.act_zoom_out.setIcon(icon("zoom_out", sub, 18, muted))
        self.act_zoom_in.setIcon(icon("zoom_in", sub, 18, muted))
        self.act_export.setIcon(icon("export", palette.accent_text, 18, muted))
        dark = palette.key == "dark"
        self.act_theme.setText("浅色" if dark else "深色")
        self.act_theme.setToolTip("切换到浅色主题" if dark else "切换到深色主题")
        self.act_theme.setIcon(icon("sun" if dark else "moon", text, 18, muted))

        self.btn_delete.setIcon(icon("trash", sub, 16, muted))
        self.btn_clear.setIcon(icon("clear", sub, 16, muted))
        self.btn_cancel.setIcon(icon("clear", palette.danger, 16, muted))
        self.btn_reset.setIcon(icon("reset", sub, 16, muted))
        self._brand_icon.setPixmap(pixmap("grid", palette.accent, 18))
        self._empty_list_icon.setPixmap(pixmap("image", muted, 30))
        self._empty_guide_icon.setPixmap(pixmap("region", palette.accent, 32))
        self._empty_region_icon.setPixmap(pixmap("region", muted, 26))

        self.canvas.apply_palette(palette)
        self._sync_status_dot("busy" if self._worker is not None else "idle")
        if self._images:
            self._refresh_image_list()
        if self._regions:
            self._refresh_region_list()

    def _sync_status_dot(self, state: str) -> None:
        p = self._theme.palette
        color = {"idle": p.text_muted, "busy": p.accent,
                 "ok": p.success, "error": p.danger}.get(state, p.text_muted)
        self.status_dot.setStyleSheet(f"background:{color}; border-radius:4px;")

    # ---------------- 连接 ----------------
    def _connect(self) -> None:
        self.act_import.triggered.connect(self._choose_folder)
        self.act_fit.triggered.connect(self.canvas.fit_view)
        self.act_zoom_in.triggered.connect(lambda: self.canvas.zoom_by(1.25))
        self.act_zoom_out.triggered.connect(lambda: self.canvas.zoom_by(1 / 1.25))
        self.act_export.triggered.connect(self._export)
        self.act_theme.triggered.connect(self._toggle_theme)

        self.list_images.currentRowChanged.connect(self._on_reference_changed)
        self.list_regions.currentRowChanged.connect(self._on_region_row_changed)

        self.canvas.regionsEdited.connect(self._on_regions_edited)
        self.canvas.regionSelected.connect(self._on_region_selected)
        self.canvas.zoomChanged.connect(self._on_zoom_changed)

        self.btn_delete.clicked.connect(self.canvas.remove_selected)
        self.btn_clear.clicked.connect(self._clear_regions)
        self.btn_reset.clicked.connect(self._reset_session)

        self.slider_block.valueChanged.connect(self._on_block_changed)
        self.spin_block.valueChanged.connect(self._on_block_changed)
        self.btn_cancel.clicked.connect(self._cancel_batch)
        self._theme.changed.connect(self._on_theme_changed)

    def _on_zoom_changed(self, scale: float) -> None:
        self.lbl_zoom.setText(f"{round(scale * 100)}%")

    # ---------------- 导入 ----------------
    def _folder_dialog_start(self) -> Path:
        """文件夹对话框的起始目录。

        已导入时从当前文件夹的父目录开始，让同级目录一目了然；否则沿用上次
        位置的父目录或用户主目录。旧实现直接停在当前文件夹内部，用户想换到
        别的文件夹时会被困在里面，看起来像是「没法再导入」。
        """
        if self._folder is not None:
            return self._folder.parent
        return self._last_dir or Path.home()

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择图片文件夹", str(self._folder_dialog_start()))
        if path:
            self.load_folder(Path(path))

    def _reset_session(self) -> None:
        """显式清空当前会话，与「覆盖式再导入」互补。"""
        if self._worker is not None or not self._images:
            return
        if self._regions:
            answer = QMessageBox.question(
                self, "重置工作区",
                "重置将清除当前导入的文件夹、图片列表与已框选的区域，是否继续？")
            if answer != QMessageBox.Yes:
                return
        self._clear_session()

    def _clear_session(self) -> None:
        """复位全部导入状态，并同步刷新列表、画布、计数与状态栏。"""
        if self._folder is not None:
            # 重置后保留父目录，方便下一次直接选到同级文件夹
            self._last_dir = self._folder.parent
        self._folder = None
        self._images = []
        self._sizes = {}
        self._regions = []
        self._ref_index = -1
        self._ref_size = (0, 0)
        self._reset_block = False
        self._block_fraction = block_fraction_from_pixels(DEFAULT_BLOCK_PX, 1000)
        self._preview_timer.stop()

        for widget in (self.slider_block, self.spin_block):
            widget.blockSignals(True)
            widget.setValue(DEFAULT_BLOCK_PX)
            widget.blockSignals(False)

        self.list_images.blockSignals(True)
        self.list_images.clear()
        self.list_images.clearSelection()
        self.list_images.blockSignals(False)

        self.canvas.clear_image()
        self._refresh_image_list()
        self._refresh_region_list()
        self.progress.setVisible(False)
        self.progress.setValue(0)
        self._update_state()
        self.lbl_status.setText("已重置，请导入图片文件夹")

    def load_folder(self, folder: Path) -> None:
        images = scan_images(folder)
        if not images:
            QMessageBox.information(
                self, "没有图片",
                "该文件夹里没有可直接处理的图片。\n"
                "支持格式：jpg / jpeg / png / webp / bmp / tif / tiff / gif")
            return

        self._folder = folder
        self._last_dir = folder
        self._images = images
        self._regions = []
        self._ref_index = -1
        self._reset_block = True
        self._probe_sizes()

        self.list_images.blockSignals(True)
        self.list_images.clear()
        for path in images:
            item = QListWidgetItem()  # 内容由 _refresh_image_list 的自绘两行承担
            item.setToolTip(str(path))
            item.setSizeHint(QSize(0, 44))
            self.list_images.addItem(item)
        self.list_images.blockSignals(False)

        self.canvas.clear_regions(emit=False)
        self.list_images.setCurrentRow(0)
        self._refresh_image_list()
        if self._ref_index < 0:
            self._update_state()

    def _probe_sizes(self) -> None:
        self._sizes = {}
        for path in self._images:
            self._sizes[path] = probe_size(path)

    def _on_reference_changed(self, row: int) -> None:
        if not (0 <= row < len(self._images)):
            return
        path = self._images[row]
        try:
            with Image.open(path) as src:
                # 和导出时保持一致：先按 EXIF 方向摆正，否则区域坐标会错位
                image = ImageOps.exif_transpose(src)
                image.load()
        except Exception as exc:
            QMessageBox.warning(self, "打不开这张图",
                                f"{path.name}\n{type(exc).__name__}: {exc}")
            return

        self._ref_index = row
        self._ref_size = image.size
        if self._reset_block:
            # 新导入的文件夹：块大小按参考图宽度重算，避免沿用上一批的比例
            self._block_fraction = block_fraction_from_pixels(
                self.spin_block.value(), image.size[0])
            self._reset_block = False
        self.canvas.set_image(image, self._regions, self._block_fraction)
        self._sync_block_widgets()
        self._refresh_image_list()
        self._refresh_region_list()
        self._update_state()

    # ---------------- 区域 ----------------
    def _on_regions_edited(self, regions: list) -> None:
        self._regions = list(regions)
        self._refresh_region_list()
        self._update_state()

    def _on_region_selected(self, index: int) -> None:
        if 0 <= index < self.list_regions.count():
            self.list_regions.blockSignals(True)
            self.list_regions.setCurrentRow(index)
            self.list_regions.blockSignals(False)
        else:
            self.list_regions.blockSignals(True)
            self.list_regions.clearSelection()
            self.list_regions.blockSignals(False)

    def _on_region_row_changed(self, row: int) -> None:
        if row >= 0:
            self.canvas.select_region(row)

    def _delete_region_at(self, row: int) -> None:
        # 延后一拍，避免在按钮自己的点击处理里销毁承载它的 item widget
        QTimer.singleShot(0, lambda: self._do_delete_region(row))

    def _do_delete_region(self, row: int) -> None:
        if not (0 <= row < len(self.canvas._items)):
            return
        self.canvas.select_region(row)
        self.canvas.remove_selected()

    def _clear_regions(self) -> None:
        if not self._regions:
            return
        answer = QMessageBox.question(self, "清空区域", "确定要删除所有区域吗？")
        if answer == QMessageBox.Yes:
            self.canvas.clear_regions(emit=True)
            self._regions = []
            self._refresh_region_list()
            self._update_state()

    def _refresh_region_list(self) -> None:
        width, height = self._ref_size
        p = self._theme.palette
        self.list_regions.blockSignals(True)
        self.list_regions.clear()
        for index, region in enumerate(self._regions, 1):
            px_w = int(round(region.w * width)) if width else 0
            px_h = int(round(region.h * height)) if height else 0
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 36))
            self.list_regions.addItem(item)

            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(SPACE["sm"], 0, SPACE["xs"], 0)
            row.setSpacing(SPACE["xs"])
            label = QLabel(f"#{index}   {px_w} × {px_h} px", row_widget)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            remove = QToolButton(row_widget)
            remove.setObjectName("rowDelete")
            remove.setIcon(icon("clear", p.text_muted, 14, p.text_muted))
            remove.setIconSize(QSize(14, 14))
            remove.setFixedSize(24, 24)
            remove.setToolTip(f"删除区域 #{index}")
            remove.setCursor(Qt.PointingHandCursor)
            remove.clicked.connect(
                lambda checked=False, r=index - 1: self._delete_region_at(r))
            row.addWidget(label, 1)
            row.addWidget(remove)
            self.list_regions.setItemWidget(item, row_widget)
        self.list_regions.blockSignals(False)
        self.lbl_regions.setText(f"区域（{len(self._regions)}）")
        self.lbl_count_regions.setText(str(len(self._regions)))
        self.region_stack.setCurrentIndex(1 if self._regions else 0)

    # ---------------- 块大小 ----------------
    def _on_block_changed(self, value: int) -> None:
        if self.slider_block.value() != value:
            self.slider_block.blockSignals(True)
            self.slider_block.setValue(value)
            self.slider_block.blockSignals(False)
        if self.spin_block.value() != value:
            self.spin_block.blockSignals(True)
            self.spin_block.setValue(value)
            self.spin_block.blockSignals(False)
        width = self._ref_size[0]
        if width > 0:
            self._block_fraction = block_fraction_from_pixels(value, width)
            self._preview_timer.start()  # 合并连续拖动
        self._update_state()

    def _apply_block_preview(self) -> None:
        self.canvas.set_block_fraction(self._block_fraction)

    def _sync_block_widgets(self) -> None:
        width = self._ref_size[0]
        if width <= 0:
            return
        value = block_pixels(self._block_fraction, width)
        value = max(self.slider_block.minimum(), min(self.slider_block.maximum(), value))
        for widget in (self.slider_block, self.spin_block):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

    # ---------------- 列表显示 ----------------
    def _refresh_image_list(self) -> None:
        """两行式列表项：文件名 + 尺寸/状态，警告同时给图标和文字，不会被截断。"""
        ref_size = self._ref_size
        p = self._theme.palette
        for row, path in enumerate(self._images):
            item = self.list_images.item(row)
            if item is None:
                continue
            size = self._sizes.get(path)
            name = path.name
            unreadable = size is None
            warn = (not unreadable and ref_size[0]
                    and aspects_differ(ref_size, size, ASPECT_TOLERANCE))
            if unreadable:
                meta, meta_color, glyph = "无法读取", p.danger, "warning"
                item.setToolTip(f"{path}\n无法读取这张图片，导出时会跳过")
            elif warn:
                meta, meta_color, glyph = (
                    f"{size[0]} × {size[1]} · 宽高比不同", p.warning, "warning")
                item.setToolTip(
                    f"{path}\n宽高比与参考图不同，按比例套用后可能错位")
            else:
                meta, meta_color, glyph = (
                    f"{size[0]} × {size[1]}", p.text_muted, "image")
                item.setToolTip(str(path))
            # setItemWidget 不会替 delegate 隐藏 item 自带文字；不清空会双层叠字。
            # 可读内容全部由自绘两行承担，语义信息保留在 tooltip / UserRole。
            item.setData(Qt.UserRole, f"{name} · {meta}")
            item.setText("")

            widget = QWidget()
            widget.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(widget)
            row_layout.setContentsMargins(SPACE["xs"], 4, SPACE["xs"], 4)
            row_layout.setSpacing(SPACE["sm"])
            glyph_label = QLabel(widget)
            glyph_label.setFixedSize(16, 16)
            glyph_label.setPixmap(pixmap(glyph, meta_color, 16))
            glyph_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row_layout.addWidget(glyph_label, 0, Qt.AlignVCenter)

            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(1)
            name_label = QLabel(name, widget)
            name_label.setStyleSheet(
                f"color:{p.text}; font-size:12px; background:transparent;")
            name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            meta_label = QLabel(meta, widget)
            meta_label.setStyleSheet(
                f"color:{meta_color}; font-size:11px; background:transparent;")
            meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            text_col.addWidget(name_label)
            text_col.addWidget(meta_label)
            row_layout.addLayout(text_col, 1)
            self.list_images.setItemWidget(item, widget)

        self.lbl_images.setText(
            f"图片（{len(self._images)}）" + (f" · {self._folder.name}" if self._folder else ""))
        self.lbl_count_images.setText(str(len(self._images)))
        self.lbl_folder.setText(str(self._folder) if self._folder else "尚未导入")
        self.list_images.setCurrentRow(self._ref_index)

    def _update_state(self) -> None:
        has_images = bool(self._images)
        has_regions = bool(self._regions)
        self.list_regions.setEnabled(has_regions)
        self.btn_delete.setEnabled(has_regions)
        self.btn_clear.setEnabled(has_regions)
        self.slider_block.setEnabled(has_images)
        self.spin_block.setEnabled(has_images)
        self.act_export.setEnabled(has_images and has_regions)
        self.act_fit.setEnabled(has_images)
        self.act_zoom_in.setEnabled(has_images)
        self.act_zoom_out.setEnabled(has_images)
        self.btn_reset.setEnabled(has_images and self._worker is None)
        # 已导入时把顶部动作改写成「更换文件夹」，明确它仍然可用
        self.act_import.setText("更换文件夹" if has_images else "导入文件夹")
        self.act_import.setToolTip(
            "选择其他图片文件夹（Ctrl+O）" if has_images
            else "选择一个图片文件夹（Ctrl+O）")

        self.image_stack.setCurrentIndex(1 if has_images else 0)
        self.empty_guide.setVisible(not has_images)
        self.zoom_holder.setVisible(has_images)
        self.shortcut_chip.setVisible(has_images)
        self.region_stack.setCurrentIndex(1 if has_regions else 0)
        self.lbl_count_images.setText(str(len(self._images)))
        if not has_regions:
            self.lbl_count_regions.setText("0")

        block_px = self.spin_block.value()
        parts = []
        if has_images:
            parts.append(f"{len(self._images)} 张图片")
        if has_regions:
            parts.append(f"{len(self._regions)} 个区域")
        if has_images:
            parts.append(f"块 {block_px} px")
        self.lbl_status.setText(" · ".join(parts) if parts else "请导入图片文件夹")
        if self._worker is None:
            self._sync_status_dot("idle")

    # ---------------- 导出 ----------------
    def _export(self) -> None:
        if not self._images or not self._folder:
            return
        plan = MosaicPlan(list(self._regions), self._block_fraction)
        if plan.is_empty():
            QMessageBox.information(
                self, "还没有区域", "请先在画布上拖拽框出要打码的位置。")
            return

        default_dir = self._last_out or self._folder.parent / f"{self._folder.name}_mosaic"
        dialog = ExportDialog(self._folder, default_dir, len(self._images),
                              len(plan.regions), self)
        if dialog.exec() != QDialog.Accepted:
            return
        out_dir = dialog.out_dir()
        self._last_out = out_dir
        open_after = dialog.open_when_done()

        self._start_batch(out_dir, plan, open_after)

    def _start_batch(self, out_dir: Path, plan: MosaicPlan,
                     open_after: bool = False) -> None:
        self._cancel = threading.Event()
        self._worker = BatchWorker(self._images, out_dir, plan, self)
        self._open_after = open_after
        self._worker.progressed.connect(self._on_progress)
        self._worker.completed.connect(self._on_batch_done)
        self.progress.setRange(0, len(self._images))
        self.progress.setValue(0)
        self._set_busy(True)
        self.lbl_status.setText(f"正在导出到 {out_dir} …")
        self._worker.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.lbl_status.setText(f"处理中 {done}/{total} · {name}")

    def _on_batch_done(self, report) -> None:
        self._worker = None
        self._set_busy(False)
        self.progress.setValue(self.progress.maximum())
        if report.cancelled:
            self.lbl_status.setText(f"已取消 · 完成 {report.succeeded} 张")
            self._sync_status_dot("idle")
            return

        summary = f"完成 {report.succeeded}/{report.total} 张\n输出目录：{report.out_dir}"
        if report.failed:
            lines = [f"· {r.src.name}：{r.error}" for r in report.failed[:15]]
            if len(report.failed) > 15:
                lines.append(f"… 另有 {len(report.failed) - 15} 张失败")
            self.lbl_status.setText(
                f"完成 {report.succeeded}/{report.total}，{len(report.failed)} 张失败")
            self._sync_status_dot("error")
            self._ask_open_folder(report.out_dir)
            QMessageBox.warning(self, "部分图片未处理",
                                summary + "\n\n" + "\n".join(lines))
        else:
            self.lbl_status.setText(f"导出完成 · {report.succeeded} 张")
            self._sync_status_dot("ok")
            QMessageBox.information(self, "导出完成", summary)
            self._ask_open_folder(report.out_dir)

    def _ask_open_folder(self, out_dir: Path) -> None:
        if not self._open_after:
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))
        except Exception:
            pass

    def _cancel_batch(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        if self._worker is not None:
            self._worker.cancel()
        self.lbl_status.setText("正在停止…")
        self.btn_cancel.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.act_import.setEnabled(not busy)
        self.act_export.setEnabled(not busy and bool(self._regions))
        self.act_fit.setEnabled(not busy and bool(self._images))
        self.act_zoom_in.setEnabled(not busy and bool(self._images))
        self.act_zoom_out.setEnabled(not busy and bool(self._images))
        self.btn_cancel.setVisible(busy)
        self.btn_cancel.setEnabled(busy)
        self.progress.setVisible(busy)
        self.list_images.setEnabled(not busy)
        self.btn_reset.setEnabled(not busy and bool(self._images))
        self.splitter.widget(2).setEnabled(not busy)
        self.canvas.setEnabled(not busy)
        self._sync_status_dot("busy" if busy else "idle")

    # ---------------- 拖放与关闭 ----------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.load_folder(path)
                event.acceptProposedAction()
                return
            if path.is_file():
                self.load_folder(path.parent)
                event.acceptProposedAction()
                return

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._cancel_batch()
            self._worker.wait(3000)
        super().closeEvent(event)
