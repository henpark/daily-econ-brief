#!/usr/bin/env python3
"""
최초 1회만, 내 맥에서 실행하는 스크립트.
카카오 리프레시 토큰을 뽑아낸다. 이후로는 GitHub Actions가 알아서 갱신한다.

사용법:
    export KAKAO_REST_API_KEY="카카오 REST API 키"
    python3 get_refresh_token.py
"""
import os
import sys
import urllib.parse
import urllib.request

REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()  # 사용 안 하면 비워두기
REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI", "https://example.com/oauth").strip()

if not REST_API_KEY:
    sys.exit("KAKAO_REST_API_KEY 환경변수가 없습니다.")

auth_url = (
    "https://kauth.kakao.com/oauth/authorize?"
    + urllib.parse.urlencode(
        {
            "client_id": REST_API_KEY,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "talk_message",
        }
    )
)

print("\n[1] 아래 주소를 브라우저에 붙여넣고 카카오 로그인 + 동의하세요.\n")
print(auth_url)
print(
    "\n[2] 동의하면 하얀 화면(또는 404)으로 넘어갑니다. 주소창의 ?code=XXXXX 값만 복사하세요.\n"
)

code = input("code 값 붙여넣기 > ").strip()
if not code:
    sys.exit("code가 비었습니다.")

payload = {
    "grant_type": "authorization_code",
    "client_id": REST_API_KEY,
    "redirect_uri": REDIRECT_URI,
    "code": code,
}
if CLIENT_SECRET:
    payload["client_secret"] = CLIENT_SECRET

req = urllib.request.Request(
    "https://kauth.kakao.com/oauth/token",
    data=urllib.parse.urlencode(payload).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
)

import json

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

print("\n성공. 아래 값을 GitHub Secret으로 등록하세요.\n")
print("KAKAO_REFRESH_TOKEN =", data["refresh_token"])
print("\n(access_token은 6시간짜리라 저장할 필요 없습니다.)")
print("scope:", data.get("scope"))
if "talk_message" not in (data.get("scope") or ""):
    print("\n경고: scope에 talk_message가 없습니다. 카카오 개발자 콘솔에서")
    print("      [카카오 로그인 > 동의항목 > 카카오톡 메시지 전송]을 켜고 다시 하세요.")
