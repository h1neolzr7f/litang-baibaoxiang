from app.mosaic import MOSAIC_PARTS, _detector_parts_with_fallback


def test_all_four_parts_available() -> None:
    assert MOSAIC_PARTS == ["欧金金", "欧芒果", "欧派派", "欧西利"]


def test_empty_parts_fall_back_to_all() -> None:
    assert _detector_parts_with_fallback([]) == [MOSAIC_PARTS]


def test_user_subset_then_full_cover() -> None:
    attempts = _detector_parts_with_fallback(["欧金金"])
    assert attempts[0] == ["欧金金"]
    assert attempts[1] == MOSAIC_PARTS
