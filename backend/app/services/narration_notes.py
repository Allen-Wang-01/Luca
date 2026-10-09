# The narration model's notes on what its web searches found. A search runs on OpenAI's
# side inside one model call, and the pages it returns are only visible to the model
# within that call: what comes back to this loop is the query and the list of URLs, not
# the content, so there is nothing to carry into the next turn. A model that searched in
# turn 1 and wrote its script in turn 3 had forgotten what it read - it either said
# there was nothing to report, or wrote from a vague memory and made up a link to go
# with it.
#
# So it writes down what it means to use, while it can still see the page: one
# `note_finding` call per fact, with the page's URL. Tool calls and their outputs stay
# in the conversation, so the notes are there when the script is written. The URL is
# checked on the spot against what the searches really returned - the model can still
# correct it then, which it cannot do once the results are gone. No I/O.
from typing import Any

from app.services import narration_validator
from app.services.narration_tools import call_tool

TOOL_NAME = "note_finding"

# Per run. A note is for a fact the script will use, not a summary of every page.
MAX_NOTES = 12


class Notebook:
    """The notes taken during one narration run."""

    def __init__(self, seen_urls: set[str]) -> None:
        # The loop's own set of the URLs searches have returned so far - shared, not
        # copied, so a note can cite a page from the search that just ran.
        self._seen_urls = seen_urls
        self.notes: list[dict[str, str]] = []

    def add(self, fact: Any, url: Any) -> dict[str, Any]:
        if not isinstance(fact, str) or not fact.strip():
            return {"error": "`fact` must be a non-empty sentence stating what the page says."}
        if not isinstance(url, str) or not url.strip():
            return {"error": "`url` must be the URL of the page the fact is from."}
        if len(self.notes) >= MAX_NOTES:
            return {"error": f"Note limit reached ({MAX_NOTES}). Work from the notes you have."}

        source, problem = narration_validator.resolve_source(url, self._seen_urls)
        if problem == "blocked":
            return {
                "error": (
                    "That page is on a forum, social media or video site, which can't be shown as a source. "
                    "Note the fact from a company filing or release, or an established news organization, "
                    "if one of your results has it."
                )
            }
        if source is None:
            return {
                "error": (
                    f"'{url}' is not among the pages your searches returned. Copy the URL of the page the fact "
                    "is from exactly as the search gave it, character for character - don't shorten it or "
                    "rebuild it from the page's title."
                )
            }
        note = {"note_id": f"note_{len(self.notes) + 1}", "fact": fact.strip(), "url": source}
        self.notes.append(note)
        return note


TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "name": TOOL_NAME,
    "description": (
        "Writes down one fact from a page your web search just returned, with that page's URL, so you "
        "still have it when you write the script. Search results are only visible to you in the turn "
        "you searched in; afterwards your notes are all that is left of them. Call it once per fact you "
        "intend to use, in the same turn as the search. The URL is checked against what the search "
        "returned, and an error tells you to correct it."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": (
                    "The fact as the page states it, with its figures and who said it, e.g. 'Analysts "
                    "polled before the release expected revenue of $12.1 billion and earnings of $1.40 a "
                    "share.' One fact per note, complete enough to use without the page."
                ),
            },
            "url": {"type": "string", "description": "The page's URL, exactly as the search returned it."},
        },
        "required": ["fact", "url"],
        "additionalProperties": False,
    },
}


def execute_tool(notebook: Notebook, arguments_json: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs one `note_finding` call. Returns (parsed arguments, output)."""
    return call_tool({TOOL_NAME: Notebook.add}, notebook, TOOL_NAME, arguments_json)
