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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as clock_time, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = ROOT / "launcher" / "prompts" / "report_prompt.md"
KNOWLEDGE_FILE = ROOT / "data" / "knowledge.json"
KNOWLEDGE_MAP_FILE = ROOT / "data" / "knowledge_map.json"
CASE_FILE = ROOT / "data" / "case_library.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")
USER_AGENT = "InvestmentMorningReport/1.0 (+https://github.com/2538449420-cloud/investment-morning-report)"

RSS_SOURCES = [
    ("美联储", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("全球宏观", "https://news.google.com/rss/search?q=global+markets+interest+rates+inflation&hl=en-US&gl=US&ceid=US:en"),
    ("中国市场", "https://news.google.com/rss/search?q=China+economy+A-shares+Hong+Kong+stocks&hl=en-US&gl=US&ceid=US:en"),
    ("科技与公司", "https://news.google.com/rss/search?q=AI+semiconductor+earnings+technology+companies&hl=en-US&gl=US&ceid=US:en"),
    ("商品与汇率", "https://news.google.com/rss/search?q=oil+gold+dollar+commodities+markets&hl=en-US&gl=US&ceid=US:en"),
    ("中国官方政策", "https://news.google.com/rss/search?q=(site%3Agov.cn+OR+site%3Apbc.gov.cn+OR+site%3Astats.gov.cn+OR+site%3Andrc.gov.cn+OR+site%3Amof.gov.cn+OR+site%3Acsrc.gov.cn)+%E7%BB%8F%E6%B5%8E+%E6%94%BF%E7%AD%96+%E5%B8%82%E5%9C%BA&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("中国财经媒体", "https://news.google.com/rss/search?q=(%E8%B4%A2%E6%96%B0+OR+%E7%AC%AC%E4%B8%80%E8%B4%A2%E7%BB%8F+OR+%E8%AF%81%E5%88%B8%E6%97%B6%E6%8A%A5+OR+%E4%B8%8A%E6%B5%B7%E8%AF%81%E5%88%B8%E6%8A%A5+OR+%E4%B8%AD%E5%9B%BD%E8%AF%81%E5%88%B8%E6%8A%A5+OR+%E8%AF%81%E5%88%B8%E6%97%A5%E6%8A%A5+OR+%E7%95%8C%E9%9D%A2%E6%96%B0%E9%97%BB+OR+%E6%BE%8E%E6%B9%83%E8%B4%A2%E7%BB%8F)+%E8%82%A1%E5%B8%82+%E7%BB%8F%E6%B5%8E+%E5%85%AC%E5%8F%B8&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("中国产业", "https://news.google.com/rss/search?q=%E4%B8%AD%E5%9B%BD+AI+%E6%96%B0%E8%83%BD%E6%BA%90%E8%BD%A6+%E6%88%BF%E5%9C%B0%E4%BA%A7+%E9%93%B6%E8%A1%8C+%E6%B6%88%E8%B4%B9+%E8%83%BD%E6%BA%90&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("海外权威财经", "https://news.google.com/rss/search?q=Reuters+Bloomberg+CNBC+WSJ+markets+earnings+economy&hl=en-US&gl=US&ceid=US:en"),
]

TOPIC_KEYWORDS = {
    "AI": ["AI", "人工智能", "大模型", "算力", "数据中心"],
    "芯片": ["chip", "semiconductor", "GPU", "NVIDIA", "Micron", "Broadcom", "芯片", "半导体", "存储"],
    "利率": ["Fed", "FOMC", "rate", "yield", "利率", "降息", "加息", "LPR", "美联储", "央行"],
    "房地产": ["property", "real estate", "housing", "房地产", "楼市", "房贷"],
    "消费": ["consumer", "retail", "spending", "消费", "零售", "餐饮", "旅游"],
    "能源": ["energy", "power", "electricity", "能源", "电力", "天然气"],
    "原油": ["oil", "crude", "OPEC", "原油", "油价", "石油"],
    "黄金": ["gold", "黄金", "金价"],
    "新能源汽车": ["EV", "electric vehicle", "新能源车", "新能源汽车", "电动车", "电池"],
    "银行": ["bank", "银行", "净息差", "信贷"],
    "医药": ["healthcare", "pharma", "drug", "医药", "创新药"],
    "出口": ["export", "tariff", "trade", "出口", "关税", "外贸"],
    "汇率": ["dollar", "yuan", "currency", "FX", "美元", "人民币", "汇率"],
    "政策": ["policy", "regulation", "政策", "监管", "财政部", "发改委", "证监会"],
}

DEFAULT_KNOWLEDGE_MAP = {
    "估值": ["PE", "PB", "PS", "PEG", "EV/EBITDA", "DCF", "安全边际", "内在价值", "市值", "企业价值", "股息率"],
    "财务分析": ["收入", "成本", "毛利率", "净利率", "EPS", "ROE", "ROIC", "ROA", "自由现金流", "经营现金流", "CapEx", "折旧", "资产负债率", "应收账款", "存货周转", "现金转换周期", "汇兑损益"],
    "商业模式": ["网络效应", "规模效应", "护城河", "品牌", "定价权", "客户粘性", "平台模式", "SaaS", "订阅模式", "一次性销售", "渠道优势", "成本优势", "复购率"],
    "行业分析": ["半导体", "AI", "GPU", "银行", "消费", "医药", "能源", "新能源", "地产", "航空", "汽车", "云计算", "软件", "电商", "游戏"],
    "宏观经济": ["GDP", "CPI", "PPI", "PMI", "利率", "汇率", "通胀", "通缩", "流动性", "财政政策", "货币政策", "国债收益率"],
    "市场行为": ["预期差", "风险偏好", "市场情绪", "周期", "Beta", "Alpha", "波动率", "回撤", "杠杆", "去杠杆", "监管风险"],
    "投资方法": ["价值投资", "成长投资", "指数投资", "资产配置", "分散投资", "DCA", "定投", "风险收益比", "夏普比率", "最大回撤"],
    "公司分析": ["商业模式", "收入来源", "成本结构", "利润来源", "客户结构", "供应链", "竞争优势", "生命周期", "管理层", "股东回报", "回购", "分红", "产业补贴"],
}

KNOWLEDGE_PLAYBOOK = {
    "AI": ["AI", "半导体", "云计算", "软件", "CapEx", "折旧", "ROIC", "自由现金流", "客户结构", "网络效应"],
    "芯片": ["半导体", "CapEx", "折旧", "毛利率", "存货周转", "成本结构", "供应链", "周期"],
    "利率": ["利率", "国债收益率", "流动性", "DCF", "安全边际", "企业价值", "风险偏好"],
    "房地产": ["地产", "资产负债率", "经营现金流", "现金转换周期", "杠杆", "去杠杆", "风险收益比"],
    "消费": ["消费", "品牌", "定价权", "客户粘性", "毛利率", "复购率", "渠道优势", "收入来源"],
    "能源": ["能源", "成本", "成本结构", "毛利率", "周期", "风险偏好", "经营现金流"],
    "原油": ["能源", "成本", "成本结构", "周期", "风险偏好", "通胀", "PPI"],
    "黄金": ["利率", "通胀", "汇率", "风险偏好", "波动率", "资产配置"],
    "新能源汽车": ["新能源", "汽车", "规模效应", "成本优势", "毛利率", "存货周转", "供应链"],
    "银行": ["银行", "PB", "资产负债率", "ROE", "ROA", "风险收益比", "股息率", "分红"],
    "医药": ["医药", "收入来源", "净利率", "经营现金流", "生命周期", "竞争优势"],
    "出口": ["汇率", "收入", "成本", "供应链", "PPI", "周期", "风险收益比"],
    "汇率": ["汇率", "利率", "国债收益率", "流动性", "汇兑损益", "资产配置"],
    "政策": ["财政政策", "货币政策", "流动性", "风险偏好", "监管风险", "产业补贴"],
    "市场": ["预期差", "风险偏好", "市场情绪", "波动率", "回撤", "安全边际"],
}

OFFICIAL_DOMAINS = (
    "gov.cn", "pbc.gov.cn", "stats.gov.cn", "ndrc.gov.cn", "mof.gov.cn",
    "csrc.gov.cn", "nea.gov.cn", "mfa.gov.cn", "federalreserve.gov",
    "ecb.europa.eu", "bls.gov", "bea.gov",
)

WIRE_OR_PREMIUM_NAMES = ("Reuters", "Bloomberg", "WSJ", "CNBC", "财新", "第一财经", "证券时报", "上海证券报", "中国证券报", "证券日报")


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


def parse_bjt_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(TIMEZONE)
    except (TypeError, ValueError):
        return None


def source_level(publisher: str, url: str, feed: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(domain in host for domain in OFFICIAL_DOMAINS) or feed in {"美联储", "中国官方政策"}:
        return "official"
    if any(name.lower() in publisher.lower() for name in WIRE_OR_PREMIUM_NAMES):
        return "wire"
    return "mainstream"


def infer_region(text: str, publisher: str, url: str) -> str:
    blob = f"{text} {publisher} {url}".lower()
    if any(token in blob for token in ["中国", "a股", "港股", "人民币", "china", "hong kong", "pbc", "csrc", "gov.cn"]):
        return "CN"
    if any(token in blob for token in ["美国", "美联储", "美元", "us ", "u.s.", "fed", "fomc", "nasdaq", "s&p"]):
        return "US"
    if any(token in blob for token in ["欧央行", "欧洲", "ecb", "eurozone", "europe"]):
        return "EU"
    return "GLOBAL"


def infer_topic(text: str) -> str:
    blob = text.lower()
    scores: dict[str, int] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in blob)
        if score:
            scores[topic] = score
    if not scores:
        return "市场"
    return max(scores.items(), key=lambda item: item[1])[0]


def score_importance(title: str, summary: str, publisher: str, level: str) -> int:
    text = f"{title} {summary}"
    score = 2
    if level == "official":
        score += 2
    elif level == "wire":
        score += 1
    if re.search(r"降息|加息|利率|GDP|PMI|通胀|CPI|PPI|财政|央行|证监会|Fed|FOMC|inflation|tariff|earnings|guidance|oil|gold", text, re.I):
        score += 1
    if re.search(r"突发|重磅|大跌|大涨|surge|fall|plunge|jump|record", text, re.I):
        score += 1
    return max(1, min(score, 5))


def enrich_news_item(item: dict[str, str]) -> dict[str, str | int]:
    title = item.get("title", "")
    summary = item.get("summary", "")
    publisher = item.get("publisher", "")
    url = item.get("url", "")
    feed = item.get("feed", "")
    text = f"{title} {summary}"
    level = source_level(publisher, url, feed)
    return {
        **item,
        "topic": infer_topic(text),
        "region": infer_region(text, publisher, url),
        "source_level": level,
        "importance": score_importance(title, summary, publisher, level),
    }


def news_windows(report_date: str) -> tuple[datetime, datetime, datetime]:
    day = datetime.fromisoformat(report_date).replace(tzinfo=TIMEZONE)
    flash_start = datetime.combine((day - timedelta(days=1)).date(), clock_time(8, 0), TIMEZONE)
    flash_end = datetime.combine(day.date(), clock_time(8, 0), TIMEZONE)
    macro_start = flash_end - timedelta(days=5)
    return macro_start, flash_start, flash_end


def filter_news_for_report_date(news: list[dict[str, Any]], report_date: str) -> dict[str, Any]:
    macro_start, flash_start, flash_end = news_windows(report_date)
    macro_candidates: list[dict[str, Any]] = []
    flash_candidates: list[dict[str, Any]] = []
    for item in news:
        published = parse_bjt_datetime(item.get("published_at"))
        if not published:
            continue
        if macro_start <= published < flash_end:
            macro_candidates.append(item)
        if flash_start <= published < flash_end:
            flash_candidates.append(item)
    macro_candidates.sort(key=lambda item: (int(item.get("importance", 1)), item.get("published_at", "")), reverse=True)
    flash_candidates.sort(key=lambda item: (int(item.get("importance", 1)), item.get("published_at", "")), reverse=True)
    if len(macro_candidates) < 5:
        raise RuntimeError(f"{report_date} 可用宏观候选不足5条")
    if len(flash_candidates) < 2:
        raise RuntimeError(f"{report_date} 严格时间窗口内市场快讯不足2条")
    return {
        "macro_candidates": macro_candidates[:18],
        "flash_candidates": flash_candidates[:16],
        "windows": {
            "macro_start_bjt": macro_start.isoformat(),
            "flash_start_bjt": flash_start.isoformat(),
            "flash_end_bjt": flash_end.isoformat(),
        },
    }


def parse_feed(label: str, url: str, limit: int = 10) -> list[dict[str, str]]:
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
            unique.append(enrich_news_item(item))  # type: ignore[arg-type]
    unique.sort(key=lambda item: (int(item.get("importance", 1)), item.get("published_at", "")), reverse=True)
    if len(unique) < 8:
        raise RuntimeError("可用新闻不足8条；" + " | ".join(errors[:3]))
    return unique[:70]  # type: ignore[return-value]


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]


def choose_case(report_date: str) -> dict[str, Any]:
    cases = load_cases()
    index = int(report_date.replace("-", "")) % len(cases)
    return cases[index]


def estimate_depth_level(entry: dict[str, Any]) -> int:
    text = " ".join(str(entry.get(key, "")) for key in (
        "lesson", "question", "knowledge_today", "knowledge_parent", "summary",
    ))
    text += " " + " ".join(entry.get("knowledge_tags", []) or [])
    depth = 1
    if re.search(r"为什么|不一定|区别|关系|如何|影响|传导|边界|适用|持续", text):
        depth = 2
    if re.search(r"失效|反例|陷阱|周期|银行|资本开支|现金流|ROIC|DCF|压力测试|风险溢价", text, re.I):
        depth = 3
    return depth


def reasoning_pattern_from_entry(entry: dict[str, Any]) -> list[str]:
    tags = []
    text = json.dumps(entry, ensure_ascii=False)
    for label, pattern in {
        "价格-成本-利润": r"成本|毛利|利润|价格|涨价",
        "利率-估值": r"利率|折现|久期|估值|PE|PB",
        "收入-现金流": r"收入|现金流|回款|自由现金流",
        "供需-周期": r"供需|库存|周期|产能|利用率",
        "竞争-护城河": r"竞争|品牌|网络效应|客户|粘性",
        "政策-风险": r"政策|监管|补贴|关税|财政",
    }.items():
        if re.search(pattern, text, re.I):
            tags.append(label)
    return tags or ["通用因果链"]


def compact_history_entry(report: dict[str, Any], archive_path: str) -> dict[str, Any]:
    concept = report.get("concept", {}) or {}
    question = report.get("question", {}) or {}
    knowledge_path = report.get("knowledge_path", {}) or {}
    macro_topics = sorted({item.get("topic") or infer_topic(f"{item.get('title', '')} {item.get('summary', '')}") for item in report.get("macro", []) if item})
    market_topics = sorted({item.get("topic") or infer_topic(f"{item.get('title', '')} {item.get('summary', '')}") for item in report.get("market_flashes", []) if item})
    terms = [item.get("name", "") for item in report.get("terms", []) if item.get("name")]
    knowledge_tags = sorted(set(filter(None, [
        concept.get("title", ""),
        knowledge_path.get("today", ""),
        knowledge_path.get("parent", ""),
        report.get("company_case", {}).get("company", ""),
        *terms,
        *macro_topics,
        *market_topics,
    ])))
    entry = {
        "report_date": report["report_date"],
        "theme": report["theme"],
        "summary": report.get("summary", ""),
        "company": report.get("company_case", {}).get("company", ""),
        "path": archive_path,
        "lesson": concept.get("title", ""),
        "terms": terms,
        "question": question.get("prompt", ""),
        "knowledge_today": knowledge_path.get("today", ""),
        "knowledge_parent": knowledge_path.get("parent", ""),
        "macro_topics": macro_topics,
        "market_topics": market_topics,
        "knowledge_tags": knowledge_tags,
    }
    entry["depth_level"] = estimate_depth_level(entry)
    entry["reasoning_pattern"] = reasoning_pattern_from_entry({
        **entry,
        "concept": concept,
        "company_case": report.get("company_case", {}) or {},
    })
    return entry


def normalize_existing_stat(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "count": int(value.get("count", 0) or 0),
            "last_seen": value.get("last_seen", ""),
            "depth_levels": sorted({int(item) for item in value.get("depth_levels", []) if str(item).isdigit()}),
            "contexts": list(dict.fromkeys(value.get("contexts", []) or []))[:12],
        }
    if isinstance(value, int):
        return {"count": value, "last_seen": "", "depth_levels": [1], "contexts": []}
    return {"count": 0, "last_seen": "", "depth_levels": [], "contexts": []}


def knowledge_stats_from_history(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}

    def touch(name: str, item: dict[str, Any], weight: int = 1) -> None:
        if not name:
            return
        current = stats.setdefault(name, {"count": 0, "last_seen": "", "depth_levels": set(), "contexts": set()})
        current["count"] += weight
        report_date = item.get("report_date", "")
        if report_date and report_date > current["last_seen"]:
            current["last_seen"] = report_date
        current["depth_levels"].add(int(item.get("depth_level") or estimate_depth_level(item)))
        for context in (item.get("macro_topics", []) or []) + (item.get("market_topics", []) or []):
            if context:
                current["contexts"].add(context)

    for item in reports:
        if "depth_level" not in item:
            item = {**item, "depth_level": estimate_depth_level(item)}
        for field in ("lesson", "knowledge_today", "knowledge_parent"):
            touch(item.get(field, ""), item, 2 if field != "knowledge_parent" else 1)
        for value in item.get("terms", []) + item.get("knowledge_tags", []):
            touch(value, item, 1)

    ordered = sorted(stats.items(), key=lambda pair: (-pair[1]["count"], pair[0]))[:120]
    return {
        name: {
            "count": meta["count"],
            "last_seen": meta["last_seen"],
            "depth_levels": sorted(meta["depth_levels"]),
            "contexts": sorted(meta["contexts"])[:12],
        }
        for name, meta in ordered
    }


def expand_history_reports(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded = []
    for item in reports:
        if item.get("lesson") or not item.get("path"):
            expanded.append(item)
            continue
        archive = ROOT / item["path"]
        if archive.exists():
            try:
                report = json.loads(archive.read_text(encoding="utf-8"))
                expanded.append(compact_history_entry(report, item["path"]))
                continue
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        expanded.append(item)
    return expanded


def build_learning_context(history: dict[str, Any], knowledge: dict[str, Any]) -> dict[str, Any]:
    reports = expand_history_reports(history.get("reports", []))
    recent = reports[:30]
    raw_stats = history.get("knowledge_stats") or knowledge_stats_from_history(reports)
    knowledge_stats = {
        key: normalize_existing_stat(value)
        for key, value in raw_stats.items()
    } if isinstance(raw_stats, dict) else {}
    return {
        "recent_lessons": [
            {
                "date": item.get("report_date", ""),
                "lesson": item.get("lesson", ""),
                "knowledge_today": item.get("knowledge_today", ""),
                "knowledge_parent": item.get("knowledge_parent", ""),
                "terms": item.get("terms", []),
                "question": item.get("question", ""),
                "company": item.get("company", ""),
                "macro_topics": item.get("macro_topics", []),
                "market_topics": item.get("market_topics", []),
                "knowledge_tags": item.get("knowledge_tags", []),
                "depth_level": item.get("depth_level") or estimate_depth_level(item),
                "reasoning_pattern": item.get("reasoning_pattern") or reasoning_pattern_from_entry(item),
            }
            for item in recent
        ],
        "knowledge_stats": knowledge_stats,
        "pending_knowledge": history.get("pending_knowledge", []),
        "recent_paths": knowledge.get("recent_paths", []),
        "modules": knowledge.get("modules", []),
    }


def topic_scores(filtered_news: dict[str, Any]) -> Counter[str]:
    scores: Counter[str] = Counter()
    for group, weight in (("macro_candidates", 1.0), ("flash_candidates", 1.4)):
        for item in filtered_news.get(group, []):
            topic = item.get("topic") or "市场"
            importance = int(item.get("importance", 1) or 1)
            level_boost = 1.25 if item.get("source_level") in {"official", "wire"} else 1.0
            scores[topic] += importance * weight * level_boost
    if not scores:
        scores["市场"] = 1
    return scores


def stat_meta(knowledge_stats: dict[str, Any], name: str) -> dict[str, Any]:
    return normalize_existing_stat(knowledge_stats.get(name, {}))


def load_knowledge_map() -> dict[str, Any]:
    if KNOWLEDGE_MAP_FILE.exists():
        try:
            payload = json.loads(KNOWLEDGE_MAP_FILE.read_text(encoding="utf-8"))
            modules = payload.get("modules", payload)
            if isinstance(modules, dict):
                return {
                    "modules": modules,
                    "pending_review": payload.get("pending_review", []) if isinstance(payload, dict) else [],
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {"modules": DEFAULT_KNOWLEDGE_MAP, "pending_review": []}


def flatten_knowledge_map(knowledge_map: Optional[dict[str, Any]] = None) -> dict[str, str]:
    modules = (knowledge_map or load_knowledge_map()).get("modules", {})
    return {
        node: module
        for module, nodes in modules.items()
        for node in nodes
    }


def days_since(date_text: str, report_date: str) -> int:
    if not date_text:
        return 999
    try:
        return (datetime.fromisoformat(report_date).date() - datetime.fromisoformat(date_text).date()).days
    except ValueError:
        return 999


def knowledge_planner(history: dict[str, Any], knowledge_stats: dict[str, Any],
                      filtered_news: dict[str, Any], report_date: str) -> dict[str, Any]:
    """轻量知识候选器：给AI提供地图内候选，不固定课程顺序。"""
    scores = topic_scores(filtered_news)
    ordered_topics = [topic for topic, _ in scores.most_common()]
    candidate_pool: list[tuple[str, str, tuple[int, int, int, int, str]]] = []
    knowledge_map = load_knowledge_map()
    allowed_nodes = flatten_knowledge_map(knowledge_map)

    for topic_rank, topic in enumerate(ordered_topics):
        playbook = KNOWLEDGE_PLAYBOOK.get(topic) or KNOWLEDGE_PLAYBOOK["市场"]
        for position, lesson in enumerate(playbook):
            if lesson not in allowed_nodes:
                continue
            meta = stat_meta(knowledge_stats, lesson)
            count = int(meta.get("count", 0) or 0)
            max_depth = max(meta.get("depth_levels", []) or [0])
            recency_penalty = 0 if days_since(meta.get("last_seen", ""), report_date) >= 10 else 2
            # 越小越适合作为候选：未讲过、讲得浅、最近没讲过、越贴近该新闻主题。
            rank = (count + recency_penalty, max_depth, topic_rank, position, lesson)
            candidate_pool.append((topic, lesson, rank))

    candidate_pool.sort(key=lambda item: item[2])
    primary_topic, primary, _ = candidate_pool[0] if candidate_pool else ("市场", "预期差", (0, 0, 0, 0, "预期差"))
    candidates = []
    for topic, lesson, _ in candidate_pool:
        if lesson not in candidates:
            candidates.append(lesson)
        if len(candidates) >= 8:
            break

    primary_meta = stat_meta(knowledge_stats, primary)
    next_depth = min(max((primary_meta.get("depth_levels") or [0])) + 1, 3)
    return {
        "suggested_focus": primary,
        "suggested_topic": primary_topic,
        "candidates": candidates,
        "suggested_depth_level": next_depth,
        "news_topics": ordered_topics[:6],
        "note": "这不是固定课程表，只是基于今日新闻和历史覆盖计算出的优先候选。AI应优先参考knowledge_map，也可在重大新主题出现时提出新知识点并归入现有模块。",
        "reason": f"今日新闻权重较高领域包含{primary_topic}；{primary}历史覆盖次数为{primary_meta.get('count', 0)}，可作为候选知识。",
    }


def build_generation_prompt(report_date: str, news: list[dict[str, str]], case: dict[str, Any],
                            retry_note: str = "",
                            filtered_news: Optional[dict[str, Any]] = None,
                            learning_context: Optional[dict[str, Any]] = None,
                            knowledge_plan: Optional[dict[str, Any]] = None) -> str:
    base = PROMPT_FILE.read_text(encoding="utf-8").replace("{{REPORT_DATE}}", report_date)
    knowledge = KNOWLEDGE_FILE.read_text(encoding="utf-8") if KNOWLEDGE_FILE.exists() else "{}"
    history_file = ROOT / "data" / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {"reports": []}
    knowledge_payload = json.loads(knowledge) if knowledge.strip() else {}
    filtered_news = filtered_news or filter_news_for_report_date(news, report_date)
    learning_context = learning_context or build_learning_context(history, knowledge_payload)
    knowledge_plan = knowledge_plan or knowledge_planner(
        history,
        learning_context.get("knowledge_stats", {}),
        filtered_news,
        report_date,
    )
    knowledge_map = load_knowledge_map()
    return f"""{base}

# 本次任务的额外硬规则

你面对的是投资小白，但不能过度简化。先讲事实，再讲因果链，再讲不确定性。
保持广度优先、深度穿插；5个名词必须互相连接，并与今日概念或案例相连。
公司案例必须具体解释客户为何付钱、收入如何变成利润和现金、优势如何形成、何时失效。
不得使用空话，例如“商业模式很好”“前景广阔”“值得关注”。

你没有联网工具。以下“新闻候选”“公司资料”和“历史学习台账”是唯一允许使用的事实来源：
- sources中的新闻URL必须逐字复制新闻候选中的URL；不得自行创造或改写URL。
- 公司案例只能使用指定公司资料；没有数字就不要编数字，metrics可以为空数组。
- market_flashes只能使用“严格快讯候选”；这些新闻已经由Python按北京时间昨日08:00至今日08:00过滤。
- macro只能使用“宏观候选”；这些新闻允许回溯最近3—5天。
- 新闻不足以支持某个结论时，明确写“不确定”，不要补写想象内容。
- 课程不能重复昨天或近期课程的学习价值。不能只是换标题、换新闻、换公司，但仍然讲同一个lesson。
- 今天的晨报必须同时回答两个问题：第一，今天市场发生了什么？第二，投资者今天应该学会什么新的认知？
- 新闻提供时效性，知识提供成长性，两者同等重要；任何一项缺失，都不是合格晨报。
- Knowledge Map是优先参考的知识空间，不是封闭边界、也不是固定课程表。
- 优先从Knowledge Map中选择知识点。如果今日重大新闻涉及Knowledge Map尚未覆盖的新知识，可以新增知识点，但必须归属到现有模块，并尽量避免与历史知识重复。
- 多个知识都合适时，按以下优先级选择：①与今日新闻联系最紧密；②历史覆盖较少；③更能帮助投资者建立长期认知；④与最近几天课程差异更大。
- 今日知识候选只是Python根据新闻主题和历史覆盖给出的参考，不是强制主课。
- 如果同一主题再次出现，必须推进一层，例如从定义推进到适用边界、失效条件、财务影响或估值影响。

# Knowledge Map（优先参考；不是封闭边界，不代表顺序）
{json.dumps(knowledge_map, ensure_ascii=False, indent=2)}

# 今日知识候选（非固定课程表；仅供选择时参考）
{json.dumps(knowledge_plan, ensure_ascii=False, indent=2)}

# 新闻窗口
{json.dumps(filtered_news["windows"], ensure_ascii=False, indent=2)}

# 宏观候选（macro只能从这里选择，最近3—5天）
{json.dumps(filtered_news["macro_candidates"], ensure_ascii=False, indent=2)}

# 严格快讯候选（market_flashes只能从这里选择，昨日08:00至今日08:00）
{json.dumps(filtered_news["flash_candidates"], ensure_ascii=False, indent=2)}

# 今日指定公司资料
{json.dumps(case, ensure_ascii=False, indent=2)}

# 历史学习台账（用于避免重复学习价值）
{json.dumps(learning_context, ensure_ascii=False, indent=2)}

{retry_note}
"""


def normalize_for_similarity(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return re.sub(r"[\W_]+", "", text.lower())


def text_similarity(left: Any, right: Any) -> float:
    a = normalize_for_similarity(left)
    b = normalize_for_similarity(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    grams_a = {a[i:i + 2] for i in range(max(1, len(a) - 1))}
    grams_b = {b[i:i + 2] for i in range(max(1, len(b) - 1))}
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def report_learning_signature(report: dict[str, Any]) -> dict[str, Any]:
    concept = report.get("concept", {}) or {}
    path = report.get("knowledge_path", {}) or {}
    question = report.get("question", {}) or {}
    company = report.get("company_case", {}) or {}
    return {
        "lesson": concept.get("title", ""),
        "knowledge_topic": path.get("today", ""),
        "parent": path.get("parent", ""),
        "terms": [item.get("name", "") for item in report.get("terms", []) if item.get("name")],
        "question": question.get("prompt", ""),
        "company_case": company.get("topic", "") or company.get("business_model", ""),
        "reasoning_pattern": reasoning_pattern_from_entry({
            "concept": concept,
            "knowledge_path": path,
            "question": question,
            "company_case": company,
        }),
    }


def history_learning_signature(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "lesson": item.get("lesson", ""),
        "knowledge_topic": item.get("knowledge_today", ""),
        "parent": item.get("knowledge_parent", ""),
        "terms": item.get("terms", []) or [],
        "question": item.get("question", ""),
        "company_case": item.get("company", ""),
        "reasoning_pattern": item.get("reasoning_pattern") or reasoning_pattern_from_entry(item),
    }


def learning_structure_similarity(new_sig: dict[str, Any], old_sig: dict[str, Any]) -> float:
    new_terms = set(new_sig.get("terms", []) or [])
    old_terms = set(old_sig.get("terms", []) or [])
    new_patterns = set(new_sig.get("reasoning_pattern", []) or [])
    old_patterns = set(old_sig.get("reasoning_pattern", []) or [])
    term_score = len(new_terms & old_terms) / max(1, min(len(new_terms), len(old_terms) or 1))
    pattern_score = len(new_patterns & old_patterns) / max(1, min(len(new_patterns), len(old_patterns) or 1))
    weighted = (
        text_similarity(new_sig.get("lesson", ""), old_sig.get("lesson", "")) * 0.25
        + text_similarity(new_sig.get("knowledge_topic", ""), old_sig.get("knowledge_topic", "")) * 0.25
        + term_score * 0.18
        + text_similarity(new_sig.get("question", ""), old_sig.get("question", "")) * 0.16
        + text_similarity(new_sig.get("company_case", ""), old_sig.get("company_case", "")) * 0.08
        + pattern_score * 0.08
    )
    return min(1.0, weighted)


def validate_knowledge_choice(report: dict[str, Any]) -> list[str]:
    knowledge_map = load_knowledge_map()
    modules = set((knowledge_map.get("modules", {}) or {}).keys())
    allowed = flatten_knowledge_map(knowledge_map)
    concept_title = (report.get("concept", {}) or {}).get("title", "")
    path = report.get("knowledge_path", {}) or {}
    today = path.get("today", "")
    module = path.get("module", "")
    chosen = today or concept_title
    if not chosen:
        return ["缺少今日知识节点：concept.title和knowledge_path.today不能同时为空"]
    is_existing = any(text_similarity(chosen, node) >= 0.72 or text_similarity(concept_title, node) >= 0.72 for node in allowed)
    if not is_existing and module not in modules:
        return [f"新增知识点必须归属到Knowledge Map现有模块：today={today}，module={module}"]
    return []


def pending_knowledge_from_report(report: dict[str, Any], report_date: str) -> Optional[dict[str, Any]]:
    allowed = flatten_knowledge_map()
    concept_title = (report.get("concept", {}) or {}).get("title", "")
    path = report.get("knowledge_path", {}) or {}
    today = path.get("today", "") or concept_title
    if not today:
        return None
    if any(text_similarity(today, node) >= 0.72 or text_similarity(concept_title, node) >= 0.72 for node in allowed):
        return None
    return {
        "name": today,
        "module": path.get("module", "待归类"),
        "first_seen": report_date,
        "source": "ai_generated_report",
        "reason": "AI在今日重大新闻中选择了Knowledge Map尚未覆盖的新知识点，需人工审核是否加入正式地图。",
    }


def merge_pending_knowledge(history: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    pending = list(history.get("pending_knowledge", []) or [])
    candidate = pending_knowledge_from_report(report, report["report_date"])
    if not candidate:
        return pending
    for item in pending:
        if text_similarity(item.get("name", ""), candidate["name"]) >= 0.8:
            item["last_seen"] = report["report_date"]
            item["count"] = int(item.get("count", 1) or 1) + 1
            return pending
    candidate["last_seen"] = report["report_date"]
    candidate["count"] = 1
    pending.insert(0, candidate)
    return pending[:80]


def check_learning_similarity(report: dict[str, Any], history: dict[str, Any]) -> list[str]:
    new_sig = report_learning_signature(report)
    problems: list[str] = []
    for item in history.get("reports", [])[:30]:
        old_sig = history_learning_signature(item)
        structure_score = learning_structure_similarity(new_sig, old_sig)
        if structure_score >= 0.70:
            problems.append(f"知识结构与{item.get('report_date')}重复度{structure_score:.0%}：{item.get('lesson')}")
        if new_sig["lesson"] and text_similarity(new_sig["lesson"], item.get("lesson", "")) >= 0.72:
            problems.append(f"lesson与{item.get('report_date')}过于相似：{item.get('lesson')}")
        if new_sig["knowledge_topic"] and new_sig["knowledge_topic"] == item.get("knowledge_today"):
            problems.append(f"knowledge_path.today重复：{new_sig['knowledge_topic']}")
        if new_sig["question"] and text_similarity(new_sig["question"], item.get("question", "")) >= 0.68:
            problems.append(f"question与{item.get('report_date')}过于相似")
    return problems[:6]


def generate_report_with_retry(report_date: str, news: list[dict[str, str]], case: dict[str, Any],
                               history: dict[str, Any], max_attempts: int = 3) -> dict[str, Any]:
    knowledge_payload = json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8")) if KNOWLEDGE_FILE.exists() else {}
    history = {**history, "reports": expand_history_reports(history.get("reports", []))}
    filtered_news = filter_news_for_report_date(news, report_date)
    learning_context = build_learning_context(history, knowledge_payload)
    knowledge_plan = knowledge_planner(
        history,
        learning_context.get("knowledge_stats", {}),
        filtered_news,
        report_date,
    )
    retry_note = ""
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        report = call_ai(build_generation_prompt(
            report_date,
            news,
            case,
            retry_note,
            filtered_news=filtered_news,
            learning_context=learning_context,
            knowledge_plan=knowledge_plan,
        ))
        normalize_sources(report, news, case)
        validate_report(report, report_date, news, case)
        problems = validate_knowledge_choice(report)
        problems.extend(check_learning_similarity(report, history))
        if not problems:
            return report
        last_error = "；".join(problems)
        retry_note = f"""
# 上一次生成被Python拒绝
原因：{last_error}

请重新设计课程。请优先参考Knowledge Map；如果确实是今日重大新主题，也可以选择新知识，但必须归入现有模块，且不能只是换标题或新闻。
如果同一知识必须再次出现，请至少推进到新的场景、边界、失效条件或财务/估值影响。
"""
        print(f"第 {attempt} 次生成学习价值重复，准备重试：{last_error[:300]}")
    raise RuntimeError("连续生成的学习价值过于重复：" + last_error[:500])


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

    request_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的投资教育编辑，只输出合法JSON对象。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 7000,
    }
    if provider == "deepseek":
        request_body["response_format"] = {"type": "json_object"}

    payload = request_json(
        endpoint,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        body=request_body,
        timeout=180,
    )
    choice = payload["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("AI输出达到长度上限，已拒绝保存不完整晨报")
    return extract_json(choice["message"]["content"])


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
    if len(report["macro"]) != 3 or not 2 <= len(report["market_flashes"]) <= 5:
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
    filtered = filter_news_for_report_date(news, report_date)
    source_url_by_id = {source["id"]: source["url"] for source in report["sources"]}
    macro_urls = {item["url"] for item in filtered["macro_candidates"]}
    flash_urls = {item["url"] for item in filtered["flash_candidates"]}
    for item in report["macro"]:
        if not any(source_url_by_id.get(source_id) in macro_urls for source_id in item.get("source_ids", [])):
            raise ValueError("宏观引用了窗口外或非宏观候选来源")
    for item in report["market_flashes"]:
        if not any(source_url_by_id.get(source_id) in flash_urls for source_id in item.get("source_ids", [])):
            raise ValueError("市场快讯引用了严格时间窗口外来源")
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
            "source_type": "primary" if item.get("source_level") == "official" else item.get("source_level", "mainstream"),
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
    reports = [item for item in expand_history_reports(history.get("reports", [])) if item.get("report_date") != report_date]
    reports.insert(0, compact_history_entry(report, archive_path))
    save_json_to_github(
        "data/history.json",
        {
            "reports": reports,
            "knowledge_stats": knowledge_stats_from_history(reports),
            "pending_knowledge": merge_pending_knowledge(history, report),
        },
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
    history_file = ROOT / "data" / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {"reports": []}
    history["reports"] = expand_history_reports(history.get("reports", []))
    report = generate_report_with_retry(report_date, news, company_case, history)
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
