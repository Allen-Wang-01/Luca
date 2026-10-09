import pytest

from app.models.narration import LineVisual, LLMNarrationLine, NarrationLine, Visual, VisualItem
from app.services.narration_validator import (
    NarrationQualityError,
    attach_visuals,
    check_quality,
    filter_sources,
    repair_target_ids,
)

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


CHART = Visual(
    id="chart_1",
    type="bar",
    title="Revenue",
    unit="millions",
    items=[
        VisualItem(key="i1", label="Last year", value=100, role="item", raw_text="100", source_id="t_income__r0_q2_ly"),
        VisualItem(key="i2", label="This year", value=200, role="item", raw_text="200", source_id="t_income__r0_q2"),
    ],
)


def _llm_line(text="Some narration.", chart_id=None, chart_emphasis=None) -> LLMNarrationLine:
    return LLMNarrationLine(
        text=text, target_id="t_income__r0", source_urls=[], figures=[], calculations=[], chart_id=chart_id, chart_emphasis=chart_emphasis
    )


def test_lines_carry_the_chart_they_reference():
    lines, removed = attach_visuals(
        [_llm_line(), _llm_line(chart_id="chart_1"), _llm_line(chart_id="chart_1", chart_emphasis="i2")],
        {"chart_1": CHART},
    )

    assert lines[0].visual is None
    assert lines[1].visual == LineVisual(chart=CHART, emphasis=None)
    assert lines[2].visual == LineVisual(chart=CHART, emphasis="i2")
    assert removed == []


def test_a_chart_that_was_never_built_is_dropped_but_the_line_stays():
    lines, removed = attach_visuals([_llm_line(), _llm_line(chart_id="chart_9", chart_emphasis="i1")], {"chart_1": CHART})

    assert [l.text for l in lines] == ["Some narration.", "Some narration."]
    assert lines[1].visual is None
    assert [(r.line, r.chart_id, r.reason) for r in removed] == [(2, "chart_9", "unknown_chart")]


def test_an_unknown_emphasis_is_dropped_but_the_chart_stays():
    lines, removed = attach_visuals([_llm_line(chart_id="chart_1", chart_emphasis="i7")], {"chart_1": CHART})

    assert lines[0].visual == LineVisual(chart=CHART, emphasis=None)
    assert [(r.line, r.reason) for r in removed] == [(1, "unknown_emphasis")]


def test_a_chart_that_comes_back_later_is_only_shown_the_first_time():
    lines, removed = attach_visuals(
        [
            _llm_line(chart_id="chart_1", chart_emphasis="i1"),
            _llm_line(chart_id="chart_1", chart_emphasis="i2"),
            _llm_line(),
            _llm_line(chart_id="chart_1"),
            _llm_line(chart_id="chart_1", chart_emphasis="i2"),
        ],
        {"chart_1": CHART},
    )

    assert [l.visual is not None for l in lines] == [True, True, False, False, False]
    assert [(r.line, r.chart_id, r.reason) for r in removed] == [(4, "chart_1", "reappeared"), (5, "chart_1", "reappeared")]


def test_removed_visuals_are_numbered_without_blank_lines():
    lines, removed = attach_visuals([_llm_line(text="  "), _llm_line(chart_id="chart_9")], {})

    assert len(lines) == 1
    assert removed[0].line == 1


def test_repair_and_source_filtering_keep_the_chart():
    visual = LineVisual(chart=CHART, emphasis="i1")
    line = NarrationLine(text="Some narration.", target_id="t_income__r0_typo", sources=["https://a.com/x"], visual=visual)

    repaired, _ = repair_target_ids([line], VALID_IDS, "p_overview")
    filtered, _ = filter_sources(repaired, set())

    assert filtered[0].visual == visual


def test_quality_check_rejects_empty_and_mostly_invented_scripts():
    with pytest.raises(NarrationQualityError):
        check_quality([], 0)
    with pytest.raises(NarrationQualityError):
        check_quality([_line("p_overview")] * 4, repair_count=3)

    check_quality([_line("p_overview")] * 4, repair_count=2)  # half is still acceptable
