# Snippet Football Geek Backend

축구 소식을 수집하고 정리해 한국어 팀별 브리핑으로 저장하는 Python 배치 백엔드입니다.

MVP는 Liverpool 소식을 대상으로 하며, GitHub Actions 스케줄을 통해 하루 3회 기본 브리핑을 생성하는 구조로 시작합니다. 이적시장이나 경기일처럼 소식이 많은 기간에는 실행 횟수를 늘릴 수 있도록 설계합니다.

## 실행 구조

- GitHub Actions가 정해진 시간에 Python 배치 작업을 실행합니다.
- Python collector가 RSS 기반 소식을 수집합니다. X 프로필 수집은 어댑터 뼈대를 먼저 두고 실제 스크래핑 구현을 별도 단계로 붙입니다.
- 중복 제거와 팀 관련성 필터링을 거친 뒤 Groq로 한국어 요약/번역을 생성합니다.
- 생성된 브리핑 데이터는 Supabase에 저장합니다.
- 프론트엔드는 Supabase에 저장된 데이터를 읽어 화면에 보여줍니다.

## 주요 방향

- Liverpool MVP로 시작하되 팀별 확장을 고려합니다.
- X 수집은 지정 계정 기반으로 시작합니다.
- X 수집은 `RawItem`을 반환하는 어댑터 구조로 준비해두고, `snscrape`, Playwright, 다른 스크래퍼로 교체할 수 있게 유지합니다.
- X 수집은 운영 보조 수집원으로 다루며, 실패해도 RSS 기반 브리핑 생성은 계속 진행합니다.
- 서비스 톤은 팬 친화형 브리핑을 기준으로 합니다.

## 환경 변수

로컬에서는 `.env`를 사용하고, GitHub Actions에서는 Repository secrets를 사용합니다. 실제 키는 커밋하지 않습니다.

필요한 값:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GROQ_API_KEY`

X 계정 기반 수집을 테스트할 때 필요한 값:

- `X_USERNAME`
- `X_EMAIL`
- `X_PASSWORD`
- `X_COOKIES_FILE`: 기본값 `x_cookies.json`
- `X_TOTP_SECRET`: 2FA를 사용하는 계정일 때만 필요
- `X_AUTH_TOKEN`: 브라우저에서 확보한 X `auth_token` 쿠키 값, 직접 로그인 실패 시 사용
- `X_CT0`: 브라우저에서 확보한 X `ct0` 쿠키 값, 직접 로그인 실패 시 사용

## 로컬 실행

기본 실행은 콘솔에 브리핑 JSON을 출력합니다.

```bash
python3 -m app.jobs.run_briefing --team liverpool --type morning
```

RSS URL을 지정하면 해당 피드를 수집해서 같은 콘솔 JSON 형식으로 출력합니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --rss-url "https://example.com/rss" \
  --rss-source-name "Example RSS"
```

임시 Liverpool 소스 설정을 사용할 수도 있습니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source all
```

현재 설정된 소스:

- `liverpool_echo`: Liverpool Echo - Liverpool FC RSS
- `official_website`: Liverpool FC Official Website, 현재 RSS 없음
- `bbc_sport`: BBC Sport football 전체 RSS, 리버풀 관련성 필터로 선별
- `x_reporters`: 지정 기자 X 프로필 묶음, 현재는 실제 스크래핑 전 어댑터 뼈대
- `james_pearce`: James Pearce X 프로필

X 프로필 소스는 `snscrape` provider를 사용합니다. 로컬에서 X 수집을 테스트하려면 선택 의존성을 설치합니다.

```bash
python3 -m pip install ".[x]"
```

`app.collectors.x_profiles`는 `post_provider`를 주입할 수 있게 만들어두었기 때문에, `snscrape`가 불안정해지면 Playwright 같은 다른 수집기로 교체할 수 있습니다.

현재 로컬 live 테스트에서는 `snscrape`가 X/Twitter GraphQL 요청에서 `blocked (404)`로 실패했습니다. 그래서 구조와 변환 로직은 준비됐지만, 운영 수집 방식은 Playwright 기반 스크래핑이나 인증 세션 기반 provider로 이어서 보강해야 합니다.

Twikit provider는 공식 API key 없이 계정 로그인과 쿠키 파일을 사용합니다. 첫 실행 때 `.env`의 X 계정 정보로 로그인을 시도하고, 이후에는 `x_cookies.json`을 재사용합니다. 이 파일은 `.gitignore`에 포함되어 있으며 커밋하지 않습니다.

X가 계정/비밀번호 직접 로그인을 막는 경우에는 브라우저에서 로그인한 뒤 개발자 도구 또는 쿠키 관리 도구로 `auth_token`, `ct0` 쿠키 값을 확인해 `.env`의 `X_AUTH_TOKEN`, `X_CT0`에 넣습니다. 그러면 실행 시 `x_cookies.json`을 생성하고 로그인 절차를 건너뜁니다.

X 수집은 차단이나 쿠키 만료가 발생할 수 있으므로, X 프로필 수집 실패는 stderr에 남기고 나머지 RSS 소스 처리를 계속합니다. 운영에서는 RSS 브리핑을 기본 축으로 유지하고, X는 추가 신호로 붙이는 구조를 권장합니다.

```bash
python3 -m pip install ".[x-twikit]"
```

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source x_reporters \
  --x-provider twikit \
  --x-cookies-file x_cookies.json \
  --limit 3
```

Playwright 로그인 세션을 만들려면 선택 의존성과 브라우저를 설치한 뒤 세션 캡처 스크립트를 실행합니다.

```bash
python3 -m pip install ".[x-playwright]"
python3 -m playwright install chromium
python3 -m app.jobs.capture_x_session
```

브라우저에서 X 로그인을 완료하고 Enter를 누르면 `x_storage_state.json`이 생성됩니다. 이 파일은 `.gitignore`에 포함되어 있으며 커밋하지 않습니다.

세션 파일 생성 후에는 Playwright provider를 선택해서 X 프로필 소스를 실행할 수 있습니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source x_reporters \
  --x-provider playwright \
  --x-storage-state x_storage_state.json
```

새로운 소식만 확인하려면 `--since`를 지정합니다. 데이터 보관 정책은 기본 7일 기준으로 보고, 그보다 오래된 항목은 콘솔 payload 생성 전에 제외합니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source all \
  --since "2026-06-06T08:00:00Z" \
  --retention-days 7
```

로컬 state 파일을 사용하면 마지막 성공 실행 시각을 자동으로 저장하고, 다음 실행부터 그 이후 소식만 처리합니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source liverpool_echo \
  --retention-days 7 \
  --state-file .runtime/liverpool-morning.json
```

Groq API key가 `.env`에 있으면 `--use-groq`로 기사 요약/번역을 실제 한국어 브리핑 문장으로 생성할 수 있습니다.
기본 모델은 한국어 기사 요약 품질을 우선해 `llama-3.3-70b-versatile`을 사용합니다.
빠른 개발 테스트가 필요하면 `--groq-model llama-3.1-8b-instant`로 바꿀 수 있습니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source liverpool_echo \
  --use-groq
```

Groq 프롬프트나 출력 구조를 확인할 때는 `--limit`으로 처리 건수를 줄일 수 있습니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source liverpool_echo \
  --limit 3 \
  --use-groq
```

Supabase에 저장하려면 `.env`에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`를 넣고 `--save-supabase`를 추가합니다.

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source liverpool_echo \
  --limit 1 \
  --use-groq \
  --save-supabase
```

`--save-supabase`를 사용하면서 `--since`를 직접 지정하지 않으면 Supabase에 저장된 해당 팀의 최신 브리핑 `published_at`을 기준으로 새 소식만 처리합니다. 새 항목이 없으면 빈 브리핑은 저장하지 않고 콘솔 출력만 남깁니다.

콘솔 출력과 Supabase 저장 payload는 아래 구조를 유지합니다.

- `team_slug`, `briefing_type`, `title`, `summary_ko`, `published_at`
- `items[].section`
- `items[].headline_ko`
- `items[].body_ko`
- `items[].category`
- `items[].category_label_ko`
- `items[].confidence_label`
- `items[].source_urls`
- `items[].source_names`
- `items[].source_type`

현재 대표 카테고리는 항목당 하나만 사용합니다.

- `transfer`: 이적
- `injury`: 부상
- `match_result`: 경기 결과
- `match_preview`: 경기 프리뷰
- `team_news`: 팀 소식
- `official`: 오피셜
- `rumor`: 루머
- `etc`: 기타

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

## Supabase 데이터베이스

생성 SQL과 테이블 설명은 `database/` 폴더에 있습니다.

- `database/schema.sql`: Supabase SQL Editor에서 실행할 테이블/인덱스 생성 SQL
- `database/README.md`: 테이블 구조와 주요 필드 설명

MVP 저장 구조는 `briefings`와 `briefing_items` 두 테이블입니다. `briefing_items.item_type`으로 기사(`article`)와 X 게시물(`social_post`)을 구분하고, `category`로 이적/부상/경기 결과 같은 대표 카테고리를 구분합니다.

## GitHub Actions

`.github/workflows/briefing.yml`은 수집, 요약, Supabase 저장까지 실행하는 배치 workflow입니다.

- 매일 3회 실행합니다.
  - `20:00 UTC`: 한국 시간 05:00 새벽/아침 브리핑
  - `07:00 UTC`: 한국 시간 16:00 오후 브리핑
  - `13:00 UTC`: 한국 시간 22:00 밤 브리핑
- `workflow_dispatch`로 수동 실행할 수 있습니다.
- 기본 실행은 `all` 소스에서 `5건`을 처리하고, Twikit provider로 X 지정 계정 수집을 함께 시도합니다.
- `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`는 GitHub Repository secrets에 등록해야 합니다.
- X 수집을 GitHub Actions에서 사용하려면 `X_AUTH_TOKEN`, `X_CT0`, `X_COOKIES_FILE`도 Repository secrets에 직접 등록해야 합니다.
- 실행 상태는 Supabase `collector_runs` 테이블에 저장합니다.
- Actions 로그에는 콘솔 JSON도 함께 남습니다.

수동 실행 입력값:

- `team`: 기본 `liverpool`
- `briefing_type`: `morning`, `afternoon`, `evening`, `transfer_extra`, `matchday`
- `source`: 기본 `liverpool_echo`
- `limit`: 기본 `3`
- `use_groq`: 기본 `true`
