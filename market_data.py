#!/usr/bin/env python3
"""
시세·뉴스 수집기. 외부 라이브러리 없이 표준 urllib만 쓴다.

핵심 원칙: 숫자는 여기서만 만든다. AI는 숫자를 만지지 못한다.
어떤 항목이 성공하고 실패했는지 전부 로그에 찍는다.

소스 (전부 무료·키 불필요):
  1순위 Yahoo Finance chart API
  2순위 Stooq CSV
  비트코인 백업 CoinGecko
  뉴스   각 언론사 + Google 뉴스 RSS
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TIMEOUT = 20


def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ────────────────────────────── 시세 ──────────────────────────────


@dataclass
class Quote:
    label: str
    symbol: str
    price: float | None = None
    prev: float | None = None
    source: str = ""
    unit: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.price is not None

    @property
    def change_pct(self) -> float | None:
        if self.price is None or not self.prev:
            return None
        return (self.price - self.prev) / self.prev * 100

    def fmt_price(self) -> str:
        if self.price is None:
            return "확인불가"
        p = self.price
        if self.unit == "%":
            return f"{p:.3f}%"
        if abs(p) >= 1000:
            return f"{p:,.0f}"
        if abs(p) >= 10:
            return f"{p:,.2f}"
        return f"{p:,.4f}"

    def fmt_change(self) -> str:
        # 금리는 %가 아니라 bp(베이시스포인트)로 보는 게 상식이다
        if self.unit == "%" and self.price is not None and self.prev:
            bp = (self.price - self.prev) * 100
            arrow = "▲" if bp > 0 else ("▼" if bp < 0 else "―")
            return f"{arrow}{abs(bp):.0f}bp"
        c = self.change_pct
        if c is None:
            return "—"
        arrow = "▲" if c > 0 else ("▼" if c < 0 else "―")
        return f"{arrow}{abs(c):.2f}%"

    def direction(self) -> str:
        """한국식: 상승 up(빨강), 하락 down(파랑)."""
        c = self.change_pct
        if c is None:
            return "flat"
        return "up" if c > 0 else ("down" if c < 0 else "flat")


# (표시명, 야후심볼, stooq심볼, 단위)
INDEX_SPECS = [
    ("S&P 500", "^GSPC", "^spx", ""),
    ("나스닥", "^IXIC", "^ndq", ""),
    ("코스피", "^KS11", "^kospi", ""),
    ("코스닥", "^KQ11", "^kosdaq", ""),
    ("미 10년물 금리", "^TNX", "10usy.b", "%"),
    ("달러지수(DXY)", "DX-Y.NYB", "^dxy", ""),
    ("원/달러", "KRW=X", "usdkrw", ""),
    ("WTI", "CL=F", "cl.f", ""),
    ("브렌트유", "BZ=F", "cb.f", ""),
    ("금", "GC=F", "gc.f", ""),
    ("비트코인", "BTC-USD", "btcusd", ""),
]

# AI 공급망 + 관심 종목
STOCK_SPECS = [
    ("NVIDIA", "NVDA"),
    ("AMD", "AMD"),
    ("Broadcom", "AVGO"),
    ("TSMC", "TSM"),
    ("ASML", "ASML"),
    ("Micron", "MU"),
    ("Astera Labs", "ALAB"),
    ("Credo", "CRDO"),
    ("Marvell", "MRVL"),
    ("Vertiv", "VRT"),
    ("Constellation Energy", "CEG"),
    ("삼성전자", "005930.KS"),
    ("SK하이닉스", "000660.KS"),
    ("한미반도체", "042700.KS"),
    ("두산에너빌리티", "034020.KS"),
    ("HD현대일렉트릭", "267260.KS"),
]


def _yahoo(symbol: str) -> tuple[float, float] | None:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range=5d&interval=1d"
    )
    data = json.loads(_get(url).decode("utf-8"))
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError("빈 응답")
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        raise ValueError("regularMarketPrice 없음")
    return float(price), float(prev if prev else price)


def _stooq(symbol: str) -> tuple[float, float] | None:
    url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol)}&f=sd2t2ohlcv&h&e=csv"
    text = _get(url).decode("utf-8", "replace").strip().splitlines()
    if len(text) < 2:
        raise ValueError("빈 CSV")
    cols = text[0].split(",")
    vals = text[1].split(",")
    row = dict(zip(cols, vals))
    close, open_ = row.get("Close"), row.get("Open")
    if not close or close == "N/D":
        raise ValueError("종가 없음")
    return float(close), float(open_) if open_ and open_ != "N/D" else float(close)


def _coingecko() -> tuple[float, float]:
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
    )
    d = json.loads(_get(url).decode("utf-8"))["bitcoin"]
    price = float(d["usd"])
    chg = float(d.get("usd_24h_change") or 0)
    return price, price / (1 + chg / 100)


def fetch_quote(label: str, yahoo_sym: str, stooq_sym: str = "", unit: str = "") -> Quote:
    q = Quote(label=label, symbol=yahoo_sym, unit=unit)
    for name, fn in (("yahoo", lambda: _yahoo(yahoo_sym)),
                     ("stooq", (lambda: _stooq(stooq_sym)) if stooq_sym else None),
                     ("coingecko", _coingecko if yahoo_sym == "BTC-USD" else None)):
        if fn is None:
            continue
        try:
            price, prev = fn()
            q.price, q.prev, q.source = price, prev, name
            print(f"    ✅ {label:16s} {q.fmt_price():>12s} {q.fmt_change():>8s}  ({name})")
            return q
        except Exception as e:
            q.error = f"{name}: {str(e)[:60]}"
    print(f"    ❌ {label:16s} 확인불가  ({q.error})")
    return q


def fetch_all_quotes() -> tuple[list[Quote], list[Quote]]:
    print("  [시세] 지수·상품")
    indices = [fetch_quote(l, y, s, u) for l, y, s, u in INDEX_SPECS]
    print("  [시세] 개별 종목")
    stocks = [fetch_quote(l, y) for l, y in STOCK_SPECS]
    return indices, stocks


# ────────────────────────────── 뉴스 ──────────────────────────────


@dataclass
class Article:
    title: str
    source: str
    published: str = ""
    link: str = ""


RSS_FEEDS = [
    ("한국경제", "https://www.hankyung.com/feed/economy"),
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
    ("CNBC 경제", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("CNBC 시장", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
]

GOOGLE_NEWS_QUERIES = [
    ("반도체", "ko"),
    ("코스피 증시", "ko"),
    ("한국은행 금리", "ko"),
    ("AI 데이터센터 전력", "ko"),
    ("Fed interest rate", "en"),
    ("AI capex hyperscaler", "en"),
    ("semiconductor earnings", "en"),
]


def _parse_rss(xml_bytes: bytes, source: str, limit: int = 8) -> list[Article]:
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry"
    )
    out = []
    for it in items[:limit]:
        def txt(tag: str) -> str:
            el = it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        title = txt("title") or txt("{http://www.w3.org/2005/Atom}title")
        if not title:
            continue
        title = re.sub(r"<[^>]+>", "", title)
        out.append(
            Article(
                title=title,
                source=source,
                published=txt("pubDate") or txt("{http://www.w3.org/2005/Atom}updated"),
                link=txt("link"),
            )
        )
    return out


def fetch_news() -> list[Article]:
    print("  [뉴스] RSS 수집")
    articles: list[Article] = []
    for name, url in RSS_FEEDS:
        try:
            got = _parse_rss(_get(url), name)
            articles.extend(got)
            print(f"    ✅ {name:14s} {len(got)}건")
        except Exception as e:
            print(f"    ❌ {name:14s} {str(e)[:60]}")

    for query, lang in GOOGLE_NEWS_QUERIES:
        loc = "hl=ko&gl=KR&ceid=KR:ko" if lang == "ko" else "hl=en-US&gl=US&ceid=US:en"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&{loc}"
        try:
            got = _parse_rss(_get(url), f"Google뉴스·{query}", limit=6)
            articles.extend(got)
            print(f"    ✅ Google뉴스 '{query}' {len(got)}건")
        except Exception as e:
            print(f"    ❌ Google뉴스 '{query}' {str(e)[:60]}")

    # 제목 중복 제거
    seen, uniq = set(), []
    for a in articles:
        key = a.title[:40]
        if key not in seen:
            seen.add(key)
            uniq.append(a)
    print(f"  [뉴스] 총 {len(uniq)}건 (중복 제거 후)")
    return uniq


# ────────────────────────────── 묶기 ──────────────────────────────


@dataclass
class MarketSnapshot:
    indices: list[Quote] = field(default_factory=list)
    stocks: list[Quote] = field(default_factory=list)
    news: list[Article] = field(default_factory=list)

    @property
    def failed(self) -> list[str]:
        return [q.label for q in self.indices + self.stocks if not q.ok]

    def as_text(self) -> str:
        """AI에게 넘길 사실 자료. 여기 없는 숫자는 AI가 쓰면 안 된다."""
        lines = ["### 실제 시세 (이 숫자만 사용할 것)", "", "[지수·상품]"]
        for q in self.indices:
            lines.append(
                f"- {q.label}: {q.fmt_price()} ({q.fmt_change()})"
                if q.ok
                else f"- {q.label}: 확인불가"
            )
        lines += ["", "[개별 종목]"]
        for q in self.stocks:
            lines.append(
                f"- {q.label}({q.symbol}): {q.fmt_price()} ({q.fmt_change()})"
                if q.ok
                else f"- {q.label}({q.symbol}): 확인불가"
            )
        lines += ["", "### 최근 뉴스 헤드라인 (이 목록 안에서만 인용할 것)", ""]
        for i, a in enumerate(self.news[:70], 1):
            lines.append(f"{i}. [{a.source}] {a.title}")
        return "\n".join(lines)


def collect() -> MarketSnapshot:
    indices, stocks = fetch_all_quotes()
    news = fetch_news()
    snap = MarketSnapshot(indices=indices, stocks=stocks, news=news)
    ok = sum(1 for q in indices + stocks if q.ok)
    total = len(indices) + len(stocks)
    print(f"  [요약] 시세 {ok}/{total} 성공, 뉴스 {len(news)}건")
    if snap.failed:
        print(f"  [요약] 확인불가: {', '.join(snap.failed)}")
    return snap


if __name__ == "__main__":
    collect()
