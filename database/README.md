# 데이터베이스 구조

MVP는 Supabase Postgres에 브리핑 묶음과 개별 항목을 분리해서 저장합니다.

## 테이블

- `briefings`: 하루 3회 생성되는 브리핑 묶음입니다.
- `briefing_items`: 브리핑 안에 들어가는 기사 또는 X 게시물 항목입니다.

## 주요 필드

`briefings`

- `team_slug`: 팀 구분값입니다. MVP는 `liverpool`입니다.
- `briefing_type`: `morning`, `afternoon`, `evening`, `transfer_extra`, `matchday` 중 하나입니다.
- `published_at`: 브리핑 발행 시각입니다.
- `raw_payload`: 현재 콘솔에 출력하는 payload 원본을 보관하는 JSONB 필드입니다.

`briefing_items`

- `item_type`: `article` 또는 `social_post`입니다. 프론트에서 기사 카드와 X 카드 표시를 나눌 때 사용합니다.
- `category`: `transfer`, `injury`, `match_result`, `match_preview`, `team_news`, `official`, `rumor`, `etc` 중 하나입니다.
- `category_label_ko`: 프론트 표시용 한글 카테고리입니다.
- `section`: `top_stories` 또는 `reporter_signals`입니다.
- `confidence_label`: `official`, `reported`, `rumor`, `unconfirmed`, `reporter_claim` 중 하나입니다.
- `source_urls`, `source_names`: 원문 링크와 출처명 배열입니다.

## 생성 방법

Supabase SQL Editor에서 `database/schema.sql` 내용을 실행하면 됩니다.

프론트엔드는 anon key로 조회할 수 있도록 `briefings`, `briefing_items`에 공개 select RLS 정책을 둡니다. 쓰기는 백엔드 배치가 service role key로 처리하는 것을 전제로 합니다.

7일 보관 정책은 `schema.sql` 마지막의 delete 문을 GitHub Actions 또는 Supabase scheduled job에서 주기적으로 실행하는 방식으로 시작합니다.
