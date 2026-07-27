#!/usr/bin/env python3
"""
Gemini 무료 티어 클라이언트. 외부 라이브러리 없이 표준 urllib만 쓴다.

구글이 API를 두 갈래로 운영 중이라 둘 다 지원한다.
  1) Interactions API   (신규, 권장)  POST /v1beta/interactions
  2) generateContent API (구형, 안정) POST /v1beta/models/{model}:generateContent
Interactions를 먼저 시도하고 실패하면 generateContent로 자동 폴백한다.

Google 검색 그라운딩(tools: google_search)을 켜서 실시간 데이터를 쓴다.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# 무료 티어에서 쓸 수 있는 모델 후보. 앞에서부터 되는 걸 쓴다.
DEFAULT_MODELS = (
    "gemini-3.5-flash,gemini-3.6-flash,gemini-2.5-flash,"
    "gemini-3.1-flash-lite,gemini-2.5-flash-lite,gemini-2.0-flash"
)

# 주의: GitHub Actions는 정의 안 된 변수를 "빈 문자열"로 넘긴다.
# os.environ.get(키, 기본값)은 이때 기본값이 아니라 빈 문자열을 준다. 그래서 `or`로 한 번 더 거른다.
MODEL_CANDIDATES = [
    m.strip()
    for m in (os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODELS).split(",")
    if m.strip()
]


class QuotaExceeded(RuntimeError):
    pass


# 검색 그라운딩이 막혀서 검색 없이 생성한 경우 True가 된다. 대시보드에 경고를 붙이는 데 쓴다.
SEARCH_DISABLED = False


def _post(path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{BASE}/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_interactions(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    chunks = []
    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                chunks.append(block["text"])
    return "\n".join(chunks).strip()


def _extract_generate(data: dict) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "\n".join(p["text"] for p in parts if "text" in p).strip()


def _try_once(model: str, system: str, prompt: str, use_search: bool = True) -> str:
    """Interactions → generateContent 순서로 시도. use_search=False면 검색 도구를 뺀다."""
    try:
        body = {"model": model, "input": f"{system}\n\n---\n\n{prompt}"}
        if use_search:
            body["tools"] = [{"type": "google_search"}]
        data = _post("interactions", body)
        out = _extract_interactions(data)
        if out:
            return out
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise QuotaExceeded(e.read().decode("utf-8", "replace")[:400]) from e
        if e.code not in (400, 404, 500, 503):
            raise
        # 400/404 = 이 API 형태를 안 받음, 500/503 = 일시 오류 → generateContent로 폴백

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16000},
    }
    if use_search:
        body["tools"] = [{"google_search": {}}]
    try:
        data = _post(f"models/{model}:generateContent", body)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise QuotaExceeded(e.read().decode("utf-8", "replace")[:400]) from e
        raise
    return _extract_generate(data)


def discover_models() -> list[str]:
    """후보가 전부 안 되면 구글에 직접 물어서 쓸 수 있는 flash 계열을 찾는다."""
    try:
        req = urllib.request.Request(
            f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": API_KEY}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  모델 목록 조회 실패: {e}")
        return []

    found = []
    for m in data.get("models", []):
        name = m.get("name", "").replace("models/", "")
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" in methods and "flash" in name and "thinking" not in name:
            found.append(name)
    # 최신 버전이 앞에 오도록 대충 정렬
    found.sort(reverse=True)
    print(f"  자동 탐색으로 찾은 모델: {found[:5]}")
    return found[:5]


def ask(system: str, prompt: str, retries: int = 3) -> str:
    """모델 후보를 돌면서 응답을 받아온다. 결제수단 미등록 시 429는 '한도 초과'이지 과금이 아니다."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY 없음 — GEMINI_API_KEY Secret을 확인하세요")
    if not MODEL_CANDIDATES:
        raise RuntimeError("모델 후보가 비었습니다 (코드 버그)")

    print(f"  시도할 모델: {MODEL_CANDIDATES}")
    candidates = list(MODEL_CANDIDATES)
    discovered = False

    last_err: Exception | None = None
    while candidates:
        model = candidates.pop(0)
        if not candidates and not discovered:
            # 마지막 후보까지 왔는데 아직 자동 탐색을 안 했으면, 실패 대비로 목록을 채워둔다
            discovered = True
            extra = [m for m in discover_models() if m != model]
            candidates.extend(extra)
        for attempt in range(retries):
            try:
                out = _try_once(model, system, prompt)
                if out:
                    print(f"  [{model}] 응답 {len(out)}자")
                    return out
                last_err = RuntimeError(f"{model}: 빈 응답")
            except QuotaExceeded as e:
                print(f"  [{model}] 검색 켠 요청 429. 검색을 빼고 한 번만 더 시도합니다.")
                last_err = e
                try:
                    out = _try_once(model, system, prompt, use_search=False)
                    if out:
                        global SEARCH_DISABLED
                        SEARCH_DISABLED = True
                        print(
                            f"  ⚠️ [{model}] 검색 없이는 성공했습니다.\n"
                            f"     → 즉, 막힌 것은 '모델'이 아니라 'Google 검색 그라운딩'입니다.\n"
                            f"     → 무료 티어에서 검색이 안 되므로 실시간 데이터를 쓸 수 없습니다."
                        )
                        return out
                except QuotaExceeded:
                    print(f"  [{model}] 검색 없이도 429 → 이 모델 자체가 무료 한도 밖입니다.")
                except Exception as e2:
                    print(f"  [{model}] 검색 없이 시도도 실패: {str(e2)[:120]}")
                break  # 같은 모델 재시도해도 소용없음 → 다음 모델
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                print(f"  [{model}] HTTP {e.code}: {detail}")
                last_err = e
                if e.code in (400, 404):
                    break  # 모델 이름이 틀림 → 다음 후보
                time.sleep(5 * (attempt + 1))
            except Exception as e:  # 네트워크 등 일시 오류
                print(f"  [{model}] 오류: {e}")
                last_err = e
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"모든 모델 실패. 마지막 오류: {last_err}")


def list_models() -> None:
    """쓸 수 있는 모델 이름 확인용. python3 gemini_client.py 로 실행."""
    req = urllib.request.Request(
        f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": API_KEY}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for m in data.get("models", []):
        name = m.get("name", "").replace("models/", "")
        if "generateContent" in (m.get("supportedGenerationMethods") or []):
            print(f"{name:40s} {m.get('displayName','')}")


if __name__ == "__main__":
    list_models()
