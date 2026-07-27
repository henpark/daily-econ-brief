# 매일 07:50 카카오톡 경제 대시보드 — 세팅 가이드 (완전 무료)

전체 소요 시간 약 40분. 코딩은 필요 없고 복사·붙여넣기만 하면 됩니다.

## 비용이 0원인 이유

| 구성요소 | 비용 | 근거 |
|---|---|---|
| GitHub Actions | 0원 | 공개 레포는 실행 시간 무제한 무료 |
| GitHub Pages | 0원 | 공개 레포 무료 제공 |
| Gemini API | 0원 | **결제수단을 등록하지 않습니다.** 무료 한도를 넘으면 과금이 아니라 429 오류로 그냥 실패합니다 |
| 카카오 나에게 보내기 API | 0원 | 무료, 검수 불필요 |

**핵심 안전장치:** Google AI Studio에서 결제수단을 등록하지 않으면 구조적으로 과금이 불가능합니다. 한도를 넘으면 그날 브리핑이 안 오거나 팩트체크 단계가 생략될 뿐, 청구서는 오지 않습니다. (검색 그라운딩 무료 한도는 월 수천 건 단위인데 이 작업은 하루 40~60건이라 넉넉합니다.)

## 어떻게 굴러가는가

```
GitHub Actions (07:35 KST 기동)
  └─ generate_dashboard.py
       PASS 1  Gemini + Google 검색 그라운딩으로 최신 데이터 수집 → 10개 섹션 작성
       PASS 2  모든 수치·날짜·고유명사를 재검색해 검증 → 수정 + 팩트체크 노트
  └─ GitHub Pages에 전문 HTML 발행
  └─ 07:50 정각까지 대기
  └─ send_kakao.py → 카카오톡 "나에게 보내기"로 요약 + [전문 보기] 버튼
```

카카오 텍스트 템플릿은 **200자 제한**이라 전문을 카톡에 넣을 수 없습니다. 카톡엔 한 줄 요약 + 핵심 지표 3개 + 리스크만 오고, 나머지는 버튼을 눌러 봅니다.

---

## 1단계 · 카카오 개발자 앱 만들기 (15분)

1. https://developers.kakao.com → 로그인 → **내 애플리케이션 › 애플리케이션 추가하기**
   - 앱 이름: 아무거나 (예: `econ-brief`), 사업자명: 본인 이름
2. **앱 설정 › 플랫폼 › Web 플랫폼 등록** → 사이트 도메인: `https://example.com`
3. **카카오 로그인 › 활성화 설정: ON**
4. **카카오 로그인 › Redirect URI 등록**: `https://example.com/oauth`
5. **카카오 로그인 › 동의항목** → `카카오톡 메시지 전송(talk_message)` → **이용 중 동의**로 설정
6. **앱 키** 탭에서 **REST API 키** 복사 → 메모장에 보관

> "나에게 보내기"는 카카오 검수(심사) 없이 바로 됩니다. 친구에게 보내기만 검수가 필요합니다.

## 2단계 · 리프레시 토큰 뽑기 (5분, 최초 1회만)

맥 터미널에서:

```bash
cd ~/Downloads/daily-econ-kakao
export KAKAO_REST_API_KEY="1단계에서 복사한 REST API 키"
python3 get_refresh_token.py
```

출력된 주소를 브라우저에 붙여넣고 → 카카오 로그인 → 동의 →
주소창이 `https://example.com/oauth?code=XXXXX` 로 바뀌면 `XXXXX` 부분만 복사해 터미널에 붙여넣습니다.
(페이지가 404로 보여도 정상입니다. 주소창만 보면 됩니다.)

출력된 `KAKAO_REFRESH_TOKEN` 값을 보관하세요.

## 3단계 · Gemini API 키 발급 (3분)

1. https://aistudio.google.com/apikey → 구글 로그인 → **Create API key**
2. **결제수단은 절대 등록하지 마세요.** 이게 0원을 보장하는 장치입니다.
3. 키를 복사해 보관

키가 제대로 되는지, 그리고 지금 쓸 수 있는 모델 이름이 뭔지 확인하려면:

```bash
export GEMINI_API_KEY="복사한 키"
python3 gemini_client.py
```

사용 가능한 모델 목록이 뜹니다. 목록에 `gemini-3.5-flash` 같은 Flash 계열이 보이면 그대로 두면 되고, 이름이 다르면 4단계에서 `GEMINI_MODEL` 변수로 지정하세요. (지정 안 하면 스크립트가 후보를 차례로 시도합니다.)

## 4단계 · GitHub 레포 만들기 (10분)

1. GitHub에서 **Public** 레포 생성 (예: `daily-econ-brief`)

   > 공개여야 하는 이유: 무료 플랜에서 GitHub Pages는 공개 레포만 지원하고, Actions 실행 시간도 공개 레포만 무제한입니다. API 키는 Secrets에 암호화 저장되므로 노출되지 않습니다. 다만 **생성된 대시보드 페이지는 누구나 URL로 볼 수 있습니다.** 일반적인 시황 분석이라 문제는 없지만 알고 계세요.

2. 이 폴더의 파일을 그대로 업로드 (`.github/workflows/` 폴더 구조 유지)

3. **Settings › Secrets and variables › Actions › Secrets** 에 추가:

   | 이름 | 값 |
   |---|---|
   | `GEMINI_API_KEY` | 3단계 키 |
   | `KAKAO_REST_API_KEY` | 1단계 REST API 키 |
   | `KAKAO_REFRESH_TOKEN` | 2단계 리프레시 토큰 |
   | `GH_PAT` | (선택) 아래 설명 참고 |

4. 같은 화면의 **Variables** 탭:

   | 이름 | 값 |
   |---|---|
   | `DASHBOARD_URL` | `https://<깃허브아이디>.github.io/daily-econ-brief/` |
   | `GEMINI_MODEL` | (선택) 3단계에서 확인한 모델 이름 |

5. **Settings › Pages** → Source: `Deploy from a branch`, Branch: `main` / `/docs` → Save

### `GH_PAT` 는 왜 필요한가 (선택이지만 권장)

카카오 리프레시 토큰은 2개월짜리인데, **만료 1개월 미만이 남았을 때 갱신 요청을 하면 새 토큰이 같이 내려옵니다.** 매일 돌리니 자동으로 계속 연장되는데, 새로 받은 토큰을 Secret에 다시 써넣어야 합니다.

`GH_PAT` 를 넣어두면 스크립트가 알아서 덮어씁니다. 없으면 갱신 시점에 로그에 경고만 남고 **2단계를 다시 해야 합니다.**

발급: GitHub **Settings › Developer settings › Personal access tokens › Fine-grained tokens** → 이 레포만 선택 → Repository permissions에서 **Secrets: Read and write** → 생성 후 `GH_PAT` Secret으로 등록.

## 5단계 · 테스트

레포의 **Actions › Daily Economic Dashboard › Run workflow** 로 수동 실행.

3~10분 뒤 카카오톡 "나와의 채팅"에 메시지가 옵니다. 실패하면 Actions 로그를 보세요.

| 오류 | 원인 |
|---|---|
| `insufficient scopes` | 1단계 5번(동의항목 talk_message)을 안 켬 |
| `invalid_grant` | 리프레시 토큰이 잘못됨 → 2단계 재실행 |
| `모든 모델 실패 ... HTTP 404` | 모델 이름 문제 → 3단계로 이름 확인 후 `GEMINI_MODEL` 지정 |
| `무료 한도 초과(429)` | 그날 한도 소진. **과금 아님.** 다음날 정상화 |
| Pages 404 | 첫 실행 후 1~2분 대기 |

---

## 알아둘 것

**팩트체크는 완벽하지 않습니다.** PASS 2가 수치를 재검색해 교차검증하고, 확인 못 한 항목은 숫자를 지어내는 대신 "확인 불가"로 남기도록 시스템 프롬프트에 강제해 뒀습니다. 대시보드 맨 아래 **🔎 팩트체크 노트**에 무엇을 고쳤는지, 무엇이 미확인인지 나옵니다. 매매 결정 전엔 그 섹션을 먼저 보세요. 팩트체크 단계 자체가 실패하면 카톡 메시지에 `⚠️ 팩트체크 실패` 가 붙습니다.

**무료 티어는 품질이 유료보다 낮습니다.** Flash 계열 모델이라 분석의 깊이가 얕을 수 있습니다. 숫자는 검색 그라운딩으로 잡히지만, 8번 인사이트나 9번 투자 행동 섹션은 참고용으로 보세요.

**무료 티어 데이터 취급.** Google AI Studio 무료 티어는 입력·출력이 구글의 모델 개선에 사용될 수 있습니다. 여기 들어가는 건 공개 시장 정보뿐이라 문제될 게 없지만, 개인 포트폴리오나 민감한 내용을 프롬프트에 넣지는 마세요.

**실행 시각은 ±몇 분 흔들립니다.** GitHub Actions 크론은 정시 보장이 안 돼서(피크 때 5~20분 지연) 07:35에 일찍 띄우고 07:50까지 대기했다가 발송합니다. GitHub 쪽이 크게 밀리면 07:50보다 늦을 수 있습니다.

**주말은 안 옵니다.** 크론이 월~금(KST)만 돌게 돼 있습니다. 주말도 원하면 `daily-dashboard.yml` 의 `0-4` 를 `*` 로 바꾸세요.

**내용 수정.** 섹션 구성이나 관심 종목을 바꾸려면 `generate_dashboard.py` 의 `PASS1` 문자열만 고치면 됩니다. 관심 종목·산업을 구체적으로 박아두면 결과가 훨씬 좋아집니다.

## 참고 문서

- [카카오톡 메시지 REST API](https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api)
- [카카오 기본 템플릿 (200자 제한)](https://developers.kakao.com/docs/ko/message-template/default)
- [Gemini 검색 그라운딩](https://ai.google.dev/gemini-api/docs/google-search)
- [Gemini API 요금/무료 한도](https://ai.google.dev/gemini-api/docs/pricing)
- [GitHub Actions 과금 정책](https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
