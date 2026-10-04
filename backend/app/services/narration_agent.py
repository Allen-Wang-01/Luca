# Turns a parsed FinancialReport into an advisor-style narration script. This is a
# hand-rolled tool-calling loop on the Responses API rather than an SDK agent runner, so
# every turn is visible: each one calls the model, runs any calculation tools it asked
# for (app/services/narration_tools.py), and feeds the results back, until the model
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
    LLMNarrationScript,
    NarrationLine,
    NarrationTrace,
    ToolCallTrace,
    WebSearchTrace,
)
from app.models.report import FinancialReport
from app.services import llm_client, narration_context, narration_tools, narration_validator

logger = get_logger(__name__)

# The last turn always forbids tools, so the model has MAX_TURNS - 1 turns to calculate.
MAX_TURNS = 6
# Across all turns - a model stuck re-requesting calculations gets told to stop.
MAX_TOOL_CALLS = 60
# Across all turns. Each search is billed per call and adds its results to the context,
# so this is both a cost and a latency guard. Once it's used up, the tool is withdrawn.
MAX_WEB_SEARCHES = 5

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search"}

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
didn't calculate it with a tool, don't say it. Tools look values up themselves; each \
operand is a reference, not a number:
- a figure in a table: {id: <cell id>, quote: null}
- a figure that only appears in paragraph text: {id: <paragraph id>, quote: <just the \
figure, exactly as written there, e.g. "$3.2 billion">} - it is checked against the \
paragraph, so copy it character for character.
Table and paragraph figures can be mixed freely; units are reconciled for you. Look \
for the insightful comparisons (a segment's share of the total, the growth implied by \
guidance versus the current quarter) and request all the calculations you need in \
parallel, in as few turns as possible. If a tool returns an error, fix the operand and \
retry. If the report already prints a figure (e.g. a Y/Y column), quote it instead of \
recomputing it.

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
Ids appear in [brackets] in the report below. Cell ids are not listed individually: a \
cell's id is its row id + "_" + its column id, e.g. row [t_results__r0] and column \
q3_2024 give cell id t_results__r0_q3_2024. Only use ids that exist in this report. \
Prefer moving through the report roughly in document order so the view doesn't jump \
around, and don't put more than three consecutive lines on the same target.

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


def generate_narration(
    report: FinancialReport,
    client: Any = None,
) -> tuple[list[NarrationLine], NarrationTrace]:
    client = client or llm_client.client
    index = narration_tools.FigureIndex(report)
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
    parsed: LLMNarrationScript | None = None

    for turn_number in range(1, MAX_TURNS + 1):
        is_last_turn = turn_number == MAX_TURNS
        searches_left = MAX_WEB_SEARCHES - web_searches_used
        tools = list(narration_tools.TOOL_DEFINITIONS)
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

    cited = [NarrationLine(text=l.text, target_id=l.target_id, sources=l.source_urls) for l in parsed.lines]
    sourced, dropped_urls, blocked_urls = narration_validator.filter_sources(cited, seen_urls)
    fallback_id = report.blocks[0].id if report.blocks else ""
    lines, repair_count = narration_validator.repair_target_ids(
        sourced, narration_context.collect_target_ids(report), fallback_id
    )
    narration_validator.check_quality(lines, repair_count)

    trace = NarrationTrace(
        turns=turns,
        total_input_tokens=sum(t.input_tokens for t in turns),
        total_output_tokens=sum(t.output_tokens for t in turns),
        total_cost_usd=sum(t.cost_usd for t in turns),
        total_duration_ms=sum(t.duration_ms for t in turns),
        total_web_searches=web_searches_used,
        repaired_target_ids=repair_count,
        dropped_source_urls=dropped_urls,
        blocked_source_urls=blocked_urls,
    )
    logger.info(
        "narration_done turns=%d lines=%d web_searches=%d sourced_lines=%d dropped_source_urls=%d blocked_source_urls=%d repaired_target_ids=%d total_cost_usd=%.6f total_duration_ms=%d",
        len(turns),
        len(lines),
        web_searches_used,
        sum(1 for line in lines if line.sources),
        dropped_urls,
        blocked_urls,
        repair_count,
        trace.total_cost_usd,
        trace.total_duration_ms,
    )
    return lines, trace
