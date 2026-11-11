"""导出对话框：路径校验与默认值。"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from masai.ui.export_dialog import ExportDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def make_dialog(tmp_path, default):
    src = tmp_path / "pics"
    if not src.exists():
        src.mkdir()
    return ExportDialog(src, default, image_count=3, region_count=2)


def test_default_path_and_open_flag(app, tmp_path):
    dialog = make_dialog(tmp_path, tmp_path / "pics_mosaic")
    assert dialog.out_dir() == tmp_path / "pics_mosaic"
    assert dialog.open_when_done() is True
    assert dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_nonexistent_folder_is_allowed(app, tmp_path):
    dialog = make_dialog(tmp_path, tmp_path / "deep" / "nested" / "out")
    assert dialog.lbl_warn.isVisible() is False
    assert dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_source_folder_is_rejected(app, tmp_path):
    dialog = make_dialog(tmp_path, tmp_path / "pics")
    assert dialog.lbl_warn.text()
    assert not dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_empty_path_is_rejected(app, tmp_path):
    dialog = make_dialog(tmp_path, tmp_path / "out")
    dialog.edit.setText("   ")
    assert not dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_file_path_is_rejected(app, tmp_path):
    target = tmp_path / "a_file"
    target.write_text("x")
    dialog = make_dialog(tmp_path, target)
    assert "文件" in dialog.lbl_warn.text()
    assert not dialog._buttons.button(QDialogButtonBox.Ok).isEnabled()
