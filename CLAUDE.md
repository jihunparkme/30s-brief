# CLAUDE.md - 30초 브리프 (30s Brief)

출근길 30초 안에 국내·세계 핵심 이슈와 "내 지갑·일상 영향"을 확인하는 로그인 없는 웹 대시보드.
**핵심 단어(Tag) + 팩트 한 문장 + 내 지갑·일상 영향 한 줄**의 3단 압축 구조를 KR·US·CN·JP·EU·ME 6개 권역에 제공하며, 전 과정을 100% 배치 자동화로 운영합니다.

---

## 📌 기준 문서

- **`docs/prd.md`가 기준 문서**입니다. `docs/proposal.md`는 참고용이며, 두 문서가 다르면 PRD를 따릅니다.
- **`docs/work-order.md`**: 작업 순서·선행 작업·Jira 키(`BRIEF-XX`) 매핑. 작업 시작 전 선행 작업을 확인합니다.

---

## 📦 프로젝트 구조

```
30s-brief/
├── docs/
│   ├── prd.md                 # PRD (기준 문서)
│   ├── proposal.md            # 기획안 (참고용)
│   └── work-order.md          # 작업 순서 및 Jira 키 매핑
├── pipeline/                  # Python 수집·요약 배치
│   ├── collector/             # RSS 수집기 (models, sources, adapters, collector, __main__)
│   └── tests/                 # unittest 기반 테스트
├── supabase/
│   └── migrations/            # SQL 마이그레이션 (briefings / issues / system_logs)
├── .claude/commands/          # jira-start, jira-commit, jira-test, jira-create, jira-complete
└── CLAUDE.md                  # 이 파일
```

> 프론트엔드(Next.js)는 아직 없으며 work-order 3단계 이후 추가됩니다. 추가 시 이 구조도를 갱신하세요.

---

## 🏗️ 아키텍처

```
GitHub Actions (3시간 주기, 일 8회)
  → Python: RSS 수집 (Google Trends / Google News)
  → Gemini Flash: Structured Outputs(JSON Schema) 요약
  → Supabase(PostgreSQL): 멱등 UPSERT
  → Next.js /api/revalidate 웹훅 → ISR 재검증
Next.js (Vercel): 메인·아카이브 ISR/CDN 서빙 (페이지 로드 시 DB 직접 조회 없음)
```

**핵심 원칙**
- 사람 개입 없는 무인 운영, 초기 인프라 비용 $0 (Vercel Hobby / Supabase Free / Gemini 무료 쿼터)
- 배치는 **멱등**해야 함: 재실행 시 중복 없이 UPSERT (`briefings.briefing_date` unique, issues는 권역·순위 기준 unique)
- `briefing_date`는 **KST 기준** 일자
- 배치 실패 시 `system_logs`/`health_check` 갱신(Supabase 7일 일시정지 방지) 및 알림
- 이슈 카드: 핵심 단어(Badge) + 팩트 한 문장(40~55자) + `market_impact` 한 줄 (+ `watch_point`)

---

## 🔧 기술 스택 및 개발 가이드

### Pipeline (Python 3.10+)

```bash
# 소스 목록 확인
cd pipeline && python -m collector --list

# 수집 실행 (예: 특정 권역만, JSON 출력)
cd pipeline && python -m collector --region US --json

# 테스트
cd pipeline && python -m unittest discover -s tests -v
```

- 의존성은 가능한 한 표준 라이브러리 위주로 유지합니다.
- 소스 정의는 `collector/sources.py`, 파서는 `collector/adapters.py`에 추가합니다.

### Database (Supabase)

- 스키마 변경은 `supabase/migrations/YYYYMMDDHHMMSS_description.sql` 새 파일로 추가합니다. 기존 마이그레이션은 수정하지 않습니다.
- SQL은 `create ... if not exists` 등 재실행 가능한 형태를 선호합니다.
- 스키마 변경 시 `docs/prd.md`의 데이터 요구사항과 일치하는지 확인합니다.

### Frontend (Next.js, 예정)

- Next.js (App Router) + TypeScript, Vercel 배포
- `revalidate=1800` + On-Demand Revalidation, LCP 2.5초 이내(모바일 4G)
- 모바일 한 손 사용 우선 (반응형 375px / 768px / 1024px+)
- 이벤트 트래킹: `copy_brief`, `accordion_open`, `feedback`

---

## 🌍 환경 변수

실제 값은 **절대 커밋하지 않습니다** (GitHub Actions Secrets / Vercel 환경 변수 사용).

```env
# Pipeline
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
REVALIDATE_URL=
REVALIDATE_SECRET=

# Frontend
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

`SUPABASE_SERVICE_ROLE_KEY`는 서버/배치 전용이며 클라이언트에 노출 금지.

---

## 🎯 Git 브랜치 전략

- `main`: 기본·보호 브랜치 (`develop` 브랜치는 사용하지 않음)
- **코드 변경은 항상 `main` 기준 새 브랜치에서 작업**
- 네이밍: `feature|bugfix|hotfix/BRIEF-{번호}-{간단한-설명}`

```
feature/BRIEF-30-rss-collector
feature/BRIEF-34-supabase-schema
```

---

## 📋 JIRA 작업 프로세스

Jira 프로젝트 키는 **`BRIEF`** 입니다. (`.claude/commands/*.md`의 `SCRUM-XX` 예시는 `BRIEF-XX`로 읽고 적용)

```
1. 티켓 조회 → "진행 중"으로 전환
2. main 기준 작업 브랜치 생성
3. Definition of Done 확인 (work-order.md의 선행 작업 포함)
4. 구현
5. 테스트 (필수)
6. 커밋 및 푸시
7. PR 생성 (base: main)
8. JIRA 코멘트 + "검토 중"
9. 리뷰·머지 → 티켓 "완료"
```

관련 커맨드: `/jira-start`, `/jira-commit`, `/jira-test`, `/jira-create`, `/jira-complete`

---

## 🧪 테스트

| 대상 | 방법 |
| --- | --- |
| Pipeline | `cd pipeline && python -m unittest discover -s tests -v` (네트워크 의존 없이 XML 픽스처 사용) |
| Supabase 마이그레이션 | SQL 문법·멱등성(재실행 시 에러 없음) 확인 |
| Frontend (추가 후) | `npm run lint`, `npm run build`, 모바일 뷰포트 확인, 접근성 점검 |
| 배치 | 수집→요약→UPSERT를 재실행해도 중복·에러가 없는지 확인 |

---

## 📝 커밋 메시지 컨벤션

이모지 + conventional commit, 제목 끝에 Jira 키를 표기합니다. 메시지는 한국어.

```
✨ feat: RSS 수집기(소스 어댑터) 구현 (BRIEF-30)
🐛 fix: macOS Python SSL 인증서 번들 누락 시 시스템 CA로 폴백 (BRIEF-30)
📝 docs: 작업 순서 문서 추가 및 PRD 기준 명시
```

| 이모지 | 타입 | 용도 |
| --- | --- | --- |
| ✨ | feat | 새로운 기능 |
| 🐛 | fix | 버그 수정 |
| 📝 | docs | 문서 변경 |
| 💄 | style | 포맷팅 (기능 변경 없음) |
| ♻️ | refactor | 리팩토링 |
| ✅ | test | 테스트 추가/수정 |
| 🔧 | chore | 빌드·설정 |

---

## ❌ 금지 사항

1. `main`에 직접 커밋 금지 — 항상 작업 브랜치 + PR
2. 테스트 실패·미실행 상태로 커밋/머지 금지
3. 테스트 없이 JIRA 티켓 완료 처리 금지, 상태 변경 시 작업 내역 코멘트 필수
4. API 키·시크릿 커밋 금지
5. 기존 마이그레이션 파일 수정 금지 (새 마이그레이션 추가)
6. PRD와 다른 동작 구현 금지 — 변경이 필요하면 PRD 먼저 확인·갱신
7. 면책 원칙 위반 금지: AI(Gemini) 요약 고지, "투자 조언이 아님" 문구 유지
8. `__pycache__`, `.DS_Store` 등 산출물 커밋 금지

---

## 📚 참고 문서

- `docs/prd.md` — 기능 명세(US-1~10), 비기능 요구사항, 범위
- `docs/work-order.md` — 작업 순서와 Jira 키
- `docs/proposal.md` — 기획 배경 (참고용)
