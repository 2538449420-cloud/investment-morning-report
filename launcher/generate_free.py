#!/usr/bin/env python3
"""GitHub Actions 免费AI晨报生成任务。"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.morning_report import (
    build_generation_prompt,
    call_ai,
    choose_case,
    collect_news,
    normalize_sources,
    now_bjt,
    validate_report,
)


DATA_DIR = ROOT / "data"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    current = now_bjt()
    start_date = date.fromisoformat(os.getenv("HISTORY_START_DATE", "2026-06-21"))
    max_reports = max(1, min(int(os.getenv("MAX_REPORTS_PER_RUN", "2")), 3))
    history_file = DATA_DIR / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {"reports": []}
    reports = history.get("reports", [])
    known_dates = {item.get("report_date") for item in reports}

    missing_dates = []
    cursor = start_date
    while cursor <= current.date():
        if cursor.isoformat() not in known_dates:
            missing_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    targets = missing_dates[:max_reports]
    if not targets:
        print("从起始日期至今天没有缺失晨报")
        return

    news = collect_news()
    knowledge_file = DATA_DIR / "knowledge.json"
    knowledge = json.loads(knowledge_file.read_text(encoding="utf-8")) if knowledge_file.exists() else {"reports": [], "recent_paths": []}
    successful = []

    for report_date in targets:
        try:
            company_case = choose_case(report_date)
            report = call_ai(build_generation_prompt(report_date, news, company_case))
            normalize_sources(report, news, company_case)
            validate_report(report, report_date, news, company_case)
            report["generated_at"] = current.isoformat()
            report["published_at"] = now_bjt().isoformat()
            write_json(DATA_DIR / "history" / f"{report_date}.json", report)
            reports = [item for item in reports if item.get("report_date") != report_date]
reports.append({
    "report_date": report_date,
    "theme": report["theme"],
    "summary": report.get("summary", ""),
    "company": report.get("company_case", {}).get("company", ""),

    "lesson": report.get("concept", {}).get("title", ""),

    "terms": [
        item.get("name", "")
        for item in report.get("terms", [])
    ],

    "question": report.get("question", {}).get("prompt", ""),

    "macro_topics": [
        item.get("title", "")
        for item in report.get("macro", [])
    ],

    "market_topics": [
        item.get("title", "")
        for item in report.get("market_flashes", [])
    ],

    "path": f"data/history/{report_date}.json",
})
            if report_date not in knowledge["reports"]:
                knowledge["reports"].append(report_date)
            knowledge["recent_paths"] = ([report["knowledge_path"]] + knowledge.get("recent_paths", []))[:30]
            successful.append(report)
            print(f"已补充 {report_date}")
        except Exception as exc:
            print(f"生成 {report_date} 失败，停止本轮后续调用：{str(exc)[:500]}")
            break

    if not successful:
        raise RuntimeError("本轮没有成功生成任何晨报")

    reports.sort(key=lambda item: item.get("report_date", ""), reverse=True)
    write_json(history_file, {"reports": reports})
    write_json(DATA_DIR / "today.json", successful[-1])
    write_json(knowledge_file, knowledge)
    print(f"本轮成功 {len(successful)} 期，候选新闻 {len(news)} 条")


if __name__ == "__main__":
    main()
