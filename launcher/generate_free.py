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
    choose_case,
    compact_history_entry,
    collect_news,
    expand_history_reports,
    filter_news_for_report_date,
    generate_report_with_retry,
    knowledge_stats_from_history,
    merge_pending_knowledge,
    now_bjt,
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
    reports = expand_history_reports(history.get("reports", []))
    history["reports"] = reports
    known_dates = {item.get("report_date") for item in reports}

    missing_dates = []
    cursor = start_date
    while cursor <= current.date():
        if cursor.isoformat() not in known_dates:
            missing_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    # 严格新闻窗口依赖RSS仍保留对应日期新闻。太久以前的缺口无法可靠补写，
    # 否则会为了补历史而污染“今日快讯”的时效性。
    oldest_reliable = current.date() - timedelta(days=1)
    targets = [
        item
        for item in missing_dates
        if date.fromisoformat(item) >= oldest_reliable
    ]
    # 优先生成今天，避免昨天缺口因为RSS窗口不足而挡住今日晨报。
    targets = sorted(targets, reverse=True)[:max_reports]
    if not targets:
        if missing_dates:
            print("存在较早缺口，但因严格新闻时效窗口已跳过：" + ", ".join(missing_dates[:5]))
        else:
            print("从起始日期至今天没有缺失晨报")
        return

    news = collect_news()
    knowledge_file = DATA_DIR / "knowledge.json"
    knowledge = json.loads(knowledge_file.read_text(encoding="utf-8")) if knowledge_file.exists() else {"reports": [], "recent_paths": []}
    successful = []

    for report_date in targets:
        try:
            try:
                filter_news_for_report_date(news, report_date)
            except RuntimeError as exc:
                if date.fromisoformat(report_date) < current.date():
                    print(f"跳过 {report_date}：严格新闻窗口不足，避免污染历史快讯：{str(exc)[:300]}")
                    continue
                raise
            company_case = choose_case(report_date)
            report = generate_report_with_retry(report_date, news, company_case, history)
            report["generated_at"] = current.isoformat()
            report["published_at"] = now_bjt().isoformat()
            write_json(DATA_DIR / "history" / f"{report_date}.json", report)
            reports = [item for item in reports if item.get("report_date") != report_date]
            reports.append(compact_history_entry(report, f"data/history/{report_date}.json"))
            history["reports"] = reports
            history["pending_knowledge"] = merge_pending_knowledge(history, report)
            knowledge.setdefault("reports", [])
            knowledge.setdefault("recent_paths", [])
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
    write_json(history_file, {
        "reports": reports,
        "knowledge_stats": knowledge_stats_from_history(reports),
        "pending_knowledge": history.get("pending_knowledge", []),
    })
    latest_report = max(successful, key=lambda item: item["report_date"])
    write_json(DATA_DIR / "today.json", latest_report)
    write_json(knowledge_file, knowledge)
    print(f"本轮成功 {len(successful)} 期，候选新闻 {len(news)} 条")


if __name__ == "__main__":
    main()
