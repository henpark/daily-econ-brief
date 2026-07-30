#!/usr/bin/env python3
"""
카카오톡 '나에게 보내기'.
1) 리프레시 토큰으로 액세스 토큰 갱신
2) 새 리프레시 토큰이 내려오면 GitHub Secret 자동 업데이트 (GH_PAT 있을 때)
3) 텍스트 템플릿(200자 제한)으로 요약 + 전문 링크 발송

필요 환경변수:
  KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN, DASHBOARD_URL
선택:
  KAKAO_CLIENT_SECRET, GH_PAT, GITHUB_REPOSITORY
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request

REST_API_KEY = os.environ["KAKAO_REST_API_KEY"].strip()
REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"].strip()
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()

MAX_TEXT = 190  # 카카오 텍스트 템플릿 한도는 200자. 여유 두고 190자.


def post_form(url: str, payload: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_access_token() -> tuple[str, str | None]:
    payload = {
        "grant_type": "refresh_token",
        "client_id": REST_API_KEY,
        "refresh_token": REFRESH_TOKEN,
    }
    if CLIENT_SECRET:
        payload["client_secret"] = CLIENT_SECRET
    data = post_form("https://kauth.kakao.com/oauth/token", payload)
    # 리프레시 토큰은 유효기간이 1개월 미만 남았을 때만 새로 내려온다.
    return data["access_token"], data.get("refresh_token")


def rotate_github_secret(new_refresh_token: str) -> None:
    """새 리프레시 토큰을 GitHub Secret에 덮어쓴다. gh CLI 사용(러너에 기본 설치됨)."""
    pat = os.environ.get("GH_PAT", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not pat or not repo:
        print("::warning::리프레시 토큰이 갱신됐지만 GH_PAT이 없어 자동 저장 못 함. "
              "KAKAO_REFRESH_TOKEN Secret을 수동으로 바꾸세요.")
        return
    subprocess.run(
        ["gh", "secret", "set", "KAKAO_REFRESH_TOKEN", "--repo", repo,
         "--body", new_refresh_token],
        check=True,
        env={**os.environ, "GH_TOKEN": pat},
    )
    print("리프레시 토큰 갱신 및 Secret 업데이트 완료.")


def clip(text: str, limit: int = MAX_TEXT) -> str:
    text = " ".join(text.split()) if "\n" not in text else text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def send_memo(access_token: str, text: str, url: str, with_button: bool) -> None:
    template = {
        "object_type": "text",
        "text": clip(text),
        "link": {"web_url": url, "mobile_web_url": url},
    }
    if with_button:
        template["button_title"] = "전문 보기"
    data = post_form(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {"Authorization": f"Bearer {access_token}"},
    )
    if data.get("result_code") != 0:
        raise RuntimeError(f"카카오 전송 실패: {data}")


def collect_messages() -> list[str]:
    """out/kakao_1.txt, kakao_2.txt ... 순서대로 모은다.
    인자로 파일 경로를 직접 주면 그 파일만 보낸다."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        paths = [pathlib.Path(p) for p in sys.argv[1:]]
    else:
        paths = sorted(pathlib.Path("out").glob("kakao_[0-9].txt"))
        if not paths:  # 예전 구조 대비
            paths = [pathlib.Path("out/kakao_summary.txt")]

    msgs = []
    for p in paths:
        if not p.exists():
            print(f"::warning::{p} 없음 — 건너뜁니다")
            continue
        body = p.read_text(encoding="utf-8").strip()
        if body:
            msgs.append(body)
    return msgs


def main() -> None:
    msgs = collect_messages()
    if not msgs:
        sys.exit("보낼 메시지가 없습니다.")

    access_token, new_refresh = refresh_access_token()
    if new_refresh and new_refresh != REFRESH_TOKEN:
        rotate_github_secret(new_refresh)

    url = DASHBOARD_URL or "https://developers.kakao.com"
    sent = 0
    for i, msg in enumerate(msgs, 1):
        last = i == len(msgs)
        try:
            send_memo(access_token, msg, url, with_button=last)
            sent += 1
            print(f"  ✅ {i}/{len(msgs)} 전송 ({len(msg)}자)")
        except Exception as e:
            print(f"  ❌ {i}/{len(msgs)} 실패: {str(e)[:200]}")
        if not last:
            time.sleep(1.5)  # 카톡에 순서대로 쌓이도록 잠깐 쉰다

    print(f"카카오톡 전송 완료: {sent}/{len(msgs)}통")
    if sent == 0:
        sys.exit("전부 실패했습니다.")


if __name__ == "__main__":
    main()
