import numpy as np
import pytest
from PIL import Image

from masai.core.batch import run_batch
from masai.core.pipeline import (
    ProcessingError,
    process_image,
    probe_size,
    scan_images,
)
from masai.core.regions import MosaicPlan, Region


def noisy_rgb(size=(200, 120), seed=3):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr)


def test_scan_images_filters_and_sorts(tmp_path):
    (tmp_path / "b.PNG").write_bytes(b"x")
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("ignore me")
    (tmp_path / "sub").mkdir()
    names = [p.name for p in scan_images(tmp_path)]
    assert names == ["a.jpg", "b.PNG"]


def test_png_keeps_name_format_and_size(tmp_path):
    src = tmp_path / "a.png"
    noisy_rgb().save(src)
    plan = MosaicPlan([Region(0.2, 0.25, 0.3, 0.4)], block_fraction=0.05)

    dst = tmp_path / "out" / "a.png"
    result = process_image(src, dst, plan)

    assert result.ok, result.error
    assert dst.exists()
    with Image.open(dst) as out:
        assert out.format == "PNG"
        assert out.size == (200, 120)


def test_only_region_pixels_change(tmp_path):
    src = tmp_path / "a.png"
    noisy_rgb().save(src)
    plan = MosaicPlan([Region(0.2, 0.25, 0.3, 0.4)], block_fraction=0.05)
    dst = tmp_path / "a_out.png"
    assert process_image(src, dst, plan).ok

    before = np.array(Image.open(src))
    after = np.array(Image.open(dst))
    assert np.array_equal(before[:30, :], after[:30, :])
    assert np.array_equal(before[:, :40], after[:, :40])
    assert not np.array_equal(before[30:78, 40:100], after[30:78, 40:100])


def test_same_region_applies_proportionally(tmp_path):
    big = tmp_path / "big.png"
    noisy_rgb(size=(400, 240), seed=5).save(big)
    plan = MosaicPlan([Region(0.2, 0.25, 0.3, 0.4)], block_fraction=0.05)

    dst = tmp_path / "big_out.png"
    assert process_image(big, dst, plan).ok

    arr = np.array(Image.open(dst))
    # 区域换算到 400x240 上为 (80,60)-(200,156)，块大小 20
    cell = arr[60:80, 80:100]
    assert (cell == cell[0, 0]).all()
    assert np.array_equal(arr[:60, :], np.array(Image.open(big))[:60, :])


def test_exif_orientation_is_applied(tmp_path):
    src = tmp_path / "rot.jpg"
    img = noisy_rgb(size=(120, 60))
    exif = Image.Exif()
    exif[0x0112] = 6  # 顺时针旋转 90°，显示时应为 60x120
    img.save(src, format="JPEG", exif=exif)

    dst = tmp_path / "rot_out.jpg"
    result = process_image(src, dst, MosaicPlan([]))
    assert result.ok, result.error

    with Image.open(dst) as out:
        assert out.size == (60, 120)
        assert out.getexif().get(0x0112, 1) == 1


def test_probe_size_follows_exif_orientation(tmp_path):
    plain = tmp_path / "plain.jpg"
    noisy_rgb(size=(120, 60)).save(plain, format="JPEG")
    assert probe_size(plain) == (120, 60)

    rotated = tmp_path / "rot.jpg"
    img = noisy_rgb(size=(120, 60))
    exif = Image.Exif()
    exif[0x0112] = 6  # 顺时针旋转 90°，摆正后宽高互换
    img.save(rotated, format="JPEG", exif=exif)
    assert probe_size(rotated) == (60, 120)

    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    assert probe_size(broken) is None


def test_jpeg_keeps_format(tmp_path):
    src = tmp_path / "photo.jpg"
    noisy_rgb().save(src, quality=90)
    dst = tmp_path / "photo_out.jpg"
    result = process_image(src, dst, MosaicPlan([Region(0.1, 0.1, 0.2, 0.2)],
                                                block_fraction=0.04))
    assert result.ok, result.error
    with Image.open(dst) as out:
        assert out.format == "JPEG"
        assert out.size == (200, 120)


def test_palette_png_is_handled(tmp_path):
    src = tmp_path / "pal.png"
    noisy_rgb().convert("P", palette=Image.Palette.ADAPTIVE).save(src)
    dst = tmp_path / "pal_out.png"
    result = process_image(src, dst, MosaicPlan([Region(0.1, 0.1, 0.3, 0.3)],
                                                block_fraction=0.05))
    assert result.ok, result.error


def test_broken_file_is_reported_not_raised(tmp_path):
    src = tmp_path / "broken.png"
    src.write_bytes(b"not really a png")
    result = process_image(src, tmp_path / "o.png", MosaicPlan([]))
    assert not result.ok
    assert result.error


def test_animated_gif_is_skipped(tmp_path):
    src = tmp_path / "anim.gif"
    frames = [noisy_rgb(size=(40, 40), seed=i).convert("P") for i in range(3)]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=100,
                   loop=0)
    result = process_image(src, tmp_path / "anim_out.gif", MosaicPlan([]))
    assert not result.ok
    assert "动图" in (result.error or "")


def test_no_regions_still_normalizes(tmp_path):
    src = tmp_path / "plain.png"
    noisy_rgb().save(src)
    dst = tmp_path / "plain_out.png"
    assert process_image(src, dst, MosaicPlan([])).ok
    assert np.array_equal(np.array(Image.open(src)), np.array(Image.open(dst)))


def test_batch_processes_all_and_reports_progress(tmp_path):
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    for i in range(3):
        noisy_rgb(seed=i).save(src_dir / f"img{i}.png")

    seen = []
    out_dir = tmp_path / "out"
    report = run_batch(scan_images(src_dir), out_dir,
                       MosaicPlan([Region(0.2, 0.2, 0.3, 0.3)], block_fraction=0.05),
                       on_progress=lambda done, total, res: seen.append((done, total)),
                       max_workers=2)

    assert report.total == 3
    assert report.succeeded == 3
    assert not report.failed
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert sorted(p.name for p in out_dir.iterdir()) == ["img0.png", "img1.png", "img2.png"]