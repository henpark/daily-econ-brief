#!/usr/bin/env python3
"""
Daily Economic Dashboard 생성기 (Gemini 무료 티어).

2단계로 돈다.
  PASS 1 (리서치+작성) : Google 검색 그라운딩으로 최신 데이터를 모아 10개 섹션 작성
  PASS 2 (팩트체크)    : 1번 결과의 모든 수치/날짜/고유명사를 재검색해 검증하고 수정

산출물:
  out/dashboard.md        - 대시보드 전문
  out/index.html          - 웹 발행용
  out/kakao_summary.txt   - 카카오톡용 190자 요약
"""
import datetime as dt
import os
import pathlib
import re
import sys
import zoneinfo

from gemini_client import ask

KST = zoneinfo.ZoneInfo("Asia/Seoul")
TODAY = dt.datetime.now(KST)
WEEKDAY_KO = "월화수목금토일"[TODAY.weekday()]
DATE_STR = f"{TODAY:%Y년 %m월 %d일} ({WEEKDAY_KO})"
DATE_ISO = f"{TODAY:%Y-%m-%d}"
OUT = pathlib.Path("out")

SYSTEM = f"""너는 한국 개인투자자를 위한 경제 브리핑 애널리스트다.
오늘은 한국시간 기준 {DATE_STR}, 장 시작 전 오전이다.

절대 규칙:
- 모든 수치는 Google 검색으로 확인한 실제 데이터만 쓴다. 기억이나 추정으로 숫자를 쓰지 않는다.
- 확인 못 한 항목은 숫자를 지어내지 말고 "확인 불가"라고 적는다. 틀린 숫자보다 이게 낫다.
- 각 수치 옆에 기준 시점을 표기한다. 미국장은 전일 종가, 한국장은 전 거래일 종가 기준.
- 뉴스는 최근 24시간 이내 것만 쓴다. 오래된 뉴스를 새 뉴스처럼 쓰지 않는다.
- 특정 종목 매수/매도를 단정적으로 권하지 않는다. "관점"과 "근거"로 쓴다.
- 한국어로 쓴다. 이모지는 섹션 헤더에만 쓴다."""

PASS1 = """아래 10개 섹션으로 오늘자 Daily Economic Dashboard를 작성해라.
먼저 검색으로 필요한 데이터를 전부 수집한 다음 작성해라.

## 1. 🌎 한눈에 보는 시장
S&P500, Nasdaq, KOSPI, KOSDAQ, 미국 10년물/2년물 국채금리, 달러지수(DXY), 원/달러 환율,
WTI, 브렌트유, 금, 비트코인. 각각 종가/현재가 + 전일 대비 등락률. 마지막에 한 줄 요약.
마크다운 표로 정리.

## 2. 🇺🇸 미국 경제 뉴스 TOP 5
각각: 핵심 내용 / 왜 중요한가 / 수혜 업종·기업 / 피해 업종·기업

## 3. 🇰🇷 한국 경제 뉴스 TOP 5
같은 형식.

## 4. 🤖 AI 공급망 뉴스
NVIDIA, AMD, Broadcom, TSMC, ASML, 삼성전자, SK하이닉스, 기타 AI 인프라 기업.
움직임이 있는 곳만 쓰고, 없으면 "특이사항 없음"이라고 적어라.

## 5. 📈 오늘 꼭 봐야 하는 종목
미국 5개 + 한국 5개. 각각 "오늘 주목해야 하는 이유" 한 줄.

## 6. 📅 오늘의 경제 일정
Fed 인사 발언, CPI/PPI, FOMC, 주요 기업 실적발표, 경제지표, 한국 일정.
한국시간 기준 시각을 병기해라.

## 7. 🔍 관심 산업
AI, 반도체, 전력·전력기기, 데이터센터, 원전 등. 각각 오늘의 중요도를 ⭐~⭐⭐⭐로.

## 8. 💡 오늘의 투자 인사이트
오늘 시장을 관통하는 핵심 메시지 딱 1개. 3~4문장.

## 9. 🟢 오늘의 투자 행동
매수 관점 / 관망 포인트 / 오늘의 리스크

## 10. 📌 오늘의 한 줄 요약
하루를 1문장으로.

마크다운으로만 출력해라. 서론이나 "알겠습니다" 같은 말 없이
바로 `# 📊 Daily Economic Dashboard` 로 시작해라."""

PASS2_TEMPLATE = """아래는 방금 작성된 오늘자 경제 대시보드 초안이다. 이걸 팩트체크해라.

1. 등장하는 모든 숫자(지수, 등락률, 금리, 유가, 환율, 시각, 날짜)를 검색으로 재확인해라.
   특히 지수 레벨과 등락률이 서로 모순되지 않는지 본다.
2. 회사명·인물명·직책·정책명이 정확한지 확인해라.
3. "오늘 일정"이 실제로 오늘(한국시간)인지 확인해라. 하루 어긋난 일정이 제일 흔한 실수다.
4. 근거 없는 인과관계 서술("~때문에 올랐다")이 실제 보도로 뒷받침되는지 본다.
5. 검색으로 확인이 안 되는 수치는 지우고 "확인 불가"로 바꿔라.

--- 초안 시작 ---
{draft}
--- 초안 끝 ---

그 다음 아래 두 블록을 정확히 이 형식으로 출력해라. 다른 말은 붙이지 마라.

<<<DASHBOARD>>>
(수정 완료된 대시보드 전문. 맨 끝에 "## 🔎 팩트체크 노트" 섹션을 추가해서
 무엇을 고쳤는지, 확인 불가로 남긴 항목이 뭔지 3~6줄로 적어라.
 그 아래 "## 📚 출처" 섹션에 참고한 주요 URL을 목록으로 적어라.)
<<<END>>>

<<<KAKAO>>>
(카카오톡 알림용. 공백 포함 185자를 절대 넘기지 마라. 형식:
 1줄 = 📊 M/D 경제 브리핑
 2줄 = 오늘의 한 줄 요약
 3줄 = 핵심 지표 3개를 "코스피 0,000 ▲0.0%" 식으로 압축
 4줄 = ⚠️ 오늘의 리스크 한 조각
 링크는 넣지 마라. 버튼으로 따로 붙는다.)
<<<END>>>"""


def extract(tag: str, blob: str) -> str:
    m = re.search(rf"<<<{tag}>>>(.*?)<<<END>>>", blob, re.S)
    if m:
        return m.group(1).strip()
    # 닫는 태그가 빠진 경우까지 구제
    m = re.search(rf"<<<{tag}>>>(.*)", blob, re.S)
    return m.group(1).split("<<<")[0].strip() if m else ""


def to_html(md: str) -> str:
    try:
        import markdown

        body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    except ImportError:
        body = "<pre>" + md.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Economic Dashboard {DATE_ISO}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ max-width: 820px; margin: 0 auto; padding: 24px 18px 80px;
         font: 16px/1.75 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid currentColor; padding-bottom: .4em; }}
  h2 {{ font-size: 1.25rem; margin-top: 2.2em; }}
  h3 {{ font-size: 1.05rem; margin-top: 1.6em; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; margin: 1em 0; }}
  th, td {{ border: 1px solid #8884; padding: 7px 10px; text-align: left; }}
  th {{ background: #8881; }}
  a {{ word-break: break-all; }}
  footer {{ margin-top: 4em; font-size: .82rem; opacity: .65; }}
</style></head><body>
{body}
<footer>Gemini 자동 생성 · {TODAY:%Y-%m-%d %H:%M} KST · 투자 판단의 책임은 본인에게 있습니다.</footer>
</body></html>"""


def main() -> None:
    OUT.mkdir(exist_ok=True)

    print("PASS 1 · 리서치 + 작성")
    draft = ask(SYSTEM, PASS1)
    (OUT / "draft.md").write_text(draft, encoding="utf-8")

    print("PASS 2 · 팩트체크")
    try:
        checked = ask(SYSTEM, PASS2_TEMPLATE.format(draft=draft))
    except Exception as e:
        print(f"  팩트체크 실패({e}) → 초안 그대로 발행합니다.")
        checked = ""

    verified = extract("DASHBOARD", checked)
    dashboard = verified or draft

    # 카카오 요약은 경고문을 붙이기 "전"의 본문에서 뽑아야 한다.
    kakao = extract("KAKAO", checked)
    if not kakao:
        lines = [l.strip("#>-* ") for l in dashboard.strip().split("\n") if l.strip("#>-*| ")]
        tail = lines[-1] if lines else "오늘의 브리핑"
        kakao = f"📊 {TODAY.month}/{TODAY.day} 경제 브리핑\n{tail[:150]}"

    if not verified:
        dashboard += "\n\n> ⚠️ 팩트체크 단계가 실패해 초안 그대로 발행됐습니다. 수치를 직접 확인하세요."
        kakao = f"{kakao}\n⚠️ 팩트체크 실패 — 수치 직접 확인"

    (OUT / "dashboard.md").write_text(dashboard, encoding="utf-8")
    (OUT / "index.html").write_text(to_html(dashboard), encoding="utf-8")
    (OUT / f"{DATE_ISO}.html").write_text(to_html(dashboard), encoding="utf-8")
    (OUT / "kakao_summary.txt").write_text(kakao[:190], encoding="utf-8")
    print(f"\n카카오 요약 ({len(kakao)}자):\n{kakao}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"치명적 오류: {e}", file=sys.stderr)
        sys.exit(1)
