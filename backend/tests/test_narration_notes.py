import json

from app.services.narration_notes import MAX_NOTES, TOOL_DEFINITION, TOOL_NAME, Notebook, execute_tool

FACT = "Analysts expected revenue of $12.1 billion."


def _note(notebook, **arguments):
    _, output = execute_tool(notebook, json.dumps(arguments))
    return output


def test_a_note_keeps_the_fact_with_the_searchs_own_spelling_of_the_url():
    notebook = Notebook({"https://news.example/story?id=7&utm_source=openai"})

    output = _note(notebook, fact=f"  {FACT} ", url="https://News.example/story/?id=7")

    assert output == {"note_id": "note_1", "fact": FACT, "url": "https://news.example/story?id=7&utm_source=openai"}
    assert notebook.notes == [output]


def test_a_url_no_search_returned_is_refused_while_it_can_still_be_corrected():
    notebook = Notebook({"https://news.example/a1b2c3"})

    output = _note(notebook, fact=FACT, url="https://news.example/analysts-expected-more")

    assert "not among the pages your searches returned" in output["error"]
    assert notebook.notes == []
    assert _note(notebook, fact=FACT, url="https://news.example/a1b2c3")["note_id"] == "note_1"


def test_a_forum_page_cannot_be_noted():
    notebook = Notebook({"https://www.reddit.com/r/stocks/1"})

    assert "forum" in _note(notebook, fact=FACT, url="https://www.reddit.com/r/stocks/1")["error"]


def test_a_note_can_cite_a_page_from_a_search_that_ran_after_the_notebook_was_opened():
    seen_urls: set[str] = set()
    notebook = Notebook(seen_urls)

    seen_urls.add("https://news.example/later")

    assert "note_id" in _note(notebook, fact=FACT, url="https://news.example/later")


def test_notes_are_limited_and_malformed_ones_are_errors():
    notebook = Notebook({"https://news.example/a"})

    assert "error" in _note(notebook, fact="  ", url="https://news.example/a")
    assert "error" in _note(notebook, fact=FACT, url="")
    assert "error" in execute_tool(notebook, json.dumps({"fact": FACT}))[1]
    for _ in range(MAX_NOTES):
        _note(notebook, fact=FACT, url="https://news.example/a")
    assert "limit" in _note(notebook, fact=FACT, url="https://news.example/a")["error"]
    assert len(notebook.notes) == MAX_NOTES


def test_the_tool_definition_matches_what_is_executed():
    assert TOOL_DEFINITION["name"] == TOOL_NAME
    assert TOOL_DEFINITION["parameters"]["required"] == ["fact", "url"]
