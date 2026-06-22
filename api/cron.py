"""Vercel Cron 入口：每天北京时间08:00生成并发布晨报。"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

from lib.morning_report import generate_and_publish


class handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        secret = os.getenv("CRON_SECRET")
        if not secret or self.headers.get("Authorization") != f"Bearer {secret}":
            self.send_json(401, {"ok": False, "error": "Unauthorized"})
            return
        try:
            self.send_json(200, generate_and_publish())
        except Exception as exc:
            # 不返回环境变量、密钥或完整上游响应。
            self.send_json(500, {"ok": False, "error": str(exc)[:600]})
