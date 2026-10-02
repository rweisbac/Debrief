from scripts.check_style import find_em_dashes


def test_no_em_dashes_in_repo():
    assert find_em_dashes() == []
