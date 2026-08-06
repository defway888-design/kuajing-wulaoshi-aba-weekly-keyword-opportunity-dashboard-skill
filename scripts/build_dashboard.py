#!/usr/bin/env python3
"""Inject normalized data into the immutable offline ABA dashboard template."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

ALLOWED_MARKETPLACES = {
    "US", "UK", "AU", "CA", "JP", "DE", "FR", "IT", "ES", "MX", "BR", "IN", "AE"
}
TOP_LEVEL_KEYS = {"status", "blockReason", "marketplace", "latestWeek", "previousWeek", "items"}
ITEM_KEYS = {
    "keyword", "zh", "currentAbaRank", "previousWeekAnomalyRank", "growthMultiple", "type"
}
TYPES = {"商品/工具", "图书/内容", "节日/季节", "品牌/专名"}
BLOCK_REASONS = {
    "no_valid_week_pair", "page_retry_exhausted", "execution_timeout", "batch_enrichment_failed"
}
DATE_PATTERN = re.compile(r"^\d{4}年\d{2}月\d{2}日$")
PLACEHOLDER = "__ABA_OPPORTUNITY_DATA_JSON__"
TEMPLATE_SHA256 = "94a2572946e5c312560c3d5b0dd268cd6441e96d2e96a2811b61e0e0b0832411"
FORBIDDEN_STATIC_PATTERNS = (
    re.compile(r"\bfetch\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:XMLHttpRequest|WebSocket|EventSource)\b", re.IGNORECASE),
    re.compile(r"<\s*(?:script|link|img|iframe|audio|video)\b[^>]*(?:src|href)\s*=", re.IGNORECASE),
    re.compile(r"@import\b", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(?:localhost|127\.0\.0\.1)\b", re.IGNORECASE),
    re.compile(r"monthlyTrendRecent24", re.IGNORECASE),
)
REQUIRED_TEMPLATE_MARKERS = (
    "<h1>ABA 周交集机会 BI 看板</h1>",
    "<div class=\"label\">快速飙升市场</div>",
    "<div class=\"label\">异动市场</div>",
    "<option value=\"current\">现 ABA 排名升序</option>",
    "<option value=\"growth\">周搜索增长倍数降序</option>",
    "<option value=\"previous\">前周异动排名升序</option>",
    "<option>商品/工具</option>",
    "<option>图书/内容</option>",
    "<option>节日/季节</option>",
    "<option>品牌/专名</option>",
    "<th>英文关键词</th><th>中文翻译</th><th class=\"num\">现 ABA 排名</th><th class=\"num\">前周异动排名</th><th class=\"num\">搜索增长倍数</th><th>机会类型</th>",
    "const EMBEDDED_DATA=__ABA_OPPORTUNITY_DATA_JSON__",
)


def fail(message: str) -> None:
    raise ValueError(message)


def positive_integer(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        fail(f"{field} must be a positive integer")


def positive_number(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{field} must be a number")
    if not math.isfinite(float(value)) or float(value) <= 0:
        fail(f"{field} must be a finite positive number")


def parse_chinese_date(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        fail(f"{field} must use yyyy年MM月dd日")
    try:
        return datetime.strptime(value, "%Y年%m月%d日")
    except ValueError as exc:
        fail(f"{field} is not a real date: {exc}")


def validate(data: object) -> dict:
    if not isinstance(data, dict):
        fail("input JSON must be an object")
    if set(data) != TOP_LEVEL_KEYS:
        fail(f"top-level keys must be exactly: {', '.join(sorted(TOP_LEVEL_KEYS))}")
    status = data["status"]
    if status not in {"ready", "blocked"}:
        fail("status must be ready or blocked")
    if data["marketplace"] not in ALLOWED_MARKETPLACES:
        fail("marketplace is invalid")
    if not isinstance(data["blockReason"], str):
        fail("blockReason must be a string")
    if not isinstance(data["latestWeek"], str) or not isinstance(data["previousWeek"], str):
        fail("week values must be strings")
    if not isinstance(data["items"], list):
        fail("items must be an array")
    if len(data["items"]) > 2000:
        fail("items cannot exceed 2000")

    if status == "ready":
        latest = parse_chinese_date(data["latestWeek"], "latestWeek")
        previous = parse_chinese_date(data["previousWeek"], "previousWeek")
        if (latest - previous).days != 7:
            fail("ready weeks must be exactly seven days apart")
        if data["blockReason"]:
            fail("ready data must have an empty blockReason")
    else:
        if data["blockReason"] not in BLOCK_REASONS:
            fail("blocked data must use a deterministic blockReason")
        if data["latestWeek"] or data["previousWeek"] or data["items"]:
            fail("blocked data must have empty weeks and no items")

    seen = set()
    for index, item in enumerate(data["items"]):
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            fail(f"item {index} must contain only the six dashboard fields")
        for field in ("keyword", "zh"):
            if not isinstance(item[field], str) or not item[field].strip():
                fail(f"item {index} {field} must be a non-empty string")
        if item["keyword"] in seen:
            fail(f"item {index} duplicates keyword {item['keyword']}")
        seen.add(item["keyword"])
        positive_integer(item["currentAbaRank"], f"item {index} currentAbaRank")
        positive_integer(item["previousWeekAnomalyRank"], f"item {index} previousWeekAnomalyRank")
        positive_number(item["growthMultiple"], f"item {index} growthMultiple")
        if item["type"] not in TYPES:
            fail(f"item {index} type is invalid")
    return data


def validate_template(template: str, raw_template: bytes) -> None:
    digest = hashlib.sha256(raw_template).hexdigest()
    if digest != TEMPLATE_SHA256:
        fail("template hash differs from the approved fixed template")
    if template.count(PLACEHOLDER) != 1:
        fail("template must contain exactly one data placeholder")
    if any(pattern.search(template) for pattern in FORBIDDEN_STATIC_PATTERNS):
        fail("template contains an external runtime dependency or forbidden monthly field")
    missing = [marker for marker in REQUIRED_TEMPLATE_MARKERS if marker not in template]
    if missing:
        fail("template is missing required fixed UI markers")


def expected_filename(data: dict) -> str:
    if data["status"] == "blocked":
        return f"aba_weekly_keyword_opportunity_{data['marketplace']}_unavailable.html"
    date = data["latestWeek"].replace("年", "").replace("月", "").replace("日", "")
    return f"aba_weekly_keyword_opportunity_{data['marketplace']}_{date}.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="normalized embedded JSON")
    parser.add_argument("--output", required=True, type=Path, help="single HTML delivery file")
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "aba_weekly_keyword_opportunity_template.html",
        help="immutable skill template",
    )
    args = parser.parse_args()
    try:
        data = validate(json.loads(args.data.read_text(encoding="utf-8")))
        if args.output.name != expected_filename(data):
            fail(f"output filename must be {expected_filename(data)}")
        raw_template = args.template.read_bytes()
        template = raw_template.decode("utf-8")
        validate_template(template, raw_template)
        embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        html = template.replace(PLACEHOLDER, embedded)
        if PLACEHOLDER in html or html.count("const EMBEDDED_DATA=") != 1:
            fail("embedded data replacement failed")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html, encoding="utf-8", newline="\n")
        print(json.dumps({
            "output": str(args.output),
            "status": data["status"],
            "marketplace": data["marketplace"],
            "items": len(data["items"]),
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"build_dashboard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
