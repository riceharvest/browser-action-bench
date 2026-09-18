from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DomainScenario:
    name: str
    start_url: str
    prompt: str
    oracle: Callable[[], dict[str, Any]]
    required_values: tuple[str, ...]


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "neeble-benchmark/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def github_browser_automation() -> dict[str, Any]:
    query = urllib.parse.urlencode({"q": "browser automation language:Rust", "sort": "stars", "order": "desc", "per_page": "3"})
    data = _get_json("https://api.github.com/search/repositories?" + query)
    top = data["items"][:3]
    return {"top_ids": [item["full_name"] for item in top], "top_stars": top[0]["stargazers_count"]}


def npm_browser_automation() -> dict[str, Any]:
    data = _get_json("https://registry.npmjs.org/-/v1/search?text=browser%20automation&size=5")
    top = data["objects"][:3]
    return {"top_names": [item["package"]["name"] for item in top], "top_version": top[0]["package"]["version"]}


def arxiv_browser_agents() -> dict[str, Any]:
    query = urllib.parse.quote('all:"browser agent"')
    url = "https://export.arxiv.org/api/query?search_query=" + query + "&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
    data = _get_json(url) if False else None
    # arXiv returns Atom XML, so keep this oracle deliberately separate from
    # JSON helpers and parse only the stable entry IDs/titles.
    import xml.etree.ElementTree as ET
    request = urllib.request.Request(url, headers={"User-Agent": "neeble-benchmark/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        root = ET.fromstring(response.read())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns)
    return {"top_ids": [((entry.findtext("a:id", namespaces=ns) or "").rsplit("/", 1)[-1]) for entry in entries[:3]]}


def stackoverflow_playwright() -> dict[str, Any]:
    params = urllib.parse.urlencode({"site": "stackoverflow", "intitle": "playwright CDP", "order": "desc", "sort": "votes", "pagesize": "5"})
    data = _get_json("https://api.stackexchange.com/2.3/search/advanced?" + params)
    top = data["items"][:3]
    return {"top_question_ids": [str(item["question_id"]) for item in top], "top_score": top[0]["score"]}


def pypi_browser_automation() -> dict[str, Any]:
    names = ["playwright", "selenium", "browser-use"]
    releases = {name: _get_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"] for name in names}
    return {"versions": releases}


DOMAIN_SCENARIOS = (
    DomainScenario(
        "github-rust-browser-automation",
        "https://github.com/search?q=browser+automation+language%3ARust&type=repositories&s=stars&o=desc",
        "Search GitHub for Rust browser-automation repositories. Sort by stars, inspect the top three repository pages, and report their full names and star counts. Open the top repository and verify its language, license, latest release/tag, and README purpose. Use GitHub pages only, not an API or web search.",
        github_browser_automation,
        ("top_ids", "top_stars"),
    ),
    DomainScenario(
        "npm-browser-automation",
        "https://www.npmjs.com/search?q=browser%20automation",
        "Search npm for browser automation packages. Determine the top three packages from the rendered search results, then open the leading package and verify its current version, weekly downloads, repository link, and direct dependencies. Use npm pages only and distinguish package popularity from package name similarity.",
        npm_browser_automation,
        ("top_version",),
    ),
    DomainScenario(
        "arxiv-browser-agents",
        "https://arxiv.org/search/?query=browser+agent&searchtype=all&abstracts=show&order=-announced_date_first&size=50",
        "Search arXiv for papers matching browser agent. Sort by newest submission, open the first three results, and report their arXiv IDs, titles, first authors, and one-sentence contribution summaries. Reject results that merely mention web browsing without being about browser agents. Use arXiv pages only.",
        arxiv_browser_agents,
        ("top_ids",),
    ),
    DomainScenario(
        "stackoverflow-playwright-cdp",
        "https://stackoverflow.com/search?q=playwright+CDP",
        "Search Stack Overflow for Playwright CDP questions. Sort or filter by votes, inspect the top three relevant questions, and report their question IDs, titles, scores, accepted-answer status, and the practical solution in the highest-voted accepted answer. Do not confuse tags or comments with answers. Use Stack Overflow pages only.",
        stackoverflow_playwright,
        ("top_question_ids", "top_score"),
    ),
    DomainScenario(
        "pypi-browser-automation",
        "https://pypi.org/search/?q=browser+automation",
        "Research browser automation packages on PyPI. Compare the rendered project pages for playwright, selenium, and browser-use. Report each current version, Python requirement, release date, and project description, and state which has the newest release date. Use PyPI pages only; do not use pip or package APIs.",
        pypi_browser_automation,
        ("versions",),
    ),
)
