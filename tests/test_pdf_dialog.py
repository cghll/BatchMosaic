"""PDF 转图片对话框：默认值、来源展开与校验。"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("pypdfium2")

from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from masai.ui.pdf_dialog import PdfDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def make_pdf(folder, name="doc.pdf"):
    import pypdfium2 as pdfium
    folder.mkdir(exist_ok=True)
    path = folder / name
    doc = pdfium.PdfDocument.new()
    doc.new_page(300, 400)
    doc.save(str(path))
    doc.close()
    return path


def ok_button(dialog):
    return dialog._buttons.button(QDialogButtonBox.Ok)


def test_defaults_and_source_expansion(app, tmp_path):
    folder = tmp_path / "pdfs"
    make_pdf(folder)
    dialog = PdfDialog(tmp_path)

    assert dialog.spin_dpi.value() == 200
    assert dialog.combo_format.currentText() == "PNG"
    assert not dialog.spin_quality.isEnabled()
    assert not ok_button(dialog).isEnabled()

    dialog._add_sources([folder])
    assert [p.name for p in dialog.sources()] == ["doc.pdf"]
    assert dialog.out_dir() == tmp_path / "pdfs_images"
    assert ok_button(dialog).isEnabled()
    options = dialog.options()
    assert options.dpi == 200 and options.fmt == "PNG" and options.pages == "all"


def test_jpeg_enables_quality_and_bad_pages_disable_ok(app, tmp_path):
    pdf = make_pdf(tmp_path / "a")
    dialog = PdfDialog(tmp_path)
    dialog._add_sources([pdf])

    dialog.combo_format.setCurrentText("JPEG")
    assert dialog.spin_quality.isEnabled()
    assert dialog.options().fmt == "JPEG"

    dialog.edit_pages.setText("3-1")
    assert not ok_button(dialog).isEnabled()
    assert "页码" in dialog.lbl_warn.text()

    dialog.edit_pages.setText("1")
    assert ok_button(dialog).isEnabled()


def test_output_file_and_missing_sources_are_rejected(app, tmp_path):
    pdf = make_pdf(tmp_path / "b")
    target = tmp_path / "a_file"
    target.write_text("x")
    dialog = PdfDialog(tmp_path)
    dialog._add_sources([pdf])
    dialog.edit.setText(str(target))

    assert not ok_button(dialog).isEnabled()
    assert "文件" in dialog.lbl_warn.text()

    dialog._sources = []
    dialog._refresh_sources()
    dialog.edit.setText(str(tmp_path / "out"))
    dialog._validate()
    assert not ok_button(dialog).isEnabled()
    assert "PDF" in dialog.lbl_warn.text()


def test_output_same_as_source_folder_is_rejected(app, tmp_path):
    folder = tmp_path / "same"
    make_pdf(folder)
    dialog = PdfDialog(tmp_path)
    dialog._add_sources([folder])
    dialog.edit.setText(str(folder))
    dialog._validate()
    assert not ok_button(dialog).isEnabled()
    assert "不能与" in dialog.lbl_warn.text()
