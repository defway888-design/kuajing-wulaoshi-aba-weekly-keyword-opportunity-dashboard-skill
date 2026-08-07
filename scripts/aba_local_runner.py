#!/usr/bin/env python3
"""Run the complete verified ABA weekly workflow through an explicit local adapter."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_dashboard
import checkpoint_state

ALLOWED_MARKETPLACES = checkpoint_state.ALLOWED_MARKETPLACES
REQUEST_FIELDS = "keyword,searchRank"
MAX_BATCH_SIZE = 3
MIN_SECONDS_PER_REQUEST = 2
MAX_WEEK_CANDIDATES = 12


class AdapterFailure(RuntimeError):
    """A normalized, non-sensitive local adapter failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def fail(message: str) -> None:
    raise ValueError(message)


def parse_adapter_command(value: str) -> list[str]:
    try:
        command = json.loads(value)
    except json.JSONDecodeError as exc:
        fail(f"adapter command must be a JSON string array: {exc}")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        fail("adapter command must be a non-empty JSON string array")
    return command


def load_adapter_command(command: str | None, command_file: Path | None) -> list[str]:
    if command_file is not None:
        return parse_adapter_command(command_file.read_text(encoding="utf-8"))
    if command is None:
        fail("adapter command is required")
    return parse_adapter_command(command)


def parse_as_of(value: str | None) -> date:
    if value is None:
        return date.today()
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        fail(f"as-of must use yyyyMMdd: {exc}")


def nearest_saturday(as_of: date) -> date:
    return as_of - timedelta(days=(as_of.weekday() - 5) % 7)


def format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def chinese_date(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").strftime("%Y年%m月%d日")


def sleep_for(seconds: float) -> None:
    """Apply the rate-limit wait without imposing a whole-run deadline."""
    if seconds > 0:
        time.sleep(seconds)


def error_reason(value: object) -> str:
    if isinstance(value, str) and "ERROR_MAXIMUM_ACCESS_PER_MINUTE" in value:
        return "ERROR_MAXIMUM_ACCESS_PER_MINUTE"
    return "page_error"


def command_json(
    command: list[str],
    payload: dict[str, Any],
    timeout_seconds: float,
    failure_reason: str,
) -> object:
    """Call one explicit local bridge and return only its parsed JSON output."""
    if timeout_seconds <= 0:
        raise AdapterFailure(failure_reason)
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdapterFailure(failure_reason) from exc
    if completed.returncode != 0:
        raise AdapterFailure(failure_reason)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AdapterFailure(failure_reason) from exc


def adapter_call(
    command: list[str],
    request: dict[str, Any],
    timeout_seconds: float,
) -> list[dict]:
    """Call an injected bridge; it alone maps local MCP transport to this contract."""
    response = command_json(
        command,
        {"operation": "aba_research_weekly", "request": request},
        timeout_seconds,
        "runner_adapter_failed",
    )
    if not isinstance(response, dict) or set(response) != {"code", "items"}:
        raise AdapterFailure("runner_adapter_failed")
    if response["code"] != "OK":
        raise AdapterFailure(error_reason(response["code"]))
    try:
        return checkpoint_state.normalize_records(response["items"])
    except ValueError as exc:
        raise AdapterFailure("runner_adapter_failed") from exc


def translate_keywords(command: list[str], keywords: list[str], timeout_seconds: float) -> dict[str, str]:
    """Translate the final exact intersection through an explicit local bridge."""
    if not keywords:
        return {}
    response = command_json(
        command,
        {
            "operation": "translate_keywords",
            "sourceLanguage": "en",
            "targetLanguage": "zh-CN",
            "keywords": keywords,
        },
        timeout_seconds,
        "translation_adapter_failed",
    )
    if not isinstance(response, dict) or set(response) != {"items"} or not isinstance(response["items"], list):
        raise AdapterFailure("translation_adapter_failed")
    expected = set(keywords)
    translations: dict[str, str] = {}
    for row in response["items"]:
        if not isinstance(row, dict) or set(row) != {"keyword", "keywordZh"}:
            raise AdapterFailure("translation_adapter_failed")
        keyword, keyword_zh = row["keyword"], row["keywordZh"]
        if (
            not isinstance(keyword, str)
            or keyword not in expected
            or keyword in translations
            or not isinstance(keyword_zh, str)
            or not keyword_zh.strip()
            or not build_dashboard.HAN_PATTERN.search(keyword_zh)
        ):
            raise AdapterFailure("translation_adapter_failed")
        translations[keyword] = keyword_zh.strip()
    if set(translations) != expected:
        raise AdapterFailure("translation_adapter_failed")
    return translations


def request_payload(marketplace: str, week: str, model: int, page: int, size: int) -> dict[str, Any]:
    return {
        "marketplace": marketplace,
        "date": week,
        "searchModel": model,
        "page": page,
        "size": size,
        "returnFields": REQUEST_FIELDS,
    }


def probe_week_pair(
    command: list[str],
    marketplace: str,
    as_of: date,
    request_timeout: float,
    metrics: dict[str, int],
) -> tuple[str, str] | None:
    candidate = nearest_saturday(as_of)
    for _ in range(MAX_WEEK_CANDIDATES):
        latest = format_date(candidate)
        previous = format_date(candidate - timedelta(days=7))
        try:
            metrics["probeRequests"] += 1
            newest_records = adapter_call(
                command,
                request_payload(marketplace, latest, 4, 1, 1),
                request_timeout,
            )
            sleep_for(MIN_SECONDS_PER_REQUEST)
            metrics["probeRequests"] += 1
            prior_records = adapter_call(
                command,
                request_payload(marketplace, previous, 2, 1, 1),
                request_timeout,
            )
        except AdapterFailure as exc:
            if exc.reason == "runner_adapter_failed":
                raise
            newest_records, prior_records = [], []
        if newest_records and prior_records:
            return latest, previous
        candidate -= timedelta(days=7)
        sleep_for(MIN_SECONDS_PER_REQUEST)
    return None


def command_check(checkpoint: Path) -> dict:
    return checkpoint_state.command_check(argparse.Namespace(checkpoint=checkpoint))


def command_init(checkpoint: Path, marketplace: str, week: str, model: int) -> dict:
    return checkpoint_state.command_init(argparse.Namespace(
        checkpoint=checkpoint,
        marketplace=marketplace,
        date=week,
        search_model=model,
        first_page=1,
    ))


def command_reserve(checkpoint: Path, count: int) -> dict:
    return checkpoint_state.command_reserve(argparse.Namespace(checkpoint=checkpoint, count=count))


def command_retry(checkpoint: Path, page: int) -> dict:
    return checkpoint_state.command_retry(argparse.Namespace(checkpoint=checkpoint, page=page))


def stage(checkpoint: Path, page: int, records: list[dict]) -> dict:
    state = checkpoint_state.validate_state(checkpoint_state.load_json(checkpoint))
    state = checkpoint_state.stage_records(state, page, records)
    checkpoint_state.write_atomic(checkpoint, state)
    return state


def mark_failed(checkpoint: Path, page: int, reason: str) -> dict:
    return checkpoint_state.command_fail(argparse.Namespace(
        checkpoint=checkpoint,
        page=page,
        reason=reason,
    ))


def retry_delay(state: dict, page: int) -> int:
    entry = next(entry for entry in state["retryQueue"] if entry["page"] == page)
    if entry["attempts"] == 0:
        return 0
    if entry["reason"] == "ERROR_MAXIMUM_ACCESS_PER_MINUTE":
        return 70
    return (5, 15, 30)[min(entry["attempts"], 3) - 1]


def invoke_page(
    command: list[str],
    marketplace: str,
    week: str,
    model: int,
    page: int,
    request_timeout: float,
) -> tuple[int, list[dict] | None, str | None]:
    try:
        records = adapter_call(
            command,
            request_payload(marketplace, week, model, page, 40),
            request_timeout,
        )
        return page, records, None
    except AdapterFailure as exc:
        return page, None, exc.reason


def settle_batch(
    command: list[str],
    checkpoint: Path,
    marketplace: str,
    week: str,
    model: int,
    pages: list[int],
    request_timeout: float,
    metrics: dict[str, int],
) -> dict:
    began = time.monotonic()
    results: dict[int, tuple[list[dict] | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=len(pages)) as executor:
        futures = {
            executor.submit(invoke_page, command, marketplace, week, model, page, request_timeout): page
            for page in pages
        }
        for future in as_completed(futures):
            page, records, reason = future.result()
            results[page] = (records, reason)
    metrics["pageRequests"] += len(pages)
    for page in sorted(pages):
        records, reason = results[page]
        if reason is None:
            state = stage(checkpoint, page, records or [])
        elif reason == "runner_adapter_failed":
            state = mark_failed(checkpoint, page, "page_error")
            metrics["failedAttempts"] += 1
        else:
            state = mark_failed(checkpoint, page, reason)
            metrics["failedAttempts"] += 1
    sleep_for((MIN_SECONDS_PER_REQUEST * len(pages)) - (time.monotonic() - began))
    return command_check(checkpoint)


def resolve_retries(
    command: list[str],
    checkpoint: Path,
    marketplace: str,
    week: str,
    model: int,
    request_timeout: float,
    metrics: dict[str, int],
) -> dict:
    state = command_check(checkpoint)
    while state["retryQueue"] and not state["terminalReason"] and not state["stopReason"]:
        page = min(entry["page"] for entry in state["retryQueue"])
        sleep_for(retry_delay(state, page))
        command_retry(checkpoint, page)
        metrics["retryRequests"] += 1
        metrics["pageRequests"] += 1
        page, records, reason = invoke_page(
            command, marketplace, week, model, page, request_timeout
        )
        if reason is None:
            state = stage(checkpoint, page, records or [])
        else:
            state = mark_failed(checkpoint, page, "page_error" if reason == "runner_adapter_failed" else reason)
            metrics["failedAttempts"] += 1
        state = command_check(checkpoint)
    return state


def run_market(
    command: list[str],
    checkpoint: Path,
    marketplace: str,
    week: str,
    model: int,
    request_timeout: float,
    metrics: dict[str, int],
    resume: bool = False,
) -> dict:
    if checkpoint.exists():
        if not resume:
            fail(f"checkpoint already exists: {checkpoint}")
        state = checkpoint_state.validate_state(checkpoint_state.load_json(checkpoint))
        if state["marketplace"] != marketplace or state["date"] != week or state["searchModel"] != model:
            fail("resume checkpoint does not match the locked week and market")
        if not state["stopReason"]:
            state = checkpoint_state.command_resume(argparse.Namespace(
                checkpoint=checkpoint,
            ))
    else:
        state = command_init(checkpoint, marketplace, week, model)
    while not state["stopReason"] and not state["terminalReason"]:
        state = command_check(checkpoint)
        if state["stopReason"] or state["terminalReason"]:
            break
        if state["retryQueue"]:
            state = resolve_retries(
                command, checkpoint, marketplace, week, model, request_timeout, metrics
            )
            continue
        state = command_reserve(checkpoint, MAX_BATCH_SIZE)
        pages = state.get("reservedPages", [])
        if not pages:
            break
        state = settle_batch(
            command, checkpoint, marketplace, week, model, pages, request_timeout, metrics
        )
        state = resolve_retries(
            command, checkpoint, marketplace, week, model, request_timeout, metrics
        )
    return command_check(checkpoint)


def shared_keywords(latest: dict, previous: dict) -> list[str]:
    return [keyword for keyword in latest["keywordMap"] if keyword in previous["keywordMap"]]


def dashboard_data(
    marketplace: str,
    latest_week: str,
    previous_week: str,
    latest: dict,
    previous: dict,
    translations: dict[str, str],
) -> dict:
    latest_rows = latest["keywordMap"]
    previous_rows = previous["keywordMap"]
    items = [
        {
            "keyword": keyword,
            "keywordZh": translations[keyword],
            "currentAbaRank": row["searchRank"],
            "previousWeekAnomalyRank": previous_rows[keyword]["searchRank"],
        }
        for keyword, row in latest_rows.items()
        if keyword in previous_rows
    ]
    items.sort(key=lambda item: (item["currentAbaRank"], item["keyword"]))
    return {
        "status": "ready",
        "blockReason": "",
        "marketplace": marketplace,
        "latestWeek": chinese_date(latest_week),
        "previousWeek": chinese_date(previous_week),
        "items": items,
    }


def blocked_data(marketplace: str, reason: str) -> dict:
    return {
        "status": "blocked",
        "blockReason": reason,
        "marketplace": marketplace,
        "latestWeek": "",
        "previousWeek": "",
        "items": [],
    }


def build_blocked(marketplace: str, output_dir: Path, template: Path, reason: str) -> dict:
    data = blocked_data(marketplace, reason)
    return build_dashboard.build(data, output_dir / build_dashboard.expected_filename(data), template)


def interrupt(checkpoints: list[Path]) -> None:
    for checkpoint in checkpoints:
        if checkpoint.exists():
            checkpoint_state.command_interrupt(argparse.Namespace(checkpoint=checkpoint))


def resume_weeks(work_dir: Path, marketplace: str) -> tuple[str, str, Path, Path]:
    candidates = sorted(work_dir.glob(f"aba_{marketplace}_*_m4.json"))
    if len(candidates) != 1:
        fail("resume requires exactly one latest-market checkpoint in work-dir")
    latest_checkpoint = candidates[0]
    latest = checkpoint_state.validate_state(checkpoint_state.load_json(latest_checkpoint))
    if latest["marketplace"] != marketplace or latest["searchModel"] != 4:
        fail("latest resume checkpoint is invalid")
    latest_date = datetime.strptime(latest["date"], "%Y%m%d").date()
    previous_week = format_date(latest_date - timedelta(days=7))
    previous_checkpoint = work_dir / f"aba_{marketplace}_{previous_week}_m2.json"
    if previous_checkpoint.exists():
        previous = checkpoint_state.validate_state(checkpoint_state.load_json(previous_checkpoint))
        if previous["marketplace"] != marketplace or previous["searchModel"] != 2 or previous["date"] != previous_week:
            fail("previous resume checkpoint is invalid")
    return latest["date"], previous_week, latest_checkpoint, previous_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marketplace", required=True)
    adapter = parser.add_mutually_exclusive_group(required=True)
    adapter.add_argument("--adapter-command", help="JSON array for an explicit local ABA adapter")
    adapter.add_argument("--adapter-command-file", type=Path, help="UTF-8 JSON command-array file for an explicit local ABA adapter")
    translator = parser.add_mutually_exclusive_group()
    translator.add_argument("--translation-command", help="JSON array for an explicit local English-to-Chinese translator")
    translator.add_argument("--translation-command-file", type=Path, help="UTF-8 JSON command-array file for an explicit local English-to-Chinese translator")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--resume", action="store_true", help="continue only checkpoints explicitly retained from an interrupted run")
    parser.add_argument("--as-of", help="optional yyyyMMdd execution date")
    parser.add_argument("--request-timeout", type=float, default=45.0)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "aba_weekly_keyword_opportunity_template.html",
    )
    args = parser.parse_args()
    if args.marketplace not in ALLOWED_MARKETPLACES:
        print("aba_local_runner: marketplace is invalid", file=sys.stderr)
        return 2
    if args.request_timeout <= 0:
        print("aba_local_runner: request timeout must be positive", file=sys.stderr)
        return 2

    checkpoints: list[Path] = []
    started = time.time()
    metrics = {"probeRequests": 0, "pageRequests": 0, "retryRequests": 0, "failedAttempts": 0}
    try:
        command = load_adapter_command(args.adapter_command, args.adapter_command_file)
        translation_command = (
            load_adapter_command(args.translation_command, args.translation_command_file)
            if args.translation_command is not None or args.translation_command_file is not None
            else None
        )
        if args.resume:
            latest_week, previous_week, latest_checkpoint, previous_checkpoint = resume_weeks(args.work_dir, args.marketplace)
        else:
            pair = probe_week_pair(command, args.marketplace, parse_as_of(args.as_of), args.request_timeout, metrics)
            if pair is None:
                result = build_blocked(args.marketplace, args.output_dir, args.template, "no_valid_week_pair")
                result.update(metrics)
                result["elapsedSeconds"] = round(time.time() - started, 2)
                print(json.dumps(result, ensure_ascii=False))
                return 0
            latest_week, previous_week = pair
            latest_checkpoint = args.work_dir / f"aba_{args.marketplace}_{latest_week}_m4.json"
            previous_checkpoint = args.work_dir / f"aba_{args.marketplace}_{previous_week}_m2.json"
        checkpoints = [latest_checkpoint, previous_checkpoint]
        latest = run_market(command, latest_checkpoint, args.marketplace, latest_week, 4, args.request_timeout, metrics, args.resume)
        if latest["terminalReason"]:
            result = build_blocked(args.marketplace, args.output_dir, args.template, latest["terminalReason"])
        else:
            previous = run_market(command, previous_checkpoint, args.marketplace, previous_week, 2, args.request_timeout, metrics, args.resume)
            if previous["terminalReason"]:
                result = build_blocked(args.marketplace, args.output_dir, args.template, previous["terminalReason"])
            elif latest["stopReason"] and previous["stopReason"]:
                keywords = shared_keywords(latest, previous)
                if keywords and translation_command is None:
                    result = build_blocked(args.marketplace, args.output_dir, args.template, "translation_adapter_unavailable")
                else:
                    translations = translate_keywords(translation_command, keywords, args.request_timeout) if keywords else {}
                    data = dashboard_data(args.marketplace, latest_week, previous_week, latest, previous, translations)
                    output = args.output_dir / build_dashboard.expected_filename(data)
                    result = build_dashboard.build(data, output, args.template)
                    result.update({
                        "latestUniqueKeywords": len(latest["keywordMap"]),
                        "previousUniqueKeywords": len(previous["keywordMap"]),
                        "intersectionKeywords": len(data["items"]),
                    })
                    for checkpoint in checkpoints:
                        checkpoint.unlink(missing_ok=True)
            else:
                fail("market runner ended without a completion or terminal state")
        result.update(metrics)
        result["elapsedSeconds"] = round(time.time() - started, 2)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        interrupt(checkpoints)
        print(json.dumps({"status": "interrupted", **metrics}, ensure_ascii=False))
        return 130
    except AdapterFailure as exc:
        reason = exc.reason if exc.reason in {"runner_adapter_failed", "translation_adapter_failed"} else "runner_adapter_failed"
        try:
            result = build_blocked(args.marketplace, args.output_dir, args.template, reason)
            result.update(metrics)
            result["elapsedSeconds"] = round(time.time() - started, 2)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as nested:
            print(f"aba_local_runner: {nested}", file=sys.stderr)
            return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"aba_local_runner: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
