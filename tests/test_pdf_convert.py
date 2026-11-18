"""PDF 转图片：命名、格式、页码、取消与失败报告。"""

import threading

import pytest

pytest.importorskip("pypdfium2")
pytest.importorskip("PIL")

import pypdfium2 as pdfium  # noqa: E402
from PIL import Image  # noqa: E402

from masai.core.pdf_convert import (  # noqa: E402
    PdfConvertError,
    PdfRenderOptions,
    collect_pdfs,
    convert_pdfs,
)


def make_pdf(path, pages=2, width=300, height=400):
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(width, height)
    doc.save(str(path))
    doc.close()
    return path


def test_collect_pdfs_expands_folder_and_deduplicates(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    nested = tmp_path / "nested"
    nested.mkdir()
    make_pdf(nested / "b.pdf")

    found = collect_pdfs([tmp_path, pdf, nested])
    assert found == [pdf, nested / "b.pdf"]


def test_default_conversion_uses_png_and_200_dpi(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", pages=2)
    report = convert_pdfs([pdf], tmp_path / "out")

    assert report.total == 2 and report.succeeded == 2 and not report.failed
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == ["doc_p001.png", "doc_p002.png"]
    with Image.open(tmp_path / "out" / "doc_p001.png") as image:
        assert image.format == "PNG"
        assert image.size[0] == pytest.approx(300 * 200 / 72, abs=2)
        assert image.size[1] == pytest.approx(400 * 200 / 72, abs=2)


def test_page_spec_and_jpeg_output(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", pages=3)
    options = PdfRenderOptions(dpi=72, image_format="jpeg", quality=80,
                               pages="2")
    report = convert_pdfs([pdf], tmp_path / "out", options)

    assert report.succeeded == 1
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["doc_p002.jpg"]
    with Image.open(tmp_path / "out" / "doc_p002.jpg") as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (300, 400)


def test_duplicate_stems_get_parent_prefix(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    make_pdf(first / "report.pdf", pages=1)
    make_pdf(second / "report.pdf", pages=1)

    report = convert_pdfs([first, second], tmp_path / "out",
                          PdfRenderOptions(dpi=72))
    assert report.succeeded == 2
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == ["report_p001.png", "two_report_p001.png"]


def test_cancel_stops_between_pages(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf", pages=4)
    cancel = threading.Event()

    def on_progress(done, total, result):
        cancel.set()

    report = convert_pdfs([pdf], tmp_path / "out",
                          on_progress=on_progress, cancel_event=cancel)
    assert report.cancelled
    assert report.total == 4
    assert report.succeeded == 1
    assert len(list((tmp_path / "out").iterdir())) == 1


def test_out_of_range_page_is_reported(tmp_path):
    pdf = make_pdf(tmp_path / "short.pdf", pages=1)
    report = convert_pdfs([pdf], tmp_path / "out",
                          PdfRenderOptions(dpi=72, pages="9"))
    assert report.total == 1 and report.succeeded == 0
    assert "没有选中任何页面" in report.failed[0].error


def test_corrupt_pdf_is_reported(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    report = convert_pdfs([bad], tmp_path / "out")
    assert report.total == 1 and report.succeeded == 0
    assert len(report.failed) == 1
    assert report.failed[0].src == bad
    assert report.failed[0].error


def test_invalid_options_are_rejected(tmp_path):
    with pytest.raises(PdfConvertError):
        PdfRenderOptions(dpi=10).validate()
    with pytest.raises(PdfConvertError):
        PdfRenderOptions(pages="2-1").validate()
    assert PdfRenderOptions(pages="1-3,5").page_indices(6) == [0, 1, 2, 4]
    # 语法合法即可；页数不足由具体文件在转换时报「没有选中任何页面」
    assert PdfRenderOptions(pages="5").page_indices(2, allow_empty=True) == []
    PdfRenderOptions(pages="5").validate()
