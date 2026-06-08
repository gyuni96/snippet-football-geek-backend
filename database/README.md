# 데이터베이스 구조

MVP는 Supabase Postgres에 브리핑 묶음과 기사/X 게시물 항목을 분리해서 저장합니다.

## 테이블

- `briefings`: 하루 3회 생성되는 브리핑 묶음입니다.
- `briefing_articles`: 기사 탭에 표시할 기사 요약 항목입니다.
- `briefing_tweets`: X 탭에 표시할 트윗 번역/요약 항목입니다.
- `briefing_items`: 이전 통합 구조를 유지하기 위한 legacy 테이블입니다.

## View

- `latest_team_briefings`: 팀별 최신 브리핑 1개를 반환합니다. 첫 화면에서 최신 브리핑을 빠르게 찾을 때 사용합니다.

## 주요 필드

`briefings`

- `team_slug`: 팀 구분값입니다. MVP는 `liverpool`입니다.
- `briefing_type`: `morning`, `afternoon`, `evening`, `transfer_extra`, `matchday` 중 하나입니다.
- `published_at`: 브리핑 발행 시각입니다.
- `raw_payload`: 현재 콘솔에 출력하는 payload 원본을 보관하는 JSONB 필드입니다.

`briefing_articles`

- `category`: `transfer`, `injury`, `match_result`, `match_preview`, `team_news`, `official`, `rumor`, `etc` 중 하나입니다.
- `category_label_ko`: 프론트 표시용 한글 카테고리입니다.
- `section`: `top_stories`, `match_schedule` 중 하나입니다.
- `confidence_label`: `official`, `reported`, `rumor`, `unconfirmed` 중 하나입니다.
- `source_urls`, `source_names`: 원문 링크와 출처명 배열입니다.
- `published_at`: 기사가 올라온 시각입니다.
- `event_at`: 경기 일정처럼 실제 이벤트 시각이 있을 때만 저장합니다.
- `llm_provider`, `llm_model`: 요약에 사용한 LLM 제공자와 모델입니다.

`briefing_tweets`

- `tweet_id`, `author_handle`, `author_name`, `tweet_url`: 원본 X 게시물 식별/출처 정보입니다.
- `original_text`: 수집한 원문 텍스트입니다.
- `translated_text_ko`: 원문 의미를 한국어로 번역한 텍스트입니다.
- `headline_ko`, `body_ko`: 카드 표시용 제목과 짧은 요약입니다.
- `category`, `category_label_ko`, `confidence_label`: 프론트 필터와 신뢰도 표시에 사용합니다.
- `published_at`: X 게시물이 올라온 시각입니다.
- `llm_provider`, `llm_model`: 요약/번역에 사용한 LLM 제공자와 모델입니다.

## 생성 방법

Supabase SQL Editor에서 `database/schema.sql` 내용을 실행하면 됩니다.

프론트엔드는 anon key로 조회할 수 있도록 `briefings`, `briefing_articles`, `briefing_tweets`, `briefing_items`에 공개 select RLS 정책을 둡니다. 쓰기는 백엔드 배치가 service role key로 처리하는 것을 전제로 합니다.

7일 보관 정책은 `schema.sql` 마지막의 delete 문을 GitHub Actions 또는 Supabase scheduled job에서 주기적으로 실행하는 방식으로 시작합니다.

## 프론트 조회 예시

최신 브리핑 ID를 먼저 가져오는 예시입니다.

```js
const { data: latestBriefing } = await supabase
  .from("latest_team_briefings")
  .select("*")
  .eq("team_slug", "liverpool")
  .single();
```

기사 탭 데이터를 가져오는 예시입니다.

```js
const { data: articles } = await supabase
  .from("briefing_articles")
  .select("*")
  .eq("team_slug", "liverpool")
  .eq("briefing_id", latestBriefing.id)
  .order("sort_order", { ascending: true });
```

X 탭 데이터를 가져오는 예시입니다.

```js
const { data: tweets } = await supabase
  .from("briefing_tweets")
  .select("*")
  .eq("team_slug", "liverpool")
  .eq("briefing_id", latestBriefing.id)
  .order("published_at", { ascending: false });
```

프론트에서는 기사 탭은 `briefing_articles`, X 탭은 `briefing_tweets`를 조회하고, 각 테이블의 `category`로 카테고리 필터를 구성합니다. 최신순 표시는 일반 소식은 `published_at`, 경기 일정 항목은 `event_at`을 우선해 정렬하면 됩니다.
