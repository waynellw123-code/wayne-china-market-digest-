from __future__ import annotations

import html
import os
import re
import smtplib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

CATEGORY_RULES = {
    "A股": ["a股", "沪深", "创业板", "科创板", "上证", "深证", "并购重组", "ipo", "证监会"],
    "债市": ["债市", "国债", "地方债", "收益率", "利率债", "信用债", "逆回购", "mlf", "shibor"],
    "汇率": ["汇率", "人民币", "美元兑人民币", "中间价", "外汇", "离岸人民币"],
    "政策": ["政策", "两会", "财政", "央行", "金融监管", "国常会", "国务院", "人大", "金监总局"],
}

SEARCH_GROUPS = {
    "A股": [
        "中国 A股 证监会 政策 资本市场",
        "中国 科创板 创业板 并购重组",
    ],
    "债市": [
        "中国 债市 国债 地方债 央行 流动性",
        "中国 债券市场 收益率 逆回购 MLF",
    ],
    "汇率": [
        "人民币 汇率 央行 外汇市场",
        "离岸人民币 中间价 外汇管理",
    ],
    "政策": [
        "中国 金融政策 央行 财政部 金融监管总局",
        "中国 两会 金融 市场 政策",
    ],
}


@dataclass
class NewsItem:
    category: str
    title: str
    url: str
    snippet: str
    source: str


def shanghai_now() -> datetime:
    return datetime.now(tz=TZ)


def week_range(today: datetime) -> tuple[str, str]:
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def is_monday(today: datetime) -> bool:
    return today.weekday() == 0


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    cookie_text = os.getenv("BAIDU_COOKIES", "").strip()
    if cookie_text:
        for pair in cookie_text.split(";"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            session.cookies.set(key.strip(), value.strip(), domain=".baidu.com")
    return session


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_source(url: str, fallback: str) -> str:
    if fallback:
        return fallback
    match = re.search(r"https?://([^/]+)", url)
    return match.group(1) if match else "百度搜索"


def categorize(title: str, snippet: str, default_category: str) -> str:
    haystack = f"{title} {snippet}".lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return default_category


def extract_items_from_html(html_text: str, default_category: str) -> list[NewsItem]:
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[NewsItem] = []
    seen: set[str] = set()

    for link in soup.select("h3 a"):
        title = clean_text(link.get_text(" ", strip=True))
        url = link.get("href", "").strip()
        if not title or not url or url in seen:
            continue

        block = link.find_parent(["div", "article"]) or link.parent
        block_text = clean_text(block.get_text(" ", strip=True))
        snippet = clean_text(block_text.replace(title, "", 1))[:180]
        source_nodes = block.select("span, div")
        source = ""
        for node in source_nodes:
            text = clean_text(node.get_text(" ", strip=True))
            if text and len(text) <= 40 and ("网" in text or "报" in text or "社" in text or "证券" in text):
                source = text
                break

        items.append(
            NewsItem(
                category=categorize(title, snippet, default_category),
                title=title,
                url=url,
                snippet=snippet,
                source=infer_source(url, source),
            )
        )
        seen.add(url)

    return items


def fetch_baidu_results(session: requests.Session, query: str, default_category: str) -> list[NewsItem]:
    url = f"https://www.baidu.com/s?ie=utf-8&tn=news&rtt=1&bsst=1&cl=2&wd={quote(query)}"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return extract_items_from_html(response.text, default_category)


def collect_news() -> dict[str, list[NewsItem]]:
    session = build_session()
    grouped: dict[str, list[NewsItem]] = defaultdict(list)
    seen_urls: set[str] = set()

    for category, queries in SEARCH_GROUPS.items():
        for query in queries:
            try:
                items = fetch_baidu_results(session, query, category)
            except Exception:
                continue

            for item in items:
                if item.url in seen_urls:
                    continue
                grouped[item.category].append(item)
                seen_urls.add(item.url)

    for category in CATEGORY_RULES:
        grouped.setdefault(category, [])

    return grouped


def top_items(items: Iterable[NewsItem], limit: int = 4) -> list[NewsItem]:
    filtered: list[NewsItem] = []
    for item in items:
        title = item.title.lower()
        if any(noise in title for noise in ["百度一下", "登录", "注册", "相关搜索"]):
            continue
        filtered.append(item)
        if len(filtered) >= limit:
            break
    return filtered


def render_section(category: str, items: list[NewsItem]) -> str:
    lines = [f"## {category}"]
    selected = top_items(items)
    if not selected:
        lines.append("- 暂未抓到足够稳定的相关新闻线索，建议手动补充核验。")
        return "\n".join(lines)

    for item in selected:
        summary = item.snippet or "百度搜索结果未提供稳定摘要，建议打开原文核对。"
        lines.append(f"- {item.title}")
        lines.append(f"  摘要：{summary}")
        lines.append(f"  来源：[{item.source}]({item.url})")
    return "\n".join(lines)


def build_report(grouped: dict[str, list[NewsItem]], today: datetime) -> str:
    start_date, end_date = week_range(today)
    monday_mode = is_monday(today)
    title = "本周前瞻" if monday_mode else "周内滚动简报"
    intro = (
        "本期聚焦未来一周可能持续影响中国金融市场的政策与交易线索。"
        if monday_mode
        else "本期汇总本周截至目前的重要中国金融市场资讯，便于早盘快速浏览。"
    )

    sections = [render_section(category, grouped.get(category, [])) for category in ["A股", "债市", "汇率", "政策"]]
    sources_note = (
        "说明：内容基于百度搜索结果整理，建议对重要条目点击原始来源复核。"
    )

    return "\n\n".join(
        [
            f"# 中国金融市场晨报：{title}",
            f"- 日期：{today.strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）",
            f"- 范围：{start_date} 至 {end_date}",
            f"- 导语：{intro}",
            *sections,
            f"## 备注\n- {sources_note}",
        ]
    )


def save_report(content: str, today: datetime) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"market-digest-{today.strftime('%Y-%m-%d')}.md"
    path.write_text(content, encoding="utf-8")
    return path


def markdown_to_html(markdown_text: str) -> str:
    html_lines = []
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            html_lines.append(f"<p>{html.escape(line[2:])}</p>")
        elif line.startswith("  "):
            html_lines.append(f"<p style='margin-left: 1.5em'>{html.escape(line.strip())}</p>")
        elif line.strip():
            html_lines.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(html_lines)


def send_email(subject: str, markdown_content: str) -> None:
    required = [
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "MAIL_FROM",
        "MAIL_TO",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ["MAIL_FROM"]
    mail_to = [mail.strip() for mail in os.environ["MAIL_TO"].split(",") if mail.strip()]
    use_tls = os.environ.get("SMTP_USE_TLS", "false").lower() == "true"

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = mail_from
    message["To"] = ", ".join(mail_to)
    message.attach(MIMEText(markdown_content, "plain", "utf-8"))
    message.attach(MIMEText(markdown_to_html(markdown_content), "html", "utf-8"))

    if use_tls:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(mail_from, mail_to, message.as_string())
    else:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(username, password)
            server.sendmail(mail_from, mail_to, message.as_string())


def main() -> None:
    today = shanghai_now()
    grouped = collect_news()
    report = build_report(grouped, today)
    save_report(report, today)
    subject = f"中国金融市场晨报 | {today.strftime('%Y-%m-%d')}"
    send_email(subject, report)
    print(subject)


if __name__ == "__main__":
    main()
