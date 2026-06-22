#!/usr/bin/env python3
"""供GitHub Actions每天运行一次的晨报生成任务。"""

from __future__ import annotations

import json
from pathlib import Path

from server import PROMPT_FILE, call_openai, now_bjt, validate_report, write_json_atomic


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_FILE = DATA_DIR / "knowledge.json"


def main() -> None:
    current = now_bjt()
    report_date = current.date().isoformat()
    prompt = PROMPT_FILE.read_text(encoding="utf-8").replace("{{REPORT_DATE}}", report_date)

    if KNOWLEDGE_FILE.exists():
        prompt += "\n\n# 内部知识台账（JSON）\n" + KNOWLEDGE_FILE.read_text(encoding="utf-8")

    report = call_openai(prompt)
    validate_report(report, report_date)
    report["generated_at"] = current.isoformat()
    report["published_at"] = current.isoformat()

    write_json_atomic(DATA_DIR / "latest.json", report)
    write_json_atomic(DATA_DIR / "history" / f"{report_date}.json", report)

    knowledge = json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8")) if KNOWLEDGE_FILE.exists() else {"reports": [], "recent_paths": []}
    if report_date not in knowledge["reports"]:
        knowledge["reports"].append(report_date)
    knowledge["recent_paths"] = ([report["knowledge_path"]] + knowledge.get("recent_paths", []))[:30]
    write_json_atomic(KNOWLEDGE_FILE, knowledge)
    print(f"已生成并发布 {report_date} 投资晨报")


if __name__ == "__main__":
    main()
