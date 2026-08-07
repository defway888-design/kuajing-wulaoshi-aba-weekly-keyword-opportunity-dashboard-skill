#!/usr/bin/env python3
"""Persist ABA weekly pagination state with ordered commits and recovery."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ALLOWED_MARKETPLACES = {
    "US", "UK", "AU", "CA", "JP", "DE", "FR", "IT", "ES", "MX", "BR", "IN", "AE"
}
VALID_MODELS = {2, 4}
STATE_KEYS_V1 = {
    "version", "marketplace", "date", "searchModel", "nextPage", "nextCommitPage",
    "inFlightPages", "pendingPages", "committedPages", "keywordMap", "noNewPages",
    "retryQueue", "stopReason", "terminalReason",
}
STATE_KEYS_V2 = STATE_KEYS_V1 | {"deadlineEpoch"}
STATE_KEYS = STATE_KEYS_V1
TERMINAL_REASONS = {"", "page_retry_exhausted", "execution_interrupted"}


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


def positive_page(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail(f"{field} must be a positive page number")
    return value


def page_list(value: object, field: str) -> list[int]:
    if not isinstance(value, list):
        fail(f"checkpoint {field} must be an array")
    pages = [positive_page(page, field) for page in value]
    if len(set(pages)) != len(pages):
        fail(f"checkpoint {field} contains duplicate pages")
    return pages


def migrate_legacy(state: object) -> object:
    """Migrate v1/v2 checkpoints and remove their obsolete run deadline."""
    if not isinstance(state, dict):
        return state
    if state.get("version") == 1 and set(state) == STATE_KEYS_V1:
        migrated = dict(state)
        migrated["version"] = 3
        return migrated
    if state.get("version") == 2 and set(state) == STATE_KEYS_V2:
        migrated = {key: value for key, value in state.items() if key != "deadlineEpoch"}
        migrated["version"] = 3
        if migrated["terminalReason"] == "execution_timeout":
            migrated["terminalReason"] = ""
        return migrated
    return state


def validate_state(raw_state: object) -> dict:
    state = migrate_legacy(raw_state)
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
        fail("checkpoint has an invalid state schema")
    if state["version"] != 3:
        fail("unsupported checkpoint version")
    if state["marketplace"] not in ALLOWED_MARKETPLACES:
        fail("checkpoint marketplace is invalid")
    if not isinstance(state["date"], str) or len(state["date"]) != 8 or not state["date"].isdigit():
        fail("checkpoint date must use yyyyMMdd")
    if state["searchModel"] not in VALID_MODELS:
        fail("checkpoint searchModel is invalid")
    for key in ("nextPage", "nextCommitPage"):
        positive_page(state[key], key)
    if not isinstance(state["noNewPages"], int) or state["noNewPages"] < 0:
        fail("checkpoint noNewPages is invalid")

    in_flight = page_list(state["inFlightPages"], "inFlightPages")
    if len(in_flight) > 3:
        fail("checkpoint has more than three in-flight pages")
    committed = page_list(state["committedPages"], "committedPages")
    if committed != sorted(committed):
        fail("checkpoint committedPages must be ordered")
    if not isinstance(state["pendingPages"], dict):
        fail("checkpoint pendingPages must be an object")
    pending = []
    for page, records in state["pendingPages"].items():
        try:
            pending_page = positive_page(int(page), "pendingPages key")
        except (TypeError, ValueError):
            fail("checkpoint pendingPages key is invalid")
        if str(pending_page) != page or not isinstance(records, list):
            fail("checkpoint pendingPages is invalid")
        pending.append(pending_page)
    if len(set(pending)) != len(pending):
        fail("checkpoint pendingPages contains duplicate pages")

    if not isinstance(state["keywordMap"], dict):
        fail("checkpoint keywordMap must be an object")
    if not isinstance(state["retryQueue"], list):
        fail("checkpoint retryQueue must be an array")
    retry_pages = []
    for entry in state["retryQueue"]:
        if not isinstance(entry, dict) or set(entry) != {"page", "attempts", "reason"}:
            fail("checkpoint retryQueue entry is invalid")
        page = positive_page(entry["page"], "retryQueue page")
        if isinstance(entry["attempts"], bool) or not isinstance(entry["attempts"], int) or entry["attempts"] < 0:
            fail("checkpoint retryQueue attempts is invalid")
        if not isinstance(entry["reason"], str) or not entry["reason"]:
            fail("checkpoint retryQueue reason is invalid")
        retry_pages.append(page)
    if len(set(retry_pages)) != len(retry_pages):
        fail("checkpoint retryQueue contains duplicate pages")

    if set(committed) & set(in_flight) or set(committed) & set(pending) or set(committed) & set(retry_pages):
        fail("checkpoint page ownership overlaps committed pages")
    if set(pending) & set(in_flight) or set(pending) & set(retry_pages):
        fail("checkpoint page ownership overlaps pending pages")
    if not isinstance(state["stopReason"], str) or not isinstance(state["terminalReason"], str):
        fail("checkpoint terminal fields must be strings")
    if state["terminalReason"] not in TERMINAL_REASONS:
        fail("checkpoint terminalReason is invalid")
    if state["nextPage"] <= max([0, *in_flight, *pending, *committed, *retry_pages]):
        fail("checkpoint nextPage is not ahead of reserved pages")
    return state


def normalize_records(data: object) -> list[dict]:
    if isinstance(data, dict) and set(data) == {"items"}:
        data = data["items"]
    if not isinstance(data, list):
        fail("records must be an array or an object containing only items")
    normalized = []
    for index, row in enumerate(data):
        if not isinstance(row, dict) or set(row) != {"keyword", "searchRank"}:
            fail(f"record {index} must contain only keyword, searchRank")
        keyword = row["keyword"]
        rank = row["searchRank"]
        if not isinstance(keyword, str) or not keyword:
            fail(f"record {index} keyword is invalid")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
            fail(f"record {index} searchRank is invalid")
        normalized.append(row)
    return normalized


def records_from(path: Path) -> list[dict]:
    return normalize_records(load_json(path))


def retry_entry(state: dict, page: int) -> dict | None:
    return next((entry for entry in state["retryQueue"] if entry["page"] == page), None)


def queue_retry(state: dict, page: int, attempts: int, reason: str) -> None:
    state["retryQueue"] = [entry for entry in state["retryQueue"] if entry["page"] != page]
    state["retryQueue"].append({"page": page, "attempts": attempts, "reason": reason})
    state["retryQueue"].sort(key=lambda entry: entry["page"])


def command_init(args: argparse.Namespace) -> dict:
    if args.marketplace not in ALLOWED_MARKETPLACES:
        fail("marketplace is invalid")
    if args.search_model not in VALID_MODELS:
        fail("search model is invalid")
    if len(args.date) != 8 or not args.date.isdigit():
        fail("date must use yyyyMMdd")
    first_page = args.first_page
    positive_page(first_page, "first page")
    state = {
        "version": 3,
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
        write_atomic(args.checkpoint, state)
        state["reservedPages"] = []
        return state
    if state["inFlightPages"] or state["retryQueue"]:
        write_atomic(args.checkpoint, state)
        state["reservedPages"] = []
        return state
    if state["pendingPages"]:
        fail("cannot reserve while pending pages await contiguous commit")
    if args.count < 1 or args.count > 3:
        fail("reserve count must be from 1 to 3")
    pages = list(range(state["nextPage"], state["nextPage"] + args.count))
    state["nextPage"] += args.count
    state["inFlightPages"].extend(pages)
    write_atomic(args.checkpoint, state)
    state["reservedPages"] = pages
    return state


def stage_records(state: dict, page: int, records: object) -> dict:
    """Accept one page result and commit only the contiguous prefix."""
    if state["terminalReason"]:
        return state
    if page not in state["inFlightPages"]:
        fail("page was not reserved or has already been handled")
    state["inFlightPages"].remove(page)
    state["pendingPages"][str(page)] = normalize_records(records)
    state["retryQueue"] = [entry for entry in state["retryQueue"] if entry["page"] != page]

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

    return state


def command_stage(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    state = stage_records(state, args.page, records_from(args.records))
    write_atomic(args.checkpoint, state)
    return state


def command_fail(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if state["terminalReason"]:
        write_atomic(args.checkpoint, state)
        return state
    if args.page not in state["inFlightPages"]:
        fail("page was not reserved or has already been handled")
    state["inFlightPages"].remove(args.page)
    prior = retry_entry(state, args.page)
    attempts = (prior["attempts"] if prior else 0) + 1
    queue_retry(state, args.page, attempts, args.reason)
    if attempts >= 3 and args.reason != "ERROR_MAXIMUM_ACCESS_PER_MINUTE":
        state["terminalReason"] = "page_retry_exhausted"
    write_atomic(args.checkpoint, state)
    return state


def command_retry(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if state["stopReason"] or state["terminalReason"]:
        fail("cannot retry a stopped or terminal checkpoint")
    if state["inFlightPages"]:
        fail("cannot retry until the active batch has settled")
    if not state["retryQueue"]:
        fail("no page is queued for retry")
    current_page = min(entry["page"] for entry in state["retryQueue"])
    if args.page != current_page:
        fail(f"must retry the earliest failed page first: {current_page}")
    state["inFlightPages"].append(args.page)
    write_atomic(args.checkpoint, state)
    return state


def command_check(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    write_atomic(args.checkpoint, state)
    return state


def command_interrupt(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if not state["stopReason"] and not state["terminalReason"]:
        state["terminalReason"] = "execution_interrupted"
    write_atomic(args.checkpoint, state)
    return state


def command_resume(args: argparse.Namespace) -> dict:
    state = validate_state(load_json(args.checkpoint))
    if state["stopReason"]:
        fail("cannot resume a completed checkpoint")
    if state["terminalReason"] not in {"", "execution_interrupted"}:
        fail("cannot resume a checkpoint with a non-recoverable terminal reason")
    for page in sorted(state["inFlightPages"]):
        prior = retry_entry(state, page)
        queue_retry(state, page, prior["attempts"] if prior else 0, "execution_interrupted")
    state["inFlightPages"] = []
    state["terminalReason"] = ""
    write_atomic(args.checkpoint, state)
    return state


def state_summary(state: dict) -> dict:
    return {
        "nextPage": state["nextPage"],
        "nextCommitPage": state["nextCommitPage"],
        "uniqueKeywords": len(state["keywordMap"]),
        "noNewPages": state["noNewPages"],
        "stopReason": state["stopReason"],
        "terminalReason": state["terminalReason"],
        "inFlightPages": state["inFlightPages"],
        "retryPages": [entry["page"] for entry in state["retryQueue"]],
        "pendingPages": sorted(int(page) for page in state["pendingPages"]),
        "reservedPages": state.get("reservedPages", []),
    }


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
    for command_name in ("check", "interrupt"):
        command = sub.add_parser(command_name)
        command.add_argument("--checkpoint", required=True, type=Path)
    resume = sub.add_parser("resume")
    resume.add_argument("--checkpoint", required=True, type=Path)
    args = parser.parse_args()
    try:
        handlers = {
            "init": command_init,
            "reserve": command_reserve,
            "stage": command_stage,
            "fail": command_fail,
            "retry": command_retry,
            "check": command_check,
            "interrupt": command_interrupt,
            "resume": command_resume,
        }
        state = handlers[args.command](args)
        print(json.dumps(state_summary(state), ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"checkpoint_state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
