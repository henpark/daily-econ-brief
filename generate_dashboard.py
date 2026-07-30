#!/usr/bin/env python3
"""
Daily Economic Dashboard 생성기.

구조가 바뀌었다. 숫자와 해설의 책임을 분리한다.
  1) market_data.py 가 실제 시세·뉴스를 가져온다.        ← 숫자는 여기서만 나온다
  2) Gemini는 그 자료를 받아 '해설'만 쓴다.               ← 숫자를 만들 수 없다
  3) 2패스로 자기 글을 자료와 대조해 근거 없는 서술을 지운다.
  4) 1번 섹션 표와 카톡 요약의 숫자는 파이썬이 직접 렌더링한다.

산출물:
  out/dashboard.md  out/index.html  out/kakao_summary.txt
"""
import datetime as dt
import pathlib
import re
import sys
import zoneinfo

import gemini_client
from gemini_client import ask
from market_data import MarketSnapshot, collect

KST = zoneinfo.ZoneInfo("Asia/Seoul")
TODAY = dt.datetime.now(KST)
WEEKDAY_KO = "월화수목금토일"[TODAY.weekday()]
DATE_STR = f"{TODAY:%Y년 %m월 %d일} ({WEEKDAY_KO})"
DATE_ISO = f"{TODAY:%Y-%m-%d}"
OUT = pathlib.Path("out")

SYSTEM = f"""너는 한국 개인투자자를 위한 경제 브리핑 애널리스트다.
오늘은 한국시간 기준 {DATE_STR}, 장 시작 전 오전이다.

절대 규칙 (어기면 브리핑이 쓸모없어진다):
- 숫자는 제공된 '실제 시세' 목록에 있는 값만 쓴다. 목록에 없는 수치는 절대 쓰지 않는다.
- 뉴스는 제공된 '헤드라인' 목록 안에서만 인용한다. 목록에 없는 사건을 지어내지 않는다.
- 자료에 근거가 없으면 "확인 불가" 또는 "해당 없음"이라고 적는다. 추측으로 채우지 않는다.
- 너는 실시간 검색을 할 수 없다. 네 기억 속 과거 수치를 오늘 것처럼 쓰면 안 된다.
- 특정 종목 매수/매도를 단정적으로 권하지 않는다. "관점"과 "근거"로 쓴다.
- 한국어. 표 중심으로 스캔하기 쉽게. 이모지는 섹션 헤더에만.

독자 프로필: AI 인프라·반도체·전력·데이터센터·원전에 집중 투자. 미국장과 한국장을 함께 본다.
재무건전성(높은 마진, 낮은 부채, 높은 자본수익률)을 중시하되 초기 성장주도 본다."""

DRAFT_PROMPT = """아래 자료만 근거로 오늘자 브리핑의 2~10번 섹션을 작성해라.
1번 섹션(시장 스냅샷 표)은 프로그램이 이미 만들었으니 쓰지 마라.

{data}

---

작성할 섹션:

## 2. 🇺🇸 미국 경제 뉴스 TOP 5
헤드라인 목록에서 중요한 것 5개를 골라라. 각각:
**핵심** / **왜 중요한가** / **수혜** / **피해**
수혜·피해는 업종 또는 기업명으로 구체적으로.

## 3. 🇰🇷 한국 경제 뉴스 TOP 5
같은 형식.

## 4. 🤖 AI 공급망 점검
제공된 개별 종목 시세와 헤드라인을 근거로 표를 만들어라.
열: 기업 | 전일 등락 | 오늘의 포인트
움직임이나 뉴스가 없는 곳은 "특이사항 없음"이라고 적어라.

## 5. 📈 오늘 꼭 봐야 하는 종목
미국 5개 + 한국 5개. 표로. 열: 종목 | 등락 | 주목 이유(한 줄)
반드시 제공된 시세 목록에 있는 종목 중에서 골라라.

## 6. 📅 오늘의 경제 일정
헤드라인에서 일정 관련 언급을 추려라.
**확실하지 않은 일정은 적지 마라.** 근거가 없으면 "헤드라인에서 확인된 일정 없음"이라고 적어라.

## 7. 🔍 관심 산업
AI·반도체·전력·데이터센터·원전. 표로. 열: 산업 | 중요도 | 코멘트
중요도는 ⭐~⭐⭐⭐. 오늘 자료에 근거가 있는 산업만 별을 높게 줘라.

## 8. 💡 오늘의 투자 인사이트
오늘 자료를 관통하는 핵심 메시지 1개. 3~4문장.

## 9. 🟢 오늘의 투자 행동
**매수 관점** / **관망 포인트** / **오늘의 리스크** 세 덩어리.

## 10. 🔭 투자자 관전포인트
앞으로 지켜볼 것들. AI 캐펙스 가이던스, 포트폴리오 집중도, 금리 경로,
물가·환율, 유가·지정학, 리스크오프 신호 등. 관찰 위주로, 권유하지 말 것.

## 11. 📌 오늘의 한 줄 요약
하루를 1문장으로.

마크다운만 출력해라. 서론 없이 바로 `## 2.` 로 시작해라."""

VERIFY_PROMPT = """아래는 방금 네가 쓴 브리핑 초안과, 그 근거가 된 원본 자료다.
초안을 자료와 한 줄씩 대조해서 검증해라.

1. 초안에 나온 모든 수치가 원본 자료에 실제로 있는 값인가? 없으면 지우고 "확인 불가"로 바꿔라.
2. 초안에 나온 모든 사건·뉴스가 헤드라인 목록에 실제로 있는가? 없으면 그 항목을 통째로 빼라.
3. "~때문에 올랐다" 같은 인과 서술이 헤드라인으로 뒷받침되는가? 아니면 단정을 빼고 "~로 보인다" 수준으로 낮춰라.
4. 오늘 일정이 헤드라인에 근거가 있는가? 없으면 지워라.

=== 원본 자료 ===
{data}

=== 초안 ===
{draft}

=== 출력 형식 ===
아래 두 블록을 정확히 이 형식으로만 출력해라.

<<<BODY>>>
(검증·수정을 마친 2~11번 섹션 전문.
 맨 끝에 "## 🔎 팩트체크 노트" 섹션을 붙여서 무엇을 고쳤는지, 무엇을 근거 부족으로 뺐는지 3~6줄로 적어라.)
<<<END>>>

<<<KAKAO_NEWS>>>
(카카오톡 2번째 메시지. **공백 포함 180자를 절대 넘기지 마라.**
 표나 마크다운 기호를 쓰지 마라. 폰에서 그냥 읽히는 줄글이어야 한다.
 형식:
 1줄 = 📰 오늘의 뉴스 핵심
 2~3줄 = 🇺🇸 로 시작, 미국 뉴스 중 가장 중요한 것 2건을 각 한 줄로
 4~5줄 = 🇰🇷 로 시작, 한국 뉴스 중 가장 중요한 것 2건을 각 한 줄로
 각 줄은 35자 이내. 회사명·업종을 구체적으로 넣어라.)
<<<END>>>

<<<KAKAO_ACTION>>>
(카카오톡 3번째 메시지. **공백 포함 170자를 절대 넘기지 마라.**
 표나 마크다운 기호를 쓰지 마라.
 형식:
 1줄 = 💡 오늘의 한 줄 (오늘을 관통하는 메시지, 40자 이내)
 2줄 = 🟢 매수 관점: (한 줄, 40자 이내)
 3줄 = 🟡 관망: (한 줄, 40자 이내)
 4줄 = ⚠️ 리스크: (한 줄, 40자 이내))
<<<END>>>"""


def extract(tag: str, blob: str) -> str:
    m = re.search(rf"<<<{tag}>>>(.*?)<<<END>>>", blob, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(rf"<<<{tag}>>>(.*)", blob, re.S)
    return m.group(1).split("<<<")[0].strip() if m else ""


# ─────────────────── 파이썬이 직접 만드는 부분 (숫자 담당) ───────────────────


def render_snapshot_md(snap: MarketSnapshot) -> str:
    rows = ["| 지표 | 현재 | 전일 대비 |", "|---|---:|---:|"]
    for q in snap.indices:
        rows.append(f"| {q.label} | {q.fmt_price()} | {q.fmt_change()} |")
    return "## 1. 🌎 한눈에 보는 시장\n\n" + "\n".join(rows) + "\n"


KAKAO_LIMIT = 188  # 카카오 텍스트 템플릿 한도는 200자. 여유 두고 188자.

# 1번 메시지에 넣을 지표와 짧은 표시명 (긴 이름은 폰에서 줄이 넘친다)
SNAPSHOT_ROWS = [
    ("S&P500", "S&P 500"),
    ("나스닥", "나스닥"),
    ("코스피", "코스피"),
    ("코스닥", "코스닥"),
    ("美10년", "미 10년물 금리"),
    ("환율", "원/달러"),
    ("WTI", "WTI"),
    ("금", "금"),
    ("BTC", "비토코인"),
]


def build_kakao_snapshot(snap: MarketSnapshot) -> str:
    """1번 메시지. 숫자는 전부 파이썬이 만든다. AI가 손댈 수 없다."""
    by_label = {q.label: q for q in snap.indices}
    head = f"📊 {TODAY.month}/{TODAY.day}({WEEKDAY_KO}) 시장 스냅샷"
    lines = []
    for short, label in SNAPSHOT_ROWS:
        q = by_label.get(label if label != "비토코인" else "비트코인")
        if q is None or not q.ok:
            continue
        lines.append(f"{short} {q.fmt_price()} {q.fmt_change()}")

    if not lines:
        return f"{head}\n시세를 가져오지 못했습니다. 실행 로그를 확인하세요."

    # 한도를 넘으면 뒤에서부터 줄을 덜어낸다
    while lines and len("\n".join([head] + lines)) > KAKAO_LIMIT:
        lines.pop()
    return "\n".join([head] + lines)


def clean_kakao(text: str, limit: int = KAKAO_LIMIT) -> str:
    """AI가 뱉은 메시지에서 마크다운 기호를 걷어내고 길이를 맞춘다."""
    text = re.sub(r"[*_`#|]+", "", text).strip()
    text = re.sub(r"\n{2,}", "\n", text)
    if len(text) <= limit:
        return text
    # 줄 단위로 잘라서 자연스럽게 끝나게 한다
    out: list[str] = []
    for line in text.split("\n"):
        if len("\n".join(out + [line])) > limit:
            break
        out.append(line)
    return "\n".join(out) if out else text[: limit - 1] + "…"


# ─────────────────────────────── HTML ───────────────────────────────

CSS = """
:root{--bg:#0d1424;--card:#141d33;--line:#243352;--tx:#e8edf7;--dim:#8fa0c0;
      --up:#ff4d5e;--down:#3d8bff;--acc:#ffcc4d}
*{box-sizing:border-box}
body{margin:0;padding:18px 14px 70px;background:var(--bg);color:var(--tx);
     font:15px/1.7 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
     max-width:840px;margin-inline:auto}
h1{font-size:1.4rem;margin:.2em 0 .1em}
h2{font-size:1.12rem;margin:2em 0 .6em;padding-bottom:.35em;border-bottom:1px solid var(--line)}
h3{font-size:1rem;margin:1.4em 0 .4em;color:var(--acc)}
.sub{color:var(--dim);font-size:.85rem;margin-bottom:1.4em}
table{width:100%;border-collapse:collapse;margin:.9em 0;font-size:.88rem;
      display:block;overflow-x:auto;white-space:nowrap}
th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left}
th{color:var(--dim);font-weight:600;background:#0000001a}
td:nth-child(n+2){text-align:right}
.up{color:var(--up);font-weight:600}
.down{color:var(--down);font-weight:600}
strong{color:var(--acc)}
blockquote{border-left:3px solid var(--acc);margin:1em 0;padding:.4em 0 .4em 1em;
           color:var(--dim);background:#ffffff08}
ul,ol{padding-left:1.2em}
code{background:#ffffff12;padding:1px 5px;border-radius:4px;font-size:.9em}
a{color:#7fb0ff}
footer{margin-top:3.5em;padding-top:1.2em;border-top:1px solid var(--line);
       color:var(--dim);font-size:.8rem}
"""


def colorize(html: str) -> str:
    """▲는 빨강, ▼는 파랑 (한국식)."""
    html = re.sub(r"(▲[\d.,]+\s*(?:%|bp)?)", r'<span class="up">\1</span>', html)
    html = re.sub(r"(▼[\d.,]+\s*(?:%|bp)?)", r'<span class="down">\1</span>', html)
    return html


def to_html(md: str, snap: MarketSnapshot) -> str:
    try:
        import markdown

        body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    except ImportError:
        body = "<pre>" + md.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    body = colorize(body)
    ok = sum(1 for q in snap.indices + snap.stocks if q.ok)
    total = len(snap.indices) + len(snap.stocks)
    note = f"시세 {ok}/{total}개 수집 성공 · 뉴스 {len(snap.news)}건 분석"
    if snap.failed:
        note += f" · 확인불가: {', '.join(snap.failed)}"
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Daily Economic Dashboard {DATE_ISO}</title>
<style>{CSS}</style></head><body>
<h1>📊 Daily Economic Dashboard</h1>
<div class="sub">{DATE_STR} · {TODAY:%H:%M} KST</div>
{body}
<footer>
{note}<br>
시세: Yahoo Finance / Stooq / CoinGecko · 뉴스: 각 언론사 RSS<br>
숫자는 프로그램이 직접 수집했고, 해설은 AI가 작성한 뒤 원본 자료와 대조했습니다.<br>
투자 판단과 그 결과의 책임은 본인에게 있습니다.
</footer></body></html>"""


# ─────────────────────────────── main ───────────────────────────────


def main() -> None:
    OUT.mkdir(exist_ok=True)

    print("STEP 1 · 실제 데이터 수집")
    snap = collect()
    data_text = snap.as_text()
    (OUT / "raw_data.txt").write_text(data_text, encoding="utf-8")

    if not any(q.ok for q in snap.indices):
        print("⚠️ 시세를 하나도 못 가져왔습니다. 데이터 소스를 점검하세요.")

    print("\nSTEP 2 · AI 해설 작성")
    draft = ask(SYSTEM, DRAFT_PROMPT.format(data=data_text))
    (OUT / "draft.md").write_text(draft, encoding="utf-8")

    print("\nSTEP 3 · 자료 대조 검증")
    try:
        checked = ask(SYSTEM, VERIFY_PROMPT.format(data=data_text, draft=draft))
    except Exception as e:
        print(f"  검증 실패({str(e)[:80]}) → 초안 그대로 사용")
        checked = ""

    verified = extract("BODY", checked)
    body = verified or draft

    dashboard = render_snapshot_md(snap) + "\n" + body
    if not verified:
        dashboard += "\n\n> ⚠️ 검증 단계가 실패해 초안 그대로 발행됐습니다. 해설 부분을 주의해서 보세요."
    if gemini_client.SEARCH_DISABLED:
        dashboard += (
            "\n\n> ℹ️ AI는 실시간 검색 없이 위 수집 데이터만 보고 해설을 작성했습니다."
            " 숫자는 실제 시세이며, 해설은 그 범위 안에서만 쓰였습니다."
        )
    if snap.failed:
        dashboard += f"\n\n> ⚠️ 다음 항목은 시세를 못 가져왔습니다: {', '.join(snap.failed)}"

    # ── 카톡 3통 만들기 ──
    msg1 = build_kakao_snapshot(snap)

    news = clean_kakao(extract("KAKAO_NEWS", checked))
    if not news:
        news = "📰 오늘의 뉴스 핵심\n뉴스 요약 생성에 실패했습니다. 전문 링크를 확인하세요."

    action = clean_kakao(extract("KAKAO_ACTION", checked))
    if not action:
        action = "💡 오늘의 한 줄\n요약 생성에 실패했습니다. 전문 링크를 확인하세요."

    (OUT / "dashboard.md").write_text(dashboard, encoding="utf-8")
    (OUT / "index.html").write_text(to_html(dashboard, snap), encoding="utf-8")
    (OUT / f"{DATE_ISO}.html").write_text(to_html(dashboard, snap), encoding="utf-8")

    for i, msg in enumerate((msg1, news, action), 1):
        (OUT / f"kakao_{i}.txt").write_text(msg, encoding="utf-8")
        print(f"\n─── 카톡 {i}/3 ({len(msg)}자) ───\n{msg}")

    # 예전 파일명도 남겨둔다 (워크플로가 아직 옛 인자를 쓰는 경우 대비)
    (OUT / "kakao_summary.txt").write_text(msg1, encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"치명적 오류: {e}", file=sys.stderr)
        sys.exit(1)
