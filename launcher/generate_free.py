#!/usr/bin/env python3
"""GitHub Actions 免费AI晨报生成任务。"""

from __future__ import annotations

import json
import sys
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
    report_date = current.date().isoformat()
    news = collect_news()
    company_case = choose_case(report_date)
    report = call_ai(build_generation_prompt(report_date, news, company_case))
    normalize_sources(report, news, company_case)
    validate_report(report, report_date, news, company_case)
    report["generated_at"] = current.isoformat()
    report["published_at"] = now_bjt().isoformat()

    archive_path = DATA_DIR / "history" / f"{report_date}.json"
    write_json(archive_path, report)

    history_file = DATA_DIR / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {"reports": []}
    reports = [item for item in history.get("reports", []) if item.get("report_date") != report_date]
    reports.insert(0, {
        "report_date": report_date,
        "theme": report["theme"],
        "summary": report.get("summary", ""),
        "company": report.get("company_case", {}).get("company", ""),
        "path": f"data/history/{report_date}.json",
    })
    write_json(history_file, {"reports": reports})
    write_json(DATA_DIR / "today.json", report)

    knowledge_file = DATA_DIR / "knowledge.json"
    knowledge = json.loads(knowledge_file.read_text(encoding="utf-8")) if knowledge_file.exists() else {"reports": [], "recent_paths": []}
    if report_date not in knowledge["reports"]:
        knowledge["reports"].append(report_date)
    knowledge["recent_paths"] = ([report["knowledge_path"]] + knowledge.get("recent_paths", []))[:30]
    write_json(knowledge_file, knowledge)
    print(f"已生成 {report_date} 晨报，候选新闻 {len(news)} 条")


if __name__ == "__main__":
    main()
