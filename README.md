# Snippet Football Geek Backend

축구 소식을 수집하고 정리해 한국어 팀별 브리핑으로 저장하는 Python 배치 백엔드입니다.

MVP는 Liverpool 소식을 대상으로 하며, GitHub Actions 스케줄을 통해 하루 3회 기본 브리핑을 생성하는 구조로 시작합니다. 이적시장이나 경기일처럼 소식이 많은 기간에는 실행 횟수를 늘릴 수 있도록 설계합니다.

## 실행 구조

- GitHub Actions가 정해진 시간에 Python 배치 작업을 실행합니다.
- Python collector가 RSS, 크롤링, X 프로필 기반 소식을 수집합니다.
- 중복 제거와 팀 관련성 필터링을 거친 뒤 Groq로 한국어 요약/번역을 생성합니다.
- 생성된 브리핑 데이터는 Supabase에 저장합니다.
- 프론트엔드는 Supabase에 저장된 데이터를 읽어 화면에 보여줍니다.

## 주요 방향

- Liverpool MVP로 시작하되 팀별 확장을 고려합니다.
- X 수집은 지정 계정 기반으로 시작합니다.
- `snscrape`는 첫 X 수집 어댑터로 사용하되, 다른 어댑터로 교체할 수 있는 구조를 유지합니다.
- 서비스 톤은 팬 친화형 브리핑을 기준으로 합니다.

## 환경 변수

로컬에서는 `.env`를 사용하고, GitHub Actions에서는 Repository secrets를 사용합니다. 실제 키는 커밋하지 않습니다.

필요한 값:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GROQ_API_KEY`

## 로컬 실행

현재 1차 구현은 Supabase 저장 없이 콘솔에서 브리핑 데이터 형식을 확인하는 단계입니다.

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

현재 콘솔 payload는 Supabase 저장 전 검증용으로 아래 구조를 유지합니다.

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

`.github/workflows/briefing.yml`은 현재 Supabase 저장 전 단계의 배치 실행 검증용 workflow입니다.

- 매일 3회 실행합니다.
  - `20:00 UTC`: 한국 시간 05:00 새벽/아침 브리핑
  - `07:00 UTC`: 한국 시간 16:00 오후 브리핑
  - `13:00 UTC`: 한국 시간 22:00 밤 브리핑
- `workflow_dispatch`로 수동 실행할 수 있습니다.
- 기본 실행은 `liverpool_echo` 소스에서 `3건`만 처리합니다.
- `GROQ_API_KEY`는 GitHub Repository secrets에 등록해야 합니다.
- 현재 단계에서는 콘솔 JSON을 Actions 로그에서 확인합니다.

수동 실행 입력값:

- `team`: 기본 `liverpool`
- `briefing_type`: `morning`, `afternoon`, `evening`, `transfer_extra`, `matchday`
- `source`: 기본 `liverpool_echo`
- `limit`: 기본 `3`
- `use_groq`: 기본 `true`
