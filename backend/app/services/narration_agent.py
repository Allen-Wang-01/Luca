# Turns a parsed FinancialReport into an advisor-style narration script. This is a
# hand-rolled tool-calling loop on the Responses API rather than an SDK agent runner, so
# every turn is visible: each one calls the model, runs any calculation tools
# (app/services/narration_tools.py) and chart tools (app/services/narration_visuals.py)
# it asked for, and feeds the results back, until the model
# returns the final script or MAX_TURNS is reached. Every turn is logged and recorded
# in a NarrationTrace that the endpoint returns alongside the script.
#
# The model also has the API's built-in web search, for outside context on changes the
# report itself doesn't explain. Those searches run on OpenAI's side within a single
# model call, so this loop doesn't execute them - it records what was searched and
# which URLs came back, caps the total with MAX_WEB_SEARCHES, and uses the returned
# URLs to verify the sources the model cites.
import json
import time
from typing import Any

from app.core.logging import get_logger
from app.core.pricing import calculate_cost, calculate_web_search_cost
from app.models.narration import (
    AgentTurn,
    LLMNarrationLine,
    LLMNarrationScript,
    LLMScriptEdits,
    NarrationLine,
    NarrationReview,
    NarrationTrace,
    RemovedLine,
    ReviewFinding,
    ToolCallTrace,
    WebSearchTrace,
)
from app.models.report import FinancialReport
from app.services import (
    llm_client,
    narration_context,
    narration_figures,
    narration_notes,
    narration_reviewer,
    narration_tools,
    narration_validator,
    narration_visuals,
)

logger = get_logger(__name__)

# The last turn always forbids tools, so the model has MAX_TURNS - 1 turns to calculate.
# A calculation on an earlier result needs that result's id first, so each extra step
# takes a turn of its own.
MAX_TURNS = 8
# Across all turns - a model stuck re-requesting calculations gets told to stop.
MAX_TOOL_CALLS = 60
# Across all turns. Each search is billed per call and adds its results to the context,
# so this is both a cost and a latency guard. Once it's used up, the tool is withdrawn.
MAX_WEB_SEARCHES = 5

# Turns the agent gets to fix what the review of its script found, on top of MAX_TURNS.
# The second is only used when a figure is still wrong after the first.
MAX_CORRECTIONS = 2

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search"}

# The tools this loop runs itself: calculations, charts, and notes on search results.
FUNCTION_TOOLS: list[dict[str, Any]] = [
    *narration_tools.TOOL_DEFINITIONS,
    *narration_visuals.TOOL_DEFINITIONS,
    narration_notes.TOOL_DEFINITION,
]

INSTRUCTIONS = """You are a sharp, friendly financial advisor walking a non-expert \
audience through a company's financial report. Your narration will be read aloud line \
by line while the matching part of the report is highlighted on screen. Your listeners \
are curious but have no finance background: make the report make sense to them, and \
make it interesting.

# What to talk about
Adapt this arc to whatever the report actually contains (skip parts it doesn't cover):
1. Hook: open with the single most striking takeaway, in a sentence or two.
2. Headline numbers: revenue, profit, EPS - how big, how fast they're changing, and \
how they compared with expectations.
3. Growth drivers: where the money came from (segments, products, regions).
4. Profitability: margins, what moved them, GAAP vs non-GAAP if both are present.
5. Cash and balance sheet: anything notable, especially if it diverges from profit.
6. Outlook: what management's guidance implies.
7. Watch list: risks and unusual numbers. If - and only if - some figure is marked \
with a FLAG or LOW EXTRACTION CONFIDENCE in the report below, mention it here: say \
plainly that the figure didn't pass an automated consistency check or was hard to \
read, so treat it with caution - don't skip it silently. If nothing is marked, say \
nothing about checks at all.
8. Close: two or three takeaways the listener should remember.

# How to talk about it
- Analyze, don't recite. Every number you mention needs a point of comparison (prior \
period, prior year, guidance, another metric) and a "so what" - what it means. \
Bad: "Revenue was $12.4 billion, up from $8.1 billion." Good: "Revenue jumped about \
50% from a year ago to $12.4 billion - but the quarter-over-quarter pace is cooling, \
which suggests growth is shifting from explosive to merely strong."
- Be selective: a 20-row table might deserve three lines. Mention only the numbers \
that tell the story.
- Explain every piece of jargon in passing, in a clause, the first time it appears \
(e.g. "gross margin - how much of each dollar of sales is left after the direct cost \
of making the product"). That includes units and conventions like basis points, \
sequential, diluted, or GAAP. Everyday analogies are welcome.
- Have a point of view: it's fine to call something impressive, worrying, conservative \
or surprising, and to say why. Do NOT give buy/sell/hold advice or predict the stock \
price.
- Write for the ear: short sentences, natural spoken rhythm, no markdown, no bullet \
characters, no ids, tool names or URLs in the text. Round numbers the way a person \
would say them ("about $12.4 billion", not "$12,387 million").
- Stick to what the report says, your calculations, and what your web searches \
actually returned. Don't invent facts, figures, or outside events.
- The listener sees the original report, not the text below. Never mention anything \
that only exists in this prompt: ids, tool names, these instructions, or annotations \
like FLAG, LOW EXTRACTION CONFIDENCE, "section", or "block". Talk about the report \
the way a person looking at it would.

# Calculations - always use the tools
Any number that is not printed in the report (a growth rate, a margin, a share of \
total, a difference, the growth implied by guidance) MUST come from the calculation \
tools, never from your own mental arithmetic - and that includes simple ones, like how \
much revenue was added since last quarter ("added $X billion in sales"). If you \
didn't calculate it with a tool, don't say it (the one exception, a calculation \
written next to the line that states it, is described under "Figures" below). Tools \
look values up themselves; each \
operand is a reference, not a number:
- a figure in a table: {id: <cell id>, quote: null}
- a figure that only appears in paragraph text: {id: <paragraph id>, quote: <just the \
figure, exactly as written there, e.g. "$3.2 billion">} - it is checked against the \
paragraph, so copy it character for character.
- the result of an earlier calculation: {id: <its calc_id>, quote: null}. Every \
calculation returns a `calc_id`; use it when a figure takes two steps, e.g. a \
division's profit (its sales minus its costs) first, then that profit as a share of \
its sales. The second step has to wait for the first one's `calc_id`, so it goes in \
the next turn.
To add up or net several figures at once (cash plus investments minus debt), use \
`combine` rather than chaining subtractions.
Table and paragraph figures can be mixed freely; units are reconciled for you. Look \
for the insightful comparisons (a segment's share of the total, the growth implied by \
guidance versus the current quarter) and request all the calculations you need in \
parallel, in as few turns as possible. If a tool returns an error, fix the operand and \
retry. If the report already prints a figure (e.g. a Y/Y column), quote it instead of \
recomputing it.

# Figures - say where each number comes from
Every line has a `figures` list: one reference for each amount and each percentage \
the line states, in the same form as a tool operand - a cell id, a paragraph id with \
the figure quoted from it, or the `calc_id` of a calculation. After you finish, each \
number in your text is compared with the figures its line lists, so:
- List the cell you actually mean: the right row and the right period. A sentence \
about this year that quotes last year's column is the most common mistake - when you \
write a number, check which column it sits in.
- A number you calculated lists its `calc_id`, not the cells that went into it. If a \
line says both "$4.1 billion" and "up 12%", it lists the cell and the calculation.
- A number that comes to you while writing, with no tool call behind it - "that is 2.4 \
points more than last year", "together they come to $9.3 billion" - goes in the line's \
`calculations` instead: name the figures and the operation, and the arithmetic is done \
for you and compared with what the line says. This is for the one-step figure you \
didn't plan; anything you can foresee, and anything a chart needs, still goes through \
the tools before you write. A number with neither behind it must not be said.
- Rounding the way a person would say it is fine ("about $4.1 billion" for 4,118 in \
millions). A different number is not.
- Keep a comparison within one period unless you say otherwise: "sales of 500 against \
a profit of 80" takes both from the same column.
- A figure from a web page has nothing to list; its line carries the page in \
`source_urls` instead.
A line whose number matches nothing it lists is sent back to you to fix, and cut if \
it still doesn't.

# Outside context - web search
A report says what happened; a good advisor also knows how it compared with what was \
expected, and why things happened that the report only states. Before writing, do \
your homework with web search on exactly these two things:
1. Expectations: how the headline results (typically revenue and EPS, and guidance if \
given) compared with what analysts expected going in - a beat, a miss, or in line. \
This gives a non-expert listener a yardstick: a growth rate means more once you know \
whether the market saw it coming.
2. The why behind the report: pick the one to three most important things the report \
states but doesn't explain - e.g. a figure or outlook that excludes or depends on a \
market, product or condition without saying why, a large unusual gain or charge with no \
stated cause, a sharp change in a trend, or a risk it names only in passing - and look \
up the cause.
Rules for what you find:
- Use outside sources for facts (what was expected, what happened, what management \
said), never for opinions: don't relay analyst ratings, price targets, stock price \
moves, or other commentators' views. Your point of view stays your own, grounded in \
the report and your calculations.
- Put the company name and fiscal period in your queries. If you use information about \
a later period than the report's, say so explicitly ("in the following quarter...") so \
the listener never mistakes it for part of this report.
- Take notes, in the same turn as the search. The pages a search returns are only \
visible to you in the turn you searched in; in every later turn - including the one \
where you write the script - they are gone, and all you have is what you noted. So \
right after a search, call `note_finding` once for each fact you intend to use: the \
fact as the page states it, with its figures, and the page's URL exactly as the search \
returned it. Then, when you write, a line that uses a noted fact puts that note's URL \
in `source_urls`. Never state an outside fact, figure or event you have no note for, \
and never write a URL from memory.
- Cite reliable sources: the company's own filings and releases, and established news \
organizations. Never cite forums, social media, or video sites (e.g. Reddit, X, \
YouTube) - such URLs are removed from the script, which would leave your claim \
unsourced.
- A figure from a web page (e.g. an expected revenue number) can't go into the \
calculation tools: quote it as stated and attribute it, and don't do arithmetic with it.
- The report wins: never let outside information override a figure in the report.
- When a line uses something you found, attribute it in the spoken text ("analysts \
had expected...", "according to news coverage at the time...") and list the page \
URL(s) in that line's `source_urls`, copied exactly from your search results. \
`source_urls` is only for what came from outside the report: a line whose facts and \
figures are all in the report - even a summary line - has empty `source_urls`, even if \
some page repeats the same figures. Never cite a URL that didn't come from a search.
- If a search turns up nothing reliable, leave that point out rather than guess.

# Targeting - what each line highlights
Every line has a `target_id`: the part of the report highlighted and zoomed while that \
line is spoken. The more precise it is, the better the effect. Pick the MOST SPECIFIC \
id that matches what the line is about:
- the line's key number is one table value -> that CELL (e.g. "operating income \
reached $2.9 billion" -> the operating income cell for this quarter). Prefer this \
whenever one figure carries the line, even if the line mentions its growth rate too.
- the line compares a metric across several columns -> the row id
- a passage of text, or a table/chart discussed as a whole -> the block id
Use the item the line is actually about, not a nearby one with a similar value: if \
the line is about a one-time gain, target the row that records that gain, not a \
subtotal that happens to include it. A line \
about outside context targets the part of the report it helps explain.
Opening and closing lines should target the headline passage or the main summary \
table. Never target legal boilerplate (forward-looking statement disclaimers, \
definitions of non-GAAP measures) unless the line is actually about it.
Ids appear in [brackets] in the report below, each one right before the thing it \
names: a block, a table row, or a single cell value. A row line reads \
"[t_results__r0] Operating income: [t_results__r0_q3_2024] 2,900 | ..." - the first id \
is the row, and each id after the colon is the cell holding the value that follows it. \
Copy ids exactly as written; only use ids that exist in this report. \
Prefer moving through the report roughly in document order so the view doesn't jump \
around, and don't put more than three consecutive lines on the same target.

# Charts - a picture for the lines that need one
A line can bring up a small chart next to what it highlights. Use one where a picture \
makes the point faster than the sentence: how a metric moved across periods, how much \
of a whole one part makes up, or how one figure turns into another (revenue down to \
operating income, a reported profit to an adjusted one). Aim for three to six charts \
in the whole script; a line that makes its point with a single number needs none.
- Build a chart with the chart tools before writing the script. Like the calculation \
tools, they take references, never numbers, and look the values up themselves. Each \
returns a `chart_id` and a `key` for every item in it.
- A chart is checked before it is accepted: a waterfall's steps must lead exactly from \
its start to its end, and a share bar's parts can't exceed its total. If a tool \
returns an error, fix the chart and call it again, or do without it. Only a chart that \
returned a `chart_id` can be shown.
- To show a chart, put its `chart_id` on the line that discusses it. If the line is \
about one item in it, also set `chart_emphasis` to that item's `key`: that item is \
drawn in full and the rest fades. Leave `chart_emphasis` null when the line is about \
the chart as a whole.
- Only emphasize an item the line actually names. If the figure the line is about is \
not one of the chart's items - a subtotal partway through a waterfall, say, when the \
chart only has the steps around it - leave `chart_emphasis` null rather than pointing \
at the nearest item.
- When a line compares two items, emphasize the one the line is about, not the one \
it is measured against: "sales rose 12% from last quarter's $4.1 billion" is about \
this quarter, so emphasize this quarter's bar, not last quarter's.
- One chart can stay up for two or three lines in a row, each emphasizing a different \
item ("the biggest piece is...", "but the fastest-growing one is...") - that reads \
better than a new chart per line. Those lines must be next to each other: a line \
without the chart in between makes the card disappear and pop up again. Once you move \
on from a chart, don't bring it back.
- A chart's figures can also be results of your calculations: pass a `calc_id` where a \
figure goes. That is how to draw what the report doesn't print, such as a margin in \
each of several periods or each division's growth rate side by side. Calculate \
first; the chart goes in the next turn, once the `calc_id`s are back. Such items are \
marked as calculated on the card.
- The spoken line still has to make sense on its own, without the chart.

# Output
Produce 25 to 40 lines. Each line is 1-3 sentences. Write every line in English.
"""


def _as_input_item(item: Any) -> dict[str, Any]:
    # Output items are fed back as input on the next turn. The parsed-response models
    # carry client-side `parsed`/`parsed_arguments` fields the API doesn't accept back,
    # and a web search's `action.sources` is output-only data requested via `include`.
    data = item.to_dict(mode="json", exclude_none=True)
    data.pop("parsed_arguments", None)
    for content in data.get("content", []) or []:
        if isinstance(content, dict):
            content.pop("parsed", None)
    action = data.get("action")
    if isinstance(action, dict):
        action.pop("sources", None)
    return data


def _web_search_trace(item: Any) -> WebSearchTrace:
    action = item.action
    if action.type == "search":
        query = action.query or "; ".join(action.queries or []) or None
        sources = [source.url for source in action.sources or []]
    else:  # open_page / find_in_page act on a single URL
        query = getattr(action, "pattern", None)
        sources = [action.url] if getattr(action, "url", None) else []
    return WebSearchTrace(action=action.type, query=query, sources=sources)


def _cited_urls(output: list[Any]) -> set[str]:
    # URL citations the API attached to the model's own message text - also pages the
    # model really saw, alongside the search results themselves.
    urls: set[str] = set()
    for item in output:
        if item.type != "message":
            continue
        for content in getattr(item, "content", None) or []:
            for annotation in getattr(content, "annotations", None) or []:
                if getattr(annotation, "type", None) == "url_citation":
                    urls.add(annotation.url)
    return urls


def _correction_request(lines: list[LLMNarrationLine], findings: list[ReviewFinding], last_chance: bool) -> str:
    # The whole script goes along, numbered: edits refer to lines by number, and after
    # an earlier round of edits the numbers are no longer those of the model's draft.
    script = "\n".join(f"{number}. {line.text}" for number, line in enumerate(lines, start=1))
    by_line: dict[int, list[ReviewFinding]] = {}
    for finding in findings:
        by_line.setdefault(finding.line, []).append(finding)
    problems = "\n\n".join(
        f'Line {number}: "{line_findings[0].text}"\n'
        + "\n".join(
            f"- [{'MUST FIX' if finding.must_fix else 'CHECK'}] {finding.detail}" for finding in line_findings
        )
        for number, line_findings in sorted(by_line.items())
    )
    closing = (
        "This is the last pass: any line that still has a MUST FIX problem after it is cut as it stands, with "
        "nothing reworded around it. So where you can't fix a line, remove it yourself, as described above."
        if last_chance
        else "A line that still has a MUST FIX problem afterwards will be cut."
    )
    return f"""Your script was checked against the report, line by line. This is the script as it stands, \
numbered:

{script}

These lines have problems:

{problems}

Return `edits`: only the lines you change, each by its number above. Every line you don't list stays exactly \
as it is, so don't repeat lines that need no change.
- 'replace' gives the whole line as it should now be - text, target, figures and all, not just the part that \
changed.
- 'remove' takes the line out.
- An empty list means every line stays as it is.
How to fix what was found:
- MUST FIX, a figure that matches none of the line's `figures`: either the sentence states the wrong number \
(say the one the report has), or the number is right and its reference is missing from `figures` (add the \
cell id, the paragraph quote, or the calc_id it came from).
- A figure you worked out yourself, with no tool call behind it: keep it by putting the calculation in the \
line's `calculations` - the figures it uses and the operation. It is then done for you and compared with what \
the line says, so if the result differs from your number, the line has to say the result.
- A figure taken from a web page is only accepted on a line whose `source_urls` has that page's URL exactly \
as a search returned it. If the problem says the page is not one a search returned, copy the right URL from \
your search results, character for character; if the figure isn't in any of them, take the claim out.
- MUST FIX, a reference that doesn't exist or a calculation that failed: replace the id with the one you \
meant, copied from the report, or correct the calculation's terms.
- CHECK: look at the line and the figures again. If the sentence presents a figure as the wrong period or the \
wrong item, correct the sentence or cite the right figure. If the line is right as it is, leave it.
- You can't call tools or search now. A number that neither a reference nor a one-step calculation in \
`calculations` can back has to go: reword the line without it.
- If a line can't be fixed, remove it, and replace its neighbours where needed so the script still flows: no \
line may refer back to something that is no longer said, and the thread from one line to the next has to hold \
without it.
{closing}"""


def _review_and_correct(
    client: Any,
    report: FinancialReport,
    index: narration_tools.FigureIndex,
    seen_urls: set[str],
    input_items: list[Any],
    response: Any,
    lines: list[LLMNarrationLine],
    turns: list[AgentTurn],
) -> tuple[list[LLMNarrationLine], NarrationReview]:
    """Checks the script's figures against what each line cites, has a second model
    read it (narration_reviewer.py), and gives the agent up to MAX_CORRECTIONS turns
    to fix what was found. Returns (the lines that hold up, what was found).

    Corrections are the agent's own turns, in its own conversation, so it fixes a line
    with everything it knew when drafting - but without tools: a correction is one
    call, not a new loop. It returns only the lines it changes (LLMScriptEdits); the
    rest of the script is not written out again and cannot come back different. Lines
    the agent removes itself come with their neighbours reworded; cutting one here is
    the last resort for a figure that is still wrong."""
    unit_note = f"Report figures are in {report.meta.currency} {report.meta.unit_scale} unless a label says otherwise."
    review = NarrationReview(rounds=[])
    for attempt in range(MAX_CORRECTIONS + 1):
        review_round = narration_figures.check_script(lines, index, seen_urls)
        findings = review_round.findings
        if attempt == 0:
            reviewer_findings, reviewer_usage = narration_reviewer.review(lines, index, unit_note, client)
            findings.extend(reviewer_findings)
            if reviewer_usage:
                review.reviewer_input_tokens = reviewer_usage["input_tokens"]
                review.reviewer_output_tokens = reviewer_usage["output_tokens"]
                review.reviewer_cost_usd = reviewer_usage["cost_usd"]
                review.reviewer_duration_ms = reviewer_usage["duration_ms"]
        review.rounds.append(review_round)

        # Advice alone is worth one correction turn, not a second: the agent has
        # already looked at it once.
        worth_a_turn = findings if attempt == 0 else [f for f in findings if f.must_fix]
        if attempt == MAX_CORRECTIONS or not worth_a_turn:
            break

        input_items.extend(_as_input_item(item) for item in response.output)
        last_chance = attempt == MAX_CORRECTIONS - 1
        input_items.append({"role": "user", "content": _correction_request(lines, findings, last_chance)})
        start = time.monotonic()
        response = client.responses.parse(
            model=llm_client.MODEL,
            instructions=INSTRUCTIONS,
            input=input_items,
            tools=FUNCTION_TOOLS,
            tool_choice="none",
            text_format=LLMScriptEdits,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        edits = response.output_parsed.edits if response.output_parsed else []
        lines, applied = narration_validator.apply_edits(lines, edits)
        usage = response.usage
        cost = calculate_cost(llm_client.MODEL, usage.input_tokens, usage.output_tokens)
        turns.append(
            AgentTurn(
                turn=len(turns) + 1,
                purpose="correction",
                tool_calls=[],
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
                duration_ms=duration_ms,
            )
        )
        logger.info(
            "narration_correction turn=%d findings=%d must_fix=%d edits=%d applied=%d input_tokens=%d output_tokens=%d cost_usd=%.6f duration_ms=%d",
            len(turns),
            len(findings),
            sum(1 for f in findings if f.must_fix),
            len(edits),
            applied,
            usage.input_tokens,
            usage.output_tokens,
            cost,
            duration_ms,
        )

    # `rounds[-1]` is always a check of `lines` as they now stand.
    failed: dict[int, str] = {}
    for finding in review.rounds[-1].findings:
        if finding.must_fix:
            failed.setdefault(finding.line, finding.detail)
    review.removed_lines = [
        RemovedLine(text=lines[number - 1].text, detail=detail) for number, detail in sorted(failed.items())
    ]
    return [line for number, line in enumerate(lines, start=1) if number not in failed], review


def generate_narration(
    report: FinancialReport,
    client: Any = None,
) -> tuple[list[NarrationLine], NarrationTrace]:
    client = client or llm_client.client
    index = narration_tools.FigureIndex(report)
    chart_builder = narration_visuals.ChartBuilder(index)
    input_items: list[Any] = [
        {
            "role": "user",
            "content": "Here is the parsed report. Write the narration script.\n\n"
            + narration_context.render_report_for_prompt(report),
        }
    ]

    turns: list[AgentTurn] = []
    tool_calls_used = 0
    web_searches_used = 0
    seen_urls: set[str] = set()
    notebook = narration_notes.Notebook(seen_urls)
    parsed: LLMNarrationScript | None = None

    for turn_number in range(1, MAX_TURNS + 1):
        is_last_turn = turn_number == MAX_TURNS
        searches_left = MAX_WEB_SEARCHES - web_searches_used
        tools = list(FUNCTION_TOOLS)
        search_kwargs: dict[str, Any] = {}
        if searches_left > 0 and not is_last_turn:
            tools.append(WEB_SEARCH_TOOL)
            # Caps built-in tool calls within this one response; the model can search
            # several times inside a single call, beyond this loop's control.
            search_kwargs["max_tool_calls"] = searches_left

        start = time.monotonic()
        response = client.responses.parse(
            model=llm_client.MODEL,
            instructions=INSTRUCTIONS,
            input=input_items,
            tools=tools,
            tool_choice="none" if is_last_turn else "auto",
            include=["web_search_call.action.sources"],
            text_format=LLMNarrationScript,
            **search_kwargs,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        web_searches = [_web_search_trace(item) for item in response.output if item.type == "web_search_call"]
        web_searches_used += len(web_searches)
        for search in web_searches:
            seen_urls.update(search.sources)
        seen_urls.update(_cited_urls(response.output))

        function_calls = [item for item in response.output if item.type == "function_call"]
        turn_traces: list[ToolCallTrace] = []
        if function_calls:
            input_items.extend(_as_input_item(item) for item in response.output)
            for call in function_calls:
                if tool_calls_used >= MAX_TOOL_CALLS:
                    arguments = {}
                    output = {"error": "Calculation budget exhausted. Write the final script now."}
                elif call.name in narration_visuals.TOOL_NAMES:
                    arguments, output = narration_visuals.execute_tool(chart_builder, call.name, call.arguments)
                    tool_calls_used += 1
                elif call.name == narration_notes.TOOL_NAME:
                    # `seen_urls` already has this response's search results (above),
                    # so a note can cite a page from the search it was taken in.
                    arguments, output = narration_notes.execute_tool(notebook, call.arguments)
                    tool_calls_used += 1
                else:
                    arguments, output = narration_tools.execute_tool(index, call.name, call.arguments)
                    tool_calls_used += 1
                turn_traces.append(ToolCallTrace(name=call.name, arguments=arguments, output=output))
                input_items.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(output)}
                )

        usage = response.usage
        cost = calculate_cost(llm_client.MODEL, usage.input_tokens, usage.output_tokens) + calculate_web_search_cost(
            len(web_searches)
        )
        turns.append(
            AgentTurn(
                turn=turn_number,
                tool_calls=turn_traces,
                web_searches=web_searches,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
                duration_ms=duration_ms,
            )
        )
        logger.info(
            "narration_turn turn=%d tool_calls=%d errors=%d web_searches=%d input_tokens=%d output_tokens=%d cost_usd=%.6f duration_ms=%d",
            turn_number,
            len(turn_traces),
            sum(1 for t in turn_traces if "error" in t.output),
            len(web_searches),
            usage.input_tokens,
            usage.output_tokens,
            cost,
            duration_ms,
        )
        for search in web_searches:
            logger.info("narration_web_search turn=%d action=%s query=%r sources=%d", turn_number, search.action, search.query, len(search.sources))

        if not function_calls:
            parsed = response.output_parsed
            break

    if parsed is None:
        raise narration_validator.NarrationQualityError(
            f"Model did not produce a narration script within {MAX_TURNS} turns."
        )

    draft_lines = [line for line in parsed.lines if line.text.strip()]
    checked_lines, review = _review_and_correct(
        client, report, index, seen_urls, input_items, response, draft_lines, turns
    )
    narration_validator.check_removed_lines(len(review.removed_lines), review.rounds[-1].lines)

    cited, removed_visuals = narration_validator.attach_visuals(checked_lines, chart_builder.charts)
    fallback_id = report.blocks[0].id if report.blocks else ""
    targeted, repair_count = narration_validator.repair_target_ids(
        cited, narration_context.collect_target_ids(report), fallback_id
    )
    # After the repair pass, which drops blank lines, so the line numbers recorded for
    # removed sources match the script the listener gets.
    lines, removed_sources = narration_validator.filter_sources(targeted, seen_urls)
    narration_validator.check_quality(lines, repair_count)
    dropped_urls = sum(1 for source in removed_sources if source.reason == "unverified")
    blocked_urls = len(removed_sources) - dropped_urls

    trace = NarrationTrace(
        turns=turns,
        total_input_tokens=sum(t.input_tokens for t in turns) + (review.reviewer_input_tokens or 0),
        total_output_tokens=sum(t.output_tokens for t in turns) + (review.reviewer_output_tokens or 0),
        total_cost_usd=sum(t.cost_usd for t in turns) + (review.reviewer_cost_usd or 0),
        total_duration_ms=sum(t.duration_ms for t in turns) + (review.reviewer_duration_ms or 0),
        total_web_searches=web_searches_used,
        repaired_target_ids=repair_count,
        dropped_source_urls=dropped_urls,
        blocked_source_urls=blocked_urls,
        removed_sources=removed_sources,
        removed_visuals=removed_visuals,
        review=review,
    )
    for number, review_round in enumerate(review.rounds, start=1):
        for finding in review_round.findings:
            logger.info(
                "narration_review_finding round=%d line=%d check=%s must_fix=%s detail=%s",
                number,
                finding.line,
                finding.check,
                finding.must_fix,
                finding.detail,
            )
    for removed in review.removed_lines:
        logger.info("narration_line_removed detail=%s text=%r", removed.detail, removed.text)
    for source in removed_sources:
        logger.info("narration_source_removed line=%d reason=%s url=%s", source.line, source.reason, source.url)
    for visual in removed_visuals:
        logger.info(
            "narration_visual_removed line=%d reason=%s chart_id=%s detail=%s",
            visual.line,
            visual.reason,
            visual.chart_id,
            visual.detail,
        )
    logger.info(
        "narration_done turns=%d lines=%d figures_confirmed=%d review_rounds=%d removed_lines=%d charts=%d illustrated_lines=%d web_searches=%d notes=%d sourced_lines=%d dropped_source_urls=%d blocked_source_urls=%d repaired_target_ids=%d total_cost_usd=%.6f total_duration_ms=%d",
        len(turns),
        len(lines),
        review.rounds[-1].figures_confirmed,
        len(review.rounds),
        len(review.removed_lines),
        len(chart_builder.charts),
        sum(1 for line in lines if line.visual),
        web_searches_used,
        len(notebook.notes),
        sum(1 for line in lines if line.sources),
        dropped_urls,
        blocked_urls,
        repair_count,
        trace.total_cost_usd,
        trace.total_duration_ms,
    )
    return lines, trace
