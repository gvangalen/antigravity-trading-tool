from backend.utils.data_normalizers import normalize_targets


def test_normalize_targets_accepts_bracketed_number_string():
    assert normalize_targets("[2700.0, 2900.0]") == [2700.0, 2900.0]


def test_normalize_targets_accepts_json_number_list_string():
    assert normalize_targets("[70000,80000,85000]") == [70000.0, 80000.0, 85000.0]


def test_normalize_targets_still_accepts_plain_csv():
    assert normalize_targets("75000, 80000, 85000") == [75000.0, 80000.0, 85000.0]
