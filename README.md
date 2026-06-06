# Snippet Football Geek Backend

축구 소식을 수집하고 정리해 한국어 팀별 브리핑으로 저장하는 Python 배치 백엔드입니다.

MVP는 Liverpool 소식을 대상으로 하며, GitHub Actions 스케줄을 통해 하루 2회 기본 브리핑을 생성하는 구조로 시작합니다. 이적시장이나 경기일처럼 소식이 많은 기간에는 실행 횟수를 늘릴 수 있도록 설계합니다.

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

```bash
python3 -m app.jobs.run_briefing \
  --team liverpool \
  --type morning \
  --source liverpool_echo \
  --use-groq
```

## 테스트

```bash
python3 -m unittest discover -s tests -v
```
