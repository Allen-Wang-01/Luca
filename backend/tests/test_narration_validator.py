import pytest

from app.models.narration import NarrationLine
from app.services.narration_validator import NarrationQualityError, check_quality, repair_target_ids

VALID_IDS = {"p_overview", "t_income", "t_income__r0", "t_income__r0_q2"}


def _line(target_id: str, text: str = "Some narration.") -> NarrationLine:
    return NarrationLine(text=text, target_id=target_id)


def test_valid_targets_are_untouched():
    lines, repairs = repair_target_ids([_line("t_income__r0_q2"), _line("p_overview")], VALID_IDS, "p_overview")

    assert [l.target_id for l in lines] == ["t_income__r0_q2", "p_overview"]
    assert repairs == 0


def test_bad_cell_id_falls_back_to_its_row():
    lines, repairs = repair_target_ids([_line("t_income__r0_q3")], VALID_IDS, "p_overview")

    assert lines[0].target_id == "t_income__r0"
    assert repairs == 1


def test_bad_row_id_falls_back_to_its_block():
    lines, _ = repair_target_ids([_line("t_income__r9_q2")], VALID_IDS, "p_overview")

    assert lines[0].target_id == "t_income"


def test_unrecognizable_id_reuses_previous_target():
    lines, _ = repair_target_ids([_line("t_income__r0"), _line("made_up")], VALID_IDS, "p_overview")

    assert lines[1].target_id == "t_income__r0"


def test_unrecognizable_first_line_uses_fallback():
    lines, _ = repair_target_ids([_line("made_up")], VALID_IDS, "p_overview")

    assert lines[0].target_id == "p_overview"


def test_blank_lines_are_dropped():
    lines, _ = repair_target_ids([_line("p_overview", "   "), _line("p_overview")], VALID_IDS, "p_overview")

    assert len(lines) == 1


def test_quality_check_rejects_empty_and_mostly_invented_scripts():
    with pytest.raises(NarrationQualityError):
        check_quality([], 0)
    with pytest.raises(NarrationQualityError):
        check_quality([_line("p_overview")] * 4, repair_count=3)

    check_quality([_line("p_overview")] * 4, repair_count=2)  # half is still acceptable
