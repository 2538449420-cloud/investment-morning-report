"""Vercel Cron 使用的投资晨报生成核心。

仅使用 Python 标准库：抓取公开 RSS，调用可替换 AI 接口，严格校验后把
data/today.json 写回 GitHub。任何失败都不会覆盖上一期晨报。
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = ROOT / "launcher" / "prompts" / "report_prompt.md"
KNOWLEDGE_FILE = ROOT / "data" / "knowledge.json"
CASE_FILE = ROOT / "data" / "case_library.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")
USER_AGENT = "InvestmentMorningReport/1.0 (+https://github.com/2538449420-cloud/investment-morning-report)"

RSS_SOURCES = [
    ("美联储", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("全球宏观", "https://news.google.com/rss/search?q=global+markets+interest+rates+inflation&hl=en-US&gl=US&ceid=US:en"),
    ("中国市场", "https://news.google.com/rss/search?q=China+economy+A-shares+Hong+Kong+stocks&hl=en-US&gl=US&ceid=US:en"),
    ("科技与公司", "https://news.google.com/rss/search?q=AI+semiconductor+earnings+technology+companies&hl=en-US&gl=US&ceid=US:en"),
    ("商品与汇率", "https://news.google.com/rss/search?q=oil+gold+dollar+commodities+markets&hl=en-US&gl=US&ceid=US:en"),
]


def now_bjt() -> datetime:
    return datetime.now(TIMEZONE)


def request_json(url: str, *, method: str = "GET", headers: Optional[dict[str, str]] = None,
                 body: Optional[dict[str, Any]] = None, timeout: int = 55) -> dict[str, Any]:
    raw = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=raw, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def fetch_bytes(url: str, timeout: int = 18) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(1_500_000)


def clean_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(TIMEZONE).isoformat()
    except (TypeError, ValueError, OverflowError):
        return clean_text(value)


def parse_feed(label: str, url: str, limit: int = 7) -> list[dict[str, str]]:
    root = ET.fromstring(fetch_bytes(url))
    items: list[dict[str, str]] = []
    candidates = root.findall(".//item")
    if not candidates:
        candidates = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in candidates[:limit]:
        title = clean_text(item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title"))
        link = clean_text(item.findtext("link"))
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link = clean_text(atom_link.get("href") if atom_link is not None else "")
        published = (
            item.findtext("pubDate")
            or item.findtext("{http://www.w3.org/2005/Atom}published")
            or item.findtext("{http://www.w3.org/2005/Atom}updated")
        )
        source = item.findtext("source") or label
        description = clean_text(
            item.findtext("description")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
        )
        if title and link.startswith("http"):
            items.append({
                "publisher": clean_text(source) or label,
                "feed": label,
                "title": title,
                "summary": description[:600],
                "published_at": parse_date(published),
                "url": link,
            })
    return items


def collect_news() -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(RSS_SOURCES)) as pool:
        jobs = {pool.submit(parse_feed, label, url): label for label, url in RSS_SOURCES}
        for future in as_completed(jobs):
            label = jobs[future]
            try:
                collected.extend(future.result())
            except Exception as exc:  # 单一来源失败不应拖垮整份晨报
                errors.append(f"{label}: {exc}")
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in collected:
        key = re.sub(r"\W+", "", item["title"].lower())[:100]
        if key and key not in seen:
            seen.add(key)
            item["id"] = f"n{len(unique) + 1}"
            unique.append(item)
    if len(unique) < 8:
        raise RuntimeError("可用新闻不足8条；" + " | ".join(errors[:3]))
    return unique[:28]


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]


def choose_case(report_date: str) -> dict[str, Any]:
    cases = load_cases()
    index = int(report_date.replace("-", "")) % len(cases)
    return cases[index]


def build_generation_prompt(report_date: str, news: list[dict[str, str]], case: dict[str, Any]) -> str:
    base = PROMPT_FILE.read_text(encoding="utf-8").replace("{{REPORT_DATE}}", report_date)
    knowledge = KNOWLEDGE_FILE.read_text(encoding="utf-8") if KNOWLEDGE_FILE.exists() else "{}"
    return f"""{base}

# 本次任务的额外硬规则

你面对的是投资小白，但不能过度简化。先讲事实，再讲因果链，再讲不确定性。
保持广度优先、深度穿插；5个名词必须互相连接，并与今日概念或案例相连。
公司案例必须具体解释客户为何付钱、收入如何变成利润和现金、优势如何形成、何时失效。
不得使用空话，例如“商业模式很好”“前景广阔”“值得关注”。

你没有联网工具。以下“新闻候选”和“公司资料”是唯一允许使用的事实来源：
- sources中的新闻URL必须逐字复制新闻候选中的URL；不得自行创造或改写URL。
- 公司案例只能使用指定公司资料；没有数字就不要编数字，metrics可以为空数组。
- 时间窗口以候选的published_at为准。无法确认在窗口内的项目不要写成市场快讯。
- 新闻不足以支持某个结论时，明确写“不确定”，不要补写想象内容。

# 新闻候选
{json.dumps(news, ensure_ascii=False, indent=2)}

# 今日指定公司资料
{json.dumps(case, ensure_ascii=False, indent=2)}

# 内部知识台账
{knowledge}
"""


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI返回中没有JSON对象")
    return json.loads(stripped[start:end + 1])


def call_ai(prompt: str) -> dict[str, Any]:
    provider = os.getenv("AI_PROVIDER", "github_models").lower()
    if provider == "github_models":
        token = os.getenv("GH_MODELS_TOKEN")
        if not token:
            raise RuntimeError("尚未配置 GH_MODELS_TOKEN")
        endpoint = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")
        model = os.getenv("AI_MODEL", "openai/gpt-4.1-mini")
    elif provider == "deepseek":
        token = os.getenv("DEEPSEEK_API_KEY")
        if not token:
            raise RuntimeError("尚未配置 DEEPSEEK_API_KEY")
        endpoint = os.getenv("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions")
        model = os.getenv("AI_MODEL", "deepseek-chat")
    elif provider == "openai":
        token = os.getenv("OPENAI_API_KEY")
        if not token:
            raise RuntimeError("尚未配置 OPENAI_API_KEY")
        endpoint = os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("AI_MODEL", "gpt-5.4")
    else:
        token = os.getenv("AI_API_KEY")
        endpoint = os.getenv("AI_ENDPOINT")
        model = os.getenv("AI_MODEL")
        if not all([token, endpoint, model]):
            raise RuntimeError("自定义AI需要 AI_API_KEY、AI_ENDPOINT、AI_MODEL")

    payload = request_json(
        endpoint,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        body={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的投资教育编辑，只输出合法JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 5000,
        },
        timeout=180,
    )
    return extract_json(payload["choices"][0]["message"]["content"])


def validate_report(report: dict[str, Any], report_date: str, news: list[dict[str, str]],
                    case: dict[str, Any]) -> None:
    required = [
        "report_date", "theme", "summary", "macro", "market_flashes", "terms",
        "concept", "company_case", "question", "knowledge_path", "sources", "disclaimer",
    ]
    missing = [key for key in required if key not in report]
    if missing:
        raise ValueError("晨报缺少字段：" + ", ".join(missing))
    if report["report_date"] != report_date:
        raise ValueError("晨报日期不正确")
    if len(report["macro"]) != 3 or not 3 <= len(report["market_flashes"]) <= 5:
        raise ValueError("宏观或市场快讯数量不正确")
    if len(report["terms"]) != 5:
        raise ValueError("投资名词必须正好5个")
    if report["company_case"].get("company") != case["company"]:
        raise ValueError("AI更换了指定公司案例")

    allowed_urls = {item["url"] for item in news}
    allowed_urls.update(source["url"] for source in case.get("sources", []))
    source_ids: set[str] = set()
    for source in report["sources"]:
        if source.get("url") not in allowed_urls:
            raise ValueError(f"发现未授权来源URL：{source.get('url')}")
        if not source.get("id") or source["id"] in source_ids:
            raise ValueError("来源ID缺失或重复")
        source_ids.add(source["id"])
    for collection in (report["macro"], report["market_flashes"]):
        for item in collection:
            if not item.get("source_ids") or not set(item["source_ids"]).issubset(source_ids):
                raise ValueError("宏观或快讯存在无法追溯的来源")
    for metric in report["company_case"].get("metrics", []):
        if not metric.get("source_ids") or not set(metric["source_ids"]).issubset(source_ids):
            raise ValueError("公司指标存在无法追溯的来源")


def normalize_sources(report: dict[str, Any], news: list[dict[str, str]],
                      case: dict[str, Any]) -> None:
    canonical: dict[str, dict[str, str]] = {}
    for item in news:
        canonical[item["url"]] = {
            "publisher": item["publisher"],
            "title": item["title"],
            "published_at": item["published_at"],
            "url": item["url"],
            "source_type": "mainstream" if item["feed"] != "美联储" else "primary",
        }
    for source in case.get("sources", []):
        canonical[source["url"]] = {
            "publisher": source["publisher"],
            "title": source["title"],
            "published_at": source.get("published_at", ""),
            "url": source["url"],
            "source_type": source.get("source_type", "primary"),
        }
    for source in report.get("sources", []):
        source_id = source.get("id")
        original = canonical.get(source.get("url", ""))
        if source_id and original:
            source.clear()
            source.update({"id": source_id, **original})


def github_file(path: str, token: str, repository: str) -> Optional[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}"
    try:
        return request_json(url, headers={
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def save_json_to_github(path: str, payload: dict[str, Any], message: str) -> dict[str, Any]:
    token = os.getenv("GH_CONTENT_TOKEN")
    repository = os.getenv("GH_CONTENT_REPOSITORY", "2538449420-cloud/investment-morning-report")
    if not token:
        raise RuntimeError("尚未配置 GH_CONTENT_TOKEN")
    existing = github_file(path, token, repository)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if existing and existing.get("sha"):
        body["sha"] = existing["sha"]
    url = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path)}"
    return request_json(
        url,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        body=body,
    )


def load_history_index(token: str, repository: str) -> dict[str, Any]:
    path = "data/history.json"
    existing = github_file(path, token, repository)
    if not existing or not existing.get("content"):
        return {"reports": []}
    raw = base64.b64decode(existing["content"].replace("\n", ""))
    return json.loads(raw.decode("utf-8"))


def save_report_bundle(report: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("GH_CONTENT_TOKEN")
    repository = os.getenv("GH_CONTENT_REPOSITORY", "2538449420-cloud/investment-morning-report")
    if not token:
        raise RuntimeError("尚未配置 GH_CONTENT_TOKEN")
    report_date = report["report_date"]
    archive_path = f"data/history/{report_date}.json"

    # 先归档，再更新目录，最后切换today；中途失败时旧晨报仍保持可读。
    save_json_to_github(
        archive_path,
        report,
        f"晨报归档：{report_date}",
    )
    history = load_history_index(token, repository)
    reports = [item for item in history.get("reports", []) if item.get("report_date") != report_date]
    reports.insert(0, {
        "report_date": report_date,
        "theme": report["theme"],
        "summary": report.get("summary", ""),
        "company": report.get("company_case", {}).get("company", ""),
        "path": archive_path,
    })
    save_json_to_github(
        "data/history.json",
        {"reports": reports},
        f"晨报目录：更新 {report_date}",
    )
    return save_json_to_github(
        "data/today.json",
        report,
        f"今日晨报：更新 {report_date}",
    )


def generate_and_publish() -> dict[str, Any]:
    current = now_bjt()
    report_date = current.date().isoformat()
    news = collect_news()
    company_case = choose_case(report_date)
    report = call_ai(build_generation_prompt(report_date, news, company_case))
    normalize_sources(report, news, company_case)
    validate_report(report, report_date, news, company_case)
    report["generated_at"] = current.isoformat()
    report["published_at"] = now_bjt().isoformat()
    result = save_report_bundle(report)
    return {
        "ok": True,
        "report_date": report_date,
        "news_candidates": len(news),
        "company": company_case["company"],
        "commit": result.get("commit", {}).get("sha"),
    }
