#!/usr/bin/env python3
"""Persist ABA weekly pagination state with ordered commits and atomic checkpoints."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

ALLOWED_MARKETPLACES = {
    "US", "UK", "AU", "CA", "JP", "DE", "FR", "IT", "ES", "MX", "BR", "IN", "AE"
}
VALID_MODELS = {2, 4}
STATE_KEYS = {
    "version", "marketplace", "date", "searchModel", "nextPage", "nextCommitPage",
    "inFlightPages", "pendingPages", "committedPages", "keywordMap", "noNewPages",
    "retryQueue", "stopReason", "terminalReason"
}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def validate_state(state: object) -> dict:
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
        fail("checkpoint has an invalid state schema")
    if state["version"] != 1:
        fail("unsupported checkpoint version")
    if state["marketplace"] not in ALLOWED_MARKETPLACES:
        fail("checkpoint marketplace is invalid")
    if not isinstance(state["date"], str) or len(state["date"]) != 8 or not state["date"].isdigit():
        fail("checkpoint date must use yyyyMMdd")
    if state["searchModel"] not in VALID_MODELS:
        fail("checkpoint searchModel is invalid")
    for key in ("nextPage", "nextCommitPage", "noNewPages"):
        if not isinstance(state[key], int) or state[key] < 0:
            fail(f"checkpoint {key} is invalid")
    for key in ("inFlightPages", "committedPages", "retryQueue"):
        if not isinstance(state[key], list):
            fail(f"checkpoint {key} must be an array")
    for key in ("pendingPages", "keywordMap"):
        if not isinstance(state[key], dict):
            fail(f"checkpoint {key} must be an object")
    for key in ("stopReason", "terminalReason"):
        if not isinstance(state[key], str):
            fail(f"checkpoint {key} must be a string")
    return state


def records_from(path: Path) -> list[dict]:
    data = load_json(path)
    if isinstance(data, dict) and set(data) == {"items"}:
        data = data["items"]
    if not isinstance(data, list):
        fail("records must be an array or an object containing only items")
    normalized = []
    for index, row in enumerate(data):
        if not isinstance(row, dict) or set(row) != {"keyword", "searchRank", "searches"}:
            fail(f"record {index} must contain only keyword, searchRank, searches")
        keyword = row["keyword"]
        rank = row["searchRank"]
        searches = row["searches"]
        if not isinstance(keyword, str) or not keyword:
            fail(f"record {index} keyword is invalid")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
            fail(f"record {index} searchRank is invalid")
        if searches is not None and (
            isinstance(searches, bool)
            or not isinstance(searches, (int, float))
            or not math.isfinite(float(searches))
        ):
            fail(f"record {index} searches is invalid")
        normalized.append(row)
    return normalized


def command_init(args: argparse.Namespace) -> dict:
    if args.marketplace not in ALLOWED_MARKETPLACES:
        fail("marketplace is invalid")
    if args.search_model not in VALID_MODELS:
        fail("search model is invalid")
    if len(args.date) != 8 or not args.date.isdigit():
        fail("date must use yyyyMMdd")
    first_page = args.first_page
    if first_page < 1:
        fail("first page must be positive")
    state = {
        "version": 1,
        "marketplace": args.marketplace,
        "date": args.date,
        "searchModel": args.search_model,
        "nextPage": first_page,
        "nextCommitPage": first_page,
        "inFlightPages": [],
        "pendingPages": {},
        "committedPages": [],
        "keywordMap": {},
        "noNewPages": 0,
        "retryQueue": [],
        "stopReason": "",
        "terminalReason": "",
    }
    write_atomic(args.checkpoint, state)
    return state


def command_reserve(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if state["stopReason"] or state["terminalReason"]:
        return state
    count = args.count
    if count < 1 or count > 3:
        fail("reserve count must be from 1 to 3")
    active = len(state["inFlightPages"])
    count = min(count, 3 - active)
    pages = list(range(state["nextPage"], state["nextPage"] + count))
    state["nextPage"] += count
    state["inFlightPages"].extend(pages)
    write_atomic(args.checkpoint, state)
    state["reservedPages"] = pages
    return state


def command_stage(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if args.page not in state["inFlightPages"]:
        fail("page was not reserved or has already been handled")
    state["inFlightPages"].remove(args.page)
    state["pendingPages"][str(args.page)] = records_from(args.records)
    state["retryQueue"] = [entry for entry in state["retryQueue"] if entry["page"] != args.page]

    while str(state["nextCommitPage"]) in state["pendingPages"] and not state["stopReason"]:
        page = state["nextCommitPage"]
        rows = state["pendingPages"].pop(str(page))
        added = 0
        for row in rows:
            if row["keyword"] not in state["keywordMap"] and len(state["keywordMap"]) < 2000:
                state["keywordMap"][row["keyword"]] = row
                added += 1
        state["committedPages"].append(page)
        state["nextCommitPage"] += 1
        state["noNewPages"] = 0 if added else state["noNewPages"] + 1
        if len(state["keywordMap"]) >= 2000:
            state["stopReason"] = "unique_keyword_limit"
        elif state["noNewPages"] >= 5:
            state["stopReason"] = "five_pages_without_new_keywords"

    write_atomic(args.checkpoint, state)
    return state


def command_fail(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if args.page not in state["inFlightPages"]:
        fail("page was not reserved or has already been handled")
    state["inFlightPages"].remove(args.page)
    prior = next((entry for entry in state["retryQueue"] if entry["page"] == args.page), None)
    attempts = (prior["attempts"] if prior else 0) + 1
    state["retryQueue"] = [entry for entry in state["retryQueue"] if entry["page"] != args.page]
    state["retryQueue"].append({"page": args.page, "attempts": attempts, "reason": args.reason})
    if attempts >= 3 and args.reason != "ERROR_MAXIMUM_ACCESS_PER_MINUTE":
        state["terminalReason"] = "page_retry_exhausted"
    write_atomic(args.checkpoint, state)
    return state


def command_retry(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if state["stopReason"] or state["terminalReason"]:
        fail("cannot retry a stopped or terminal checkpoint")
    if args.page in state["inFlightPages"]:
        fail("page is already in flight")
    if not any(entry["page"] == args.page for entry in state["retryQueue"]):
        fail("page is not queued for retry")
    if len(state["inFlightPages"]) >= 3:
        fail("maximum in-flight page count reached")
    state["inFlightPages"].append(args.page)
    write_atomic(args.checkpoint, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--checkpoint", required=True, type=Path)
    init.add_argument("--marketplace", required=True)
    init.add_argument("--date", required=True)
    init.add_argument("--search-model", required=True, type=int)
    init.add_argument("--first-page", default=1, type=int)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--checkpoint", required=True, type=Path)
    reserve.add_argument("--count", required=True, type=int)
    stage = sub.add_parser("stage")
    stage.add_argument("--checkpoint", required=True, type=Path)
    stage.add_argument("--page", required=True, type=int)
    stage.add_argument("--records", required=True, type=Path)
    failed = sub.add_parser("fail")
    failed.add_argument("--checkpoint", required=True, type=Path)
    failed.add_argument("--page", required=True, type=int)
    failed.add_argument("--reason", required=True)
    retry = sub.add_parser("retry")
    retry.add_argument("--checkpoint", required=True, type=Path)
    retry.add_argument("--page", required=True, type=int)
    args = parser.parse_args()
    try:
        handlers = {
            "init": command_init, "reserve": command_reserve, "stage": command_stage, "fail": command_fail,
            "retry": command_retry
        }
        state = handlers[args.command](args)
        print(json.dumps({
            "nextPage": state["nextPage"],
            "nextCommitPage": state["nextCommitPage"],
            "uniqueKeywords": len(state["keywordMap"]),
            "noNewPages": state["noNewPages"],
            "stopReason": state["stopReason"],
            "terminalReason": state["terminalReason"],
            "reservedPages": state.get("reservedPages", []),
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"checkpoint_state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
