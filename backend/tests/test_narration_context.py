from app.models.report import Flag, Row, SumTerm
from app.services.narration_context import collect_target_ids, render_report_for_prompt


def test_collects_block_row_and_cell_ids(report):
    ids = collect_target_ids(report)

    assert {"p_overview", "t_income", "t_income__r0", "t_income__r0_q2", "t_income__r1_q2_ly"} <= ids
    assert "sec_results" not in ids  # sections are navigation, not narration targets


def test_render_lists_rows_and_cells_with_ids_and_raw_values(report):
    text = render_report_for_prompt(report)

    assert "[t_income__r0] Revenue: [t_income__r0_q2] 200 | [t_income__r0_q2_ly] 100" in text
    assert 'q2="Q2 FY26"' in text


def test_render_tells_apart_repeated_labels_and_marks_rows_that_are_not_amounts(statement):
    text = render_report_for_prompt(statement)

    assert "[t_ops__r1] Sales · Goods: " in text
    assert "[t_ops__r3] Cost of sales · Goods: " in text
    assert "[t_ops__r4] Net income: " in text
    assert "[t_ops__r6] Earnings per share · Basic (per share): " in text
    assert "[t_ops__r8] Shares used · Basic (number of shares, in thousands): " in text


def test_totals_with_the_same_label_are_told_apart_by_what_they_add_up(statement):
    table = statement.blocks[0]
    figures = table.rows[1].cells

    def total(index, part_index):
        row_id = f"t_ops__r{index}"
        cells = [cell.model_copy(update={"id": f"{row_id}_{cell.col_id}"}) for cell in figures]
        return Row(id=row_id, label="Total", cells=cells, sum_of=[SumTerm(row_id=f"t_ops__r{part_index}", sign="add")])

    table.rows += [total(9, 1), total(10, 3)]

    text = render_report_for_prompt(statement)

    assert "[t_ops__r9] Sales · Total: " in text
    assert "[t_ops__r10] Cost of sales · Total: " in text


def test_render_surfaces_flags_and_sections(report):
    text = render_report_for_prompt(report)

    assert "## Section: Results" in text
    assert "! FLAG: Other looks wrong" in text


def test_render_leaves_out_flags_that_are_not_about_a_figure(report):
    table = report.blocks[1]
    table.flags.append(Flag(severity="warning", code="ambiguous_columns", message="Columns share a label"))
    table.rows[0].flags.append(Flag(severity="warning", code="unconfirmed_sum", message="Revenue may not add up"))

    text = render_report_for_prompt(report)

    assert "Columns share a label" not in text
    assert "Revenue may not add up" not in text
    assert "! FLAG: Other looks wrong" in text


def test_render_includes_report_meta(report):
    text = render_report_for_prompt(report)

    assert "Company: Acme Corp (ACME)" in text
    assert "figures in millions" in text
