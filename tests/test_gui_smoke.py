"""界面冒烟测试：offscreen 平台下实例化窗口并走一遍核心交互。"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from masai.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def make_folder(tmp_path, count=3, size=(400, 300)):
    folder = tmp_path / "pics"
    folder.mkdir()
    rng = np.random.default_rng(1)
    for i in range(count):
        arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
        Image.fromarray(arr).save(folder / f"p{i}.jpg", quality=92)
    return folder


def test_window_loads_folder_and_tracks_regions(app, tmp_path):
    folder = make_folder(tmp_path)
    window = MainWindow()
    try:
        window.load_folder(folder)
        assert window.canvas.has_image()
        assert window.list_images.count() == 3
        assert window._regions == []

        item = window.canvas._add_item(QRectF(20, 20, 120, 80))
        item.setSelected(True)
        window.canvas._emit_regions()

        assert len(window._regions) == 1
        assert window.act_export.isEnabled()
        assert window.list_regions.count() == 1
        assert "区域" in window.lbl_regions.text()
    finally:
        window.close()


def test_switching_reference_keeps_normalized_regions(app, tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    rng = np.random.default_rng(2)
    Image.fromarray(rng.integers(0, 256, (300, 400, 3), dtype=np.uint8)).save(
        folder / "a.jpg")
    Image.fromarray(rng.integers(0, 256, (600, 800, 3), dtype=np.uint8)).save(
        folder / "b.jpg")

    window = MainWindow()
    try:
        window.load_folder(folder)
        window.canvas._add_item(QRectF(40, 30, 160, 90)).setSelected(True)
        window.canvas._emit_regions()
        saved = list(window._regions)

        window.list_images.setCurrentRow(1)
        assert window.canvas.image_size() == (800, 600)
        assert window._regions == saved
        # 放大一倍后区域像素框也应放大一倍
        rect = window.canvas.regions()[0]
        assert rect.x == pytest.approx(40 / 400, abs=0.01)
    finally:
        window.close()


def test_block_slider_updates_canvas(app, tmp_path):
    folder = make_folder(tmp_path, count=1)
    window = MainWindow()
    try:
        window.load_folder(folder)
        window.slider_block.setValue(32)
        assert window.spin_block.value() == 32
        assert window._block_fraction == pytest.approx(32 / 400)
    finally:
        window.close()


def test_export_requires_regions(app, tmp_path):
    folder = make_folder(tmp_path, count=1)
    window = MainWindow()
    try:
        window.load_folder(folder)
        assert not window.act_export.isEnabled()
    finally:
        window.close()


def test_reset_session_clears_state_and_allows_reimport(app, tmp_path, monkeypatch):
    """导入后必须能重置回空状态，再导入另一个文件夹；对话框不能停在旧目录内。"""
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.Yes)
    folder_a = make_folder(tmp_path)
    folder_b = tmp_path / "another"
    folder_b.mkdir()
    Image.fromarray(
        np.random.default_rng(9).integers(0, 256, (240, 320, 3), dtype=np.uint8)
    ).save(folder_b / "b.png")

    window = MainWindow()
    try:
        assert not window.btn_reset.isEnabled()
        window.load_folder(folder_a)
        window.canvas._add_item(QRectF(10, 10, 80, 60)).setSelected(True)
        window.canvas._emit_regions()
        assert window._regions and window.act_export.isEnabled()
        assert window.act_import.text() == "更换文件夹"
        assert window._folder_dialog_start() == folder_a.parent

        window.btn_reset.click()
        assert window._folder is None
        assert window._images == [] and window._sizes == {}
        assert window._regions == [] and window._ref_index == -1
        assert window._ref_size == (0, 0)
        assert window.list_images.count() == 0
        assert window.list_regions.count() == 0
        assert not window.canvas.has_image()
        assert window.canvas.image_size() == (0, 0)
        assert window.image_stack.currentIndex() == 0
        assert window.lbl_folder.text() == "尚未导入"
        assert window.lbl_zoom.text() == "100%"
        assert not window.act_export.isEnabled()
        assert not window.btn_reset.isEnabled()
        assert window.act_import.text() == "导入文件夹"
        assert window._folder_dialog_start() == folder_a.parent

        window.load_folder(folder_b)
        assert window._folder == folder_b
        assert window.list_images.count() == 1
        assert window.canvas.has_image()
        assert window._regions == []
        assert window.act_import.text() == "更换文件夹"
    finally:
        window.close()


def test_reference_image_honours_exif_orientation(app, tmp_path):
    """带 EXIF 旋转的参考图必须按摆正后的方向显示，否则区域坐标会错位。"""
    folder = tmp_path / "rotated"
    folder.mkdir()
    img = Image.fromarray(
        np.random.default_rng(3).integers(0, 256, (200, 400, 3), dtype=np.uint8))
    exif = Image.Exif()
    exif[0x0112] = 6  # 顺时针 90°，摆正后是 200×400
    img.save(folder / "rot.jpg", format="JPEG", exif=exif)

    window = MainWindow()
    try:
        window.load_folder(folder)
        assert window.canvas.image_size() == (200, 400)
        # 列表里显示的尺寸也应是摆正后的，避免宽高比误报
        assert window._sizes[window._images[0]] == (200, 400)
        assert not window.list_images.item(0).text().startswith("⚠")
    finally:
        window.close()