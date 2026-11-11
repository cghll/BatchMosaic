import numpy as np
import pytest

from masai.core.mosaic import mosaic_array


def noisy(height=120, width=200, channels=3, seed=7):
    rng = np.random.default_rng(seed)
    if channels == 0:
        return rng.integers(0, 256, (height, width), dtype=np.uint8)
    return rng.integers(0, 256, (height, width, channels), dtype=np.uint8)


def mask_of(rects, height, width):
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in rects:
        mask[max(0, y0):min(height, y1), max(0, x0):min(width, x1)] = True
    return mask


def test_pixels_outside_region_are_untouched():
    arr = noisy()
    rect = (40, 30, 100, 80)
    out = mosaic_array(arr, [rect], block=10)
    outside = ~mask_of([rect], *arr.shape[:2])
    assert np.array_equal(out[outside], arr[outside])


def test_every_pixel_inside_region_is_covered():
    """隐私要求：框内不留未打码的缝隙，边缘不满一块的部分也必须处理。"""
    arr = noisy()
    rect = (43, 27, 97, 74)
    out = mosaic_array(arr, [rect], block=10)
    inside = mask_of([rect], *arr.shape[:2])
    changed = np.any(out != arr, axis=2)
    assert changed[inside].all()


def test_blocks_align_to_global_grid():
    arr = noisy()
    block = 10
    rect = (43, 27, 97, 74)
    out = mosaic_array(arr, [rect], block=block)
    # 完整落在框内的单元格：整格同色，且等于该格原图均值
    for y in range(50, 70, block):
        for x in range(50, 90, block):
            cell = out[y:y + block, x:x + block]
            assert (cell == cell[0, 0]).all()
            expected = arr[y:y + block, x:x + block].reshape(-1, 3).mean(axis=0)
            assert np.allclose(cell[0, 0], expected, atol=1.0)


def test_edge_cells_use_only_in_region_pixels():
    """边缘被裁掉的单元格只统计框内像素，不能把框外像素的均值漏出去。"""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:, :] = 255                       # 框外全白
    arr[20:40, 20:40] = 0                 # 框内全黑
    out = mosaic_array(arr, [(20, 20, 40, 40)], block=8)
    # 框内应全黑（均值来自框内黑像素），框外保持白
    assert (out[20:40, 20:40] == 0).all()
    assert (out[:20, :] == 255).all()
    assert (out[:, :20] == 255).all()


def test_mosaic_is_idempotent():
    arr = noisy()
    rects = [(20, 20, 90, 70), (60, 40, 140, 100)]
    first = mosaic_array(arr, rects, block=8)
    second = mosaic_array(first, rects, block=8)
    assert np.array_equal(first, second)


def test_overlapping_regions_do_not_cascade():
    arr = noisy()
    a = (10, 10, 90, 90)
    b = (50, 50, 130, 130)
    both = mosaic_array(arr, [a, b], block=10)
    only_a = mosaic_array(arr, [a], block=10)
    only_b = mosaic_array(arr, [b], block=10)
    # 重叠处的块应等于原图块的均值，而不是被二次糊化
    ys, xs = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    in_a = (xs >= 10) & (xs < 90) & (ys >= 10) & (ys < 90)
    in_b = (xs >= 50) & (xs < 130) & (ys >= 50) & (ys < 130)
    overlap = in_a & in_b
    grid_aligned = ((xs % 10 == 0) & (ys % 10 == 0)) | ~overlap
    assert np.array_equal(both[overlap & grid_aligned], only_a[overlap & grid_aligned])
    assert np.array_equal(both[overlap & grid_aligned], only_b[overlap & grid_aligned])


def test_grayscale_2d_array():
    arr = noisy(channels=0)
    rect = (20, 20, 80, 60)
    out = mosaic_array(arr, [rect], block=10)
    assert out.shape == arr.shape
    cell = out[20:30, 20:30]
    assert (cell == cell[0, 0]).all()
    outside = ~mask_of([rect], *arr.shape[:2])
    assert np.array_equal(out[outside], arr[outside])


def test_rgba_alpha_is_averaged_within_block():
    arr = noisy(channels=4)
    out = mosaic_array(arr, [(0, 0, 40, 40)], block=10)
    cell = out[0:10, 0:10]
    assert (cell == cell[0, 0]).all()


def test_region_outside_image_is_ignored():
    arr = noisy()
    out = mosaic_array(arr, [(500, 500, 600, 600), (-40, -40, -10, -10)], block=10)
    assert np.array_equal(out, arr)


def test_partial_out_of_bounds_region_is_clamped():
    arr = noisy()
    rect = (-30, -30, 40, 40)
    out = mosaic_array(arr, [rect], block=8)
    inside = mask_of([rect], *arr.shape[:2])
    assert np.any(out[inside] != arr[inside])
    outside = ~inside
    assert np.array_equal(out[outside], arr[outside])


def test_copy_false_modifies_in_place():
    arr = noisy()
    original = arr.copy()
    out = mosaic_array(arr, [(0, 0, 20, 20)], block=10, copy=False)
    assert out is arr
    assert not np.array_equal(arr, original)


def test_tiny_block_is_clamped_to_two():
    arr = noisy()
    out = mosaic_array(arr, [(0, 0, 20, 20)], block=1)
    assert out.shape == arr.shape


def test_tiny_region_still_uniform_and_contained():
    """小到不足一个块时：框内变均匀，框外一点不动。"""
    arr = noisy()
    rect = (50, 50, 54, 54)
    out = mosaic_array(arr, [rect], block=10)
    patch = out[50:54, 50:54]
    assert (patch == patch[0, 0]).all()
    outside = ~mask_of([rect], *arr.shape[:2])
    assert np.array_equal(out[outside], arr[outside])


def test_single_pixel_region_is_noop():
    """1 像素区域没有可平均的邻居，结果必须与原图一致且不外溢。"""
    arr = noisy()
    out = mosaic_array(arr, [(50, 50, 51, 51)], block=10)
    assert np.array_equal(out[50, 50], arr[50, 50])
    changed = np.any(out != arr, axis=2)
    assert not changed.any()


def test_invalid_dimension_raises():
    with pytest.raises(ValueError):
        mosaic_array(np.zeros((2, 2, 2, 2), dtype=np.uint8), [], block=4)
