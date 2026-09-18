from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    oracle: Callable[[], dict[str, Any]]
    required_values: tuple[str, ...]


def _models(params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen("https://huggingface.co/api/models?" + query, timeout=60) as response:
        return json.load(response)


def qwen_overview() -> dict[str, Any]:
    newest = _models({"author": "Qwen", "limit": "1", "sort": "createdAt", "direction": "-1"})[0]
    popular = _models({"author": "Qwen", "limit": "1", "sort": "downloads", "direction": "-1"})[0]
    all_models = _models({"author": "Qwen", "limit": "1000"})
    return {"latest_id": newest["id"], "popular_id": popular["id"], "total_models": len(all_models)}


def qwen_likes() -> dict[str, Any]:
    liked = _models({"author": "Qwen", "limit": "1", "sort": "likes", "direction": "-1"})[0]
    return {"most_liked_id": liked["id"], "most_liked_count": liked.get("likes", 0)}


def qwen_text_generation() -> dict[str, Any]:
    models = _models({"author": "Qwen", "pipeline_tag": "text-generation", "limit": "5", "sort": "downloads", "direction": "-1"})
    return {"top_ids": [item["id"] for item in models[:3]]}


def qwen_transformers() -> dict[str, Any]:
    models = _models({"author": "Qwen", "library": "transformers", "limit": "5", "sort": "downloads", "direction": "-1"})
    return {"top_ids": [item["id"] for item in models[:3]]}


def qwen_datasets() -> dict[str, Any]:
    with urllib.request.urlopen("https://huggingface.co/api/datasets?author=Qwen&limit=1000", timeout=60) as response:
        datasets = json.load(response)
    return {"dataset_count": len(datasets), "top_dataset_id": datasets[0]["id"] if datasets else ""}


SCENARIOS = (
    Scenario(
        "qwen-overview",
        """On Hugging Face, research the Qwen author listing using rendered browser pages only. Find the newest Qwen model, the most-downloaded Qwen model and its displayed download count, and the total number of Qwen models. Verify each value from the relevant sorted/listing pages and return their URLs.""",
        qwen_overview,
        ("latest_id", "popular_id", "total_models"),
    ),
    Scenario(
        "qwen-most-liked",
        """On Hugging Face, open the Qwen model listing and determine which Qwen model has the most likes. Use the listing's likes sort, open the model card to verify the model ID and displayed likes, and report the exact model URL.""",
        qwen_likes,
        ("most_liked_id", "most_liked_count"),
    ),
    Scenario(
        "qwen-text-generation-top3",
        """On Hugging Face, filter the Qwen author model listing to the text-generation task, sort by downloads, and report the top three model IDs in order with the filtered listing URL. Do not use the API or a web search; verify the ordering in the rendered page.""",
        qwen_text_generation,
        ("top_ids",),
    ),
    Scenario(
        "qwen-transformers-top3",
        """On Hugging Face, use the Qwen author listing's Transformers library filter and download sorting. Report the top three model IDs in order, with the exact filtered URL and the observed download values.""",
        qwen_transformers,
        ("top_ids",),
    ),
    Scenario(
        "qwen-datasets",
        """On Hugging Face, switch from Models to Datasets for the Qwen author. Determine the total dataset count and the first dataset in the default listing. Verify that you are on the Datasets tab rather than the Models tab and return the listing and dataset URLs.""",
        qwen_datasets,
        ("dataset_count", "top_dataset_id"),
    ),
)
