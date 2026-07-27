#!/usr/bin/env python3
"""
카카오 인증 코드(code) → 리프레시 토큰 교환기.
GitHub Actions에서 돌리는 용도라 토큰을 화면에 절대 출력하지 않는다.
대신 GitHub Secret(KAKAO_REFRESH_TOKEN)에 바로 저장한다.

환경변수: KAKAO_REST_API_KEY, KAKAO_CODE, GH_PAT, GITHUB_REPOSITORY
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
CODE = os.environ.get("KAKAO_CODE", "").strip()
SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
REDIRECT = os.environ.get("KAKAO_REDIRECT_URI", "https://example.com/oauth").strip()
PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()

if not KEY:
    sys.exit("❌ KAKAO_REST_API_KEY Secret이 없습니다. 3단계를 다시 확인하세요.")
if not CODE:
    sys.exit("❌ code 값이 비었습니다.")
if not PAT:
    sys.exit("❌ GH_PAT Secret이 없습니다. 먼저 GH_PAT을 등록하세요.")

# 사용자가 주소 전체를 붙여넣은 경우까지 구제
if "code=" in CODE:
    CODE = urllib.parse.parse_qs(urllib.parse.urlparse(CODE).query).get("code", [CODE])[0]

# --- 진단 정보. 비밀값은 앞 4자리만 찍는다 ---
print("=" * 50)
print("진단 정보")
print(f"  REST API 키   : {KEY[:4]}...{KEY[-2:]}  (길이 {len(KEY)})")
print(f"  클라이언트 시크릿: {'있음 ' + SECRET[:4] + '...' if SECRET else '❗️없음 — Secret 미등록'}")
print(f"  Redirect URI  : {REDIRECT}")
print(f"  code          : {CODE[:6]}... (길이 {len(CODE)})")
print("=" * 50)
if not SECRET:
    print("⚠️  클라이언트 시크릿이 없습니다. 카카오는 이제 이걸 필수로 요구합니다.")
    print("   KAKAO_CLIENT_SECRET Secret을 등록하지 않으면 KOE010이 납니다.")
if len(KEY) != 32:
    print(f"⚠️  REST API 키 길이가 {len(KEY)}입니다. 보통 32자입니다. 앞뒤 공백이나 다른 키가 아닌지 확인하세요.")

payload = {
    "grant_type": "authorization_code",
    "client_id": KEY,
    "redirect_uri": REDIRECT,
    "code": CODE,
}
if SECRET:
    payload["client_secret"] = SECRET

req = urllib.request.Request(
    "https://kauth.kakao.com/oauth/token",
    data=urllib.parse.urlencode(payload).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "replace")
    print(f"❌ 카카오 응답 오류 {e.code}: {body}")
    if "invalid_grant" in body:
        print("\n→ code는 한 번 쓰면 끝이고 몇 분 지나면 만료됩니다.")
        print("  주소창에서 code를 새로 받아서 다시 실행하세요.")
    if "invalid_client" in body:
        print("\n→ REST API 키가 틀렸거나, Redirect URI가 카카오에 등록한 값과 다릅니다.")
    sys.exit(1)

refresh = data.get("refresh_token")
scope = data.get("scope") or ""

if not refresh:
    sys.exit(f"❌ refresh_token이 안 왔습니다. 응답 키: {list(data)}")

# 토큰은 절대 출력하지 않는다. 로그가 공개될 수 있다.
print("::add-mask::" + refresh)

subprocess.run(
    ["gh", "secret", "set", "KAKAO_REFRESH_TOKEN", "--repo", REPO, "--body", refresh],
    check=True,
    env={**os.environ, "GH_TOKEN": PAT},
)

print("✅ KAKAO_REFRESH_TOKEN Secret 저장 완료.")
print(f"   받은 권한(scope): {scope}")

if "talk_message" not in scope:
    print("\n⚠️  scope에 talk_message가 없습니다. 메시지 전송이 안 됩니다.")
    print("   카카오 개발자 콘솔 → 카카오 로그인 → 동의항목 →")
    print("   '카카오톡 메시지 전송'을 [이용 중 동의]로 바꾸고 처음부터 다시 하세요.")
    sys.exit(1)

print("\n다음: Actions 탭에서 'Daily Economic Dashboard' → Run workflow 를 눌러보세요.")
