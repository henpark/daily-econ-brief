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
# GEMINI_MODEL 환경변수로 직접 지정하면 그것만 쓴다.
MODEL_CANDIDATES = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.5-flash,gemini-3.6-flash,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash-lite",
    ).split(",")
    if m.strip()
]


class QuotaExceeded(RuntimeError):
    pass


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


def _try_once(model: str, system: str, prompt: str) -> str:
    """Interactions → generateContent 순서로 시도."""
    try:
        data = _post(
            "interactions",
            {
                "model": model,
                "input": f"{system}\n\n---\n\n{prompt}",
                "tools": [{"type": "google_search"}],
            },
        )
        out = _extract_interactions(data)
        if out:
            return out
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise QuotaExceeded(e.read().decode("utf-8", "replace")[:400]) from e
        if e.code not in (400, 404):
            raise
        # 400/404면 이 API 형태를 안 받는 것 → 폴백

    data = _post(
        f"models/{model}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16000},
        },
    )
    return _extract_generate(data)


def ask(system: str, prompt: str, retries: int = 3) -> str:
    """모델 후보를 돌면서 응답을 받아온다. 결제수단 미등록 시 429는 '한도 초과'이지 과금이 아니다."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY 없음")

    last_err: Exception | None = None
    for model in MODEL_CANDIDATES:
        for attempt in range(retries):
            try:
                out = _try_once(model, system, prompt)
                if out:
                    print(f"  [{model}] 응답 {len(out)}자")
                    return out
                last_err = RuntimeError(f"{model}: 빈 응답")
            except QuotaExceeded as e:
                print(f"  [{model}] 무료 한도 초과(429). 과금은 발생하지 않았습니다.")
                last_err = e
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
