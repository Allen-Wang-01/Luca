import pytest

from app.models.narration import NarrationLine
from app.services.narration_validator import NarrationQualityError, check_quality, filter_sources, repair_target_ids

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


def test_repair_keeps_sources():
    line = NarrationLine(text="Per the news.", target_id="t_income__r0_q3", sources=["https://a.example"])

    lines, _ = repair_target_ids([line], VALID_IDS, "p_overview")

    assert lines[0].sources == ["https://a.example"]


def test_sources_must_come_from_searches():
    line = NarrationLine(text="x", target_id="p_overview", sources=["https://a.example/x", "https://invented.example"])

    lines, removed = filter_sources([line], {"https://a.example/x"})

    assert lines[0].sources == ["https://a.example/x"]
    assert [(r.line, r.url, r.reason) for r in removed] == [(1, "https://invented.example", "unverified")]


def test_removed_sources_record_which_line_cited_them():
    lines_in = [
        NarrationLine(text="x", target_id="p_overview", sources=[]),
        NarrationLine(text="y", target_id="p_overview", sources=["https://invented.example/a"]),
    ]

    _, removed = filter_sources(lines_in, set())

    assert [r.line for r in removed] == [2]


def test_source_matching_ignores_tracking_params_and_trailing_slash():
    seen = {"https://a.example/story?id=7&utm_source=openai"}
    line = NarrationLine(
        text="x",
        target_id="p_overview",
        sources=["https://A.example/story/?id=7", "https://a.example/story?id=7&utm_source=openai"],
    )

    lines, removed = filter_sources([line], seen)

    # Both spellings are the same page: kept once, in the search result's own spelling.
    assert lines[0].sources == ["https://a.example/story?id=7&utm_source=openai"]
    assert removed == []


def test_forum_social_and_video_sources_are_blocked_even_when_searched():
    seen = {
        "https://www.reddit.com/r/stocks/comments/abc",
        "https://youtu.be/xyz",
        "https://apnews.com/article/123",
    }
    line = NarrationLine(text="x", target_id="p_overview", sources=sorted(seen))

    lines, removed = filter_sources([line], seen)

    assert lines[0].sources == ["https://apnews.com/article/123"]
    assert [r.reason for r in removed] == ["blocked", "blocked"]


def test_blocklist_matches_whole_domains_only():
    # "x.com" must not catch every host that merely ends in those letters.
    seen = {"https://www.fedex.com/news", "https://mobile.x.com/post/1"}
    line = NarrationLine(text="x", target_id="p_overview", sources=sorted(seen))

    lines, removed = filter_sources([line], seen)

    assert lines[0].sources == ["https://www.fedex.com/news"]
    assert [r.url for r in removed] == ["https://mobile.x.com/post/1"]


def test_quality_check_rejects_empty_and_mostly_invented_scripts():
    with pytest.raises(NarrationQualityError):
        check_quality([], 0)
    with pytest.raises(NarrationQualityError):
        check_quality([_line("p_overview")] * 4, repair_count=3)

    check_quality([_line("p_overview")] * 4, repair_count=2)  # half is still acceptable
