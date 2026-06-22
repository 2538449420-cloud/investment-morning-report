#!/usr/bin/env python3
"""投资晨报个人版发射器。

本地默认只监听 127.0.0.1。配置 OPENAI_API_KEY 后：
- 每天 07:40（Asia/Shanghai）生成草稿；
- 每天 08:00 发布为 latest.json；
- 同时提供静态阅读页面与只读 API。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock_time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
DRAFT_FILE = DATA_DIR / "draft.json"
LATEST_FILE = DATA_DIR / "latest.json"
STATUS_FILE = DATA_DIR / "status.json"
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "report_prompt.md"
KNOWLEDGE_FILE = APP_ROOT / "data" / "knowledge.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")
GENERATE_AT = clock_time(7, 40)
PUBLISH_AT = clock_time(8, 0)


def now_bjt() -> datetime:
    return datetime.now(TIMEZONE)


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        return fallback or {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_status(**values: Any) -> None:
    status = read_json(STATUS_FILE, {"state": "idle"})
    status.update(values)
    status["updated_at"] = now_bjt().isoformat()
    write_json_atomic(STATUS_FILE, status)


def build_prompt(report_date: str) -> str:
    base_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    prompt = base_prompt.replace("{{REPORT_DATE}}", report_date)
    if KNOWLEDGE_FILE.exists():
        prompt += "\n\n---\n\n# 内部知识台账（JSON）\n\n"
        prompt += KNOWLEDGE_FILE.read_text(encoding="utf-8")
    return prompt


def extract_output_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if not chunks:
        raise ValueError("API 返回中没有可读取的晨报内容")
    return "\n".join(chunks)


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def call_openai(prompt: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("尚未配置 OPENAI_API_KEY")

    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4"),
        "input": prompt,
        "tools": [{"type": "web_search"}],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=420) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"生成接口返回 {exc.code}: {detail[:600]}") from exc

    text = strip_code_fence(extract_output_text(payload))
    report = json.loads(text)
    report["api_response_id"] = payload.get("id")
    return report


def validate_report(report: Dict[str, Any], report_date: str) -> None:
    required = [
        "report_date", "theme", "macro", "market_flashes", "terms",
        "concept", "company_case", "question", "knowledge_path", "sources",
    ]
    missing = [key for key in required if key not in report]
    if missing:
        raise ValueError("晨报缺少字段：" + ", ".join(missing))
    if report["report_date"] != report_date:
        raise ValueError("晨报日期与任务日期不一致")
    if len(report["macro"]) != 3:
        raise ValueError("全球宏观必须正好3条")
    if not 3 <= len(report["market_flashes"]) <= 5:
        raise ValueError("市场快讯必须为3—5条")
    if len(report["terms"]) != 5:
        raise ValueError("今日名词必须正好5个")


def generate_draft(report_date: str) -> Dict[str, Any]:
    update_status(state="generating", report_date=report_date, error=None)
    try:
        report = call_openai(build_prompt(report_date))
        validate_report(report, report_date)
        report["generated_at"] = now_bjt().isoformat()
        write_json_atomic(DRAFT_FILE, report)
        update_status(state="draft_ready", report_date=report_date)
        return report
    except Exception as exc:
        update_status(state="error", report_date=report_date, error=str(exc))
        raise


def publish_draft(report_date: str) -> bool:
    if not DRAFT_FILE.exists():
        return False
    draft = read_json(DRAFT_FILE)
    if draft.get("report_date") != report_date:
        return False
    draft["published_at"] = now_bjt().isoformat()
    write_json_atomic(LATEST_FILE, draft)
    update_status(state="published", report_date=report_date)
    return True


def scheduler_loop() -> None:
    generated_date = None
    published_date = None
    while True:
        current = now_bjt()
        date_key = current.date().isoformat()
        current_time = current.time().replace(tzinfo=None)

        if current_time >= GENERATE_AT and generated_date != date_key:
            if os.getenv("OPENAI_API_KEY"):
                try:
                    generate_draft(date_key)
                    generated_date = date_key
                except Exception:
                    pass
            else:
                update_status(state="waiting_for_api_key", report_date=date_key)
                generated_date = date_key

        if current_time >= PUBLISH_AT and published_date != date_key:
            if publish_draft(date_key):
                published_date = date_key

        time.sleep(30)


class LauncherHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json({
                "ok": True,
                "timezone": "Asia/Shanghai",
                "generate_at": "07:40",
                "publish_at": "08:00",
                "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
                "status": read_json(STATUS_FILE, {"state": "idle"}),
            })
            return
        if self.path == "/api/reports/latest":
            if not LATEST_FILE.exists():
                self.send_json({"error": "尚无已发布晨报"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(read_json(LATEST_FILE))
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/generate":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            report_date = now_bjt().date().isoformat()
            report = generate_draft(report_date)
            self.send_json({"ok": True, "report_date": report["report_date"]})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "4173"))
    update_status(state="running", host=host, port=port)
    scheduler = threading.Thread(target=scheduler_loop, name="morning-report-scheduler", daemon=True)
    scheduler.start()

    handler = partial(LauncherHandler, directory=str(APP_ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"投资晨报发射器运行于 http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
