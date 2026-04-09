# Phase 3 수정 보고서 v3

**작업 일시**: 2026-04-09
**작업자**: Claude Code (자율 실행)
**시작 커밋**: 6c7c219 docs: add Phase 3 fix report

---

## v1 → v2 → v3 변경 요약

- **v1**: 원본. Abstract 비어있음, 헤더 Level 7까지, 빈 헤더 76개
- **v2**: cache 비활성화 + max_depth=2 + 엄격 프롬프트 → Abstract 채워졌으나 Part 2가 24줄로 과도하게 얕아짐 (children=0)
- **v3**: 프롬프트 원칙 3 재균형 → depth=0에서 자식 생성 필수, Part 2 252줄로 복원

---

## v1 vs v2 vs v3 비교

| 지표 | v1 | v2 | v3 |
|---|---|---|---|
| 전체 줄 수 | 3,069 | 471 | 1,983 |
| 전체 크기 | 327KB | 50KB | 241KB |
| Part 1 줄 수 | 36 | 36 | 36 |
| Part 2 줄 수 | 548 | 24 | 252 |
| Part 3 줄 수 | 2,484 | 410 | 1,694 |
| 최대 헤더 Level | 7 | 4 | 5 |
| 빈 헤더 수 | 76 | 4 | 17 (모두 Part 3 topic 제목) |
| Part 2 빈 헤더 | 27+ | 0 | 0 |
| Abstract children | 0 (duplicate) | 0 (leaf) | 3 |
| Introduction children | 다수 (깊은 트리) | 0 (leaf) | 4 |
| Claude 호출 수 | 196 | 6 | 86 |
| 소요 시간 | ~194분 | ~8분 | ~96분 |
| 미해결 REF | 0 | 0 | 0 |
| Part 3 주제 수 | 26 | 4 | 17 |

---

## Part 2 섹션별 자식 노드

### Abstract (2.1)
| 버전 | children | 자식 제목 |
|---|---|---|
| v1 | 0 (duplicate) | (없음 — Phase 2 캐시 오염) |
| v2 | 0 (leaf) | (없음 — 프롬프트 과도 교정) |
| v3 | 3 | 기존 패러다임 규정 / Transformer 제안의 핵심 차별점 / 실험 결과의 압축 제시 |

### Introduction (2.2)
| 버전 | children | 자식 제목 |
|---|---|---|
| v1 | 다수 (깊은 5단계 트리) | (과도하게 세분화) |
| v2 | 0 (leaf) | (없음 — 프롬프트 과도 교정) |
| v3 | 4 | RNN 계열 모델의 지배적 위치와 순차 연산의 한계 / 기존 효율화 시도의 불충분함 / 어텐션 메커니즘의 가능성과 RNN 종속 문제 / Transformer의 제안과 구체적 성과 |

---

## v2 품질 분석 (단계 1 소견)

v2의 Part 2 본문(Abstract 1549 chars, Introduction ~3000 chars)은 **밀도가 매우 높고 품질이 우수**했다. 저자 관점 서술, REF 플레이스홀더 삽입, 논문 표현 분석 등 모든 원칙이 잘 적용됨. 문제는 **구조적 깊이 부재**: 두 섹션 모두 children=0, is_leaf=true로 처리되어 하위 헤더가 전혀 없었음. 원칙 3의 "자식 노드 기준 매우 엄격" 표현을 Claude가 "자식을 만들지 말라"로 과도 해석한 결과.

---

## v3에서 적용된 수정

| 수정 | 파일 | 커밋 |
|---|---|---|
| 원칙 3 재작성: depth=0에서 2~5개 자식 필수 | src/expander.py | 808b5ad |
| 과도 교정 방지 경고 추가 | src/expander.py | 808b5ad |
| (v2에서 유지) use_cache=False | src/expander.py, src/main.py | 65e30ba |
| (v2에서 유지) max_depth=2 | config.yaml | 34cbfe3 |
| (v2에서 유지) 헤더 Level 6 상한 | src/assembler.py | 0c2c3e3 |
| (v2에서 유지) 빈 explanation 가드 | src/expander.py | 56d0e6d |
| (v2에서 유지) 원칙 7: 모든 섹션 해설 필수 | src/expander.py | 56d0e6d |

---

## 빈 헤더 설명

v3의 빈 헤더 17개는 **모두 Part 3 topic 제목 헤더** (예: `### 3.1 신경망의 기초`).
이들은 바로 다음에 `#### 3.1.1 ...` 하위 섹션이 오는 구조이므로 topic 제목 자체에
본문이 없는 것은 정상. **Part 2에는 빈 헤더가 0개.**

---

## 사용자 검토 요청

1. **v3 가이드북 품질**:
   `cat samples/_tmp_phase3/end_to_end_attention_mini_v3.md`
   - Abstract가 3개 하위 노드로 분해되었는가?
   - Introduction이 4개 하위 노드로 분해되었는가?
   - 각 하위 노드의 본문이 충분한가?
   - Part 2의 하위 논점이 자연스럽게 이어지는가?

2. **v1/v2/v3 비교**:
   - v1: 너무 깊고 빈 헤더 많음
   - v2: 너무 얕고 자식 없음
   - v3: 적절한 깊이 (Level 3~5) + 의미 있는 자식 노드

3. **다음 단계**:
   - 품질 OK → Attention 전체 논문으로 실행
   - 개선 필요 → 해당 모듈 프롬프트 조정

---

## 산출물 파일

- `samples/_tmp_phase3/end_to_end_attention_mini_v3.md` — v3 가이드북
- `samples/_tmp_phase3/end_to_end_log_v3.txt` — v3 실행 로그
- `samples/_tmp_phase3/end_to_end_attention_mini_v2_saved.md` — v2 백업
- `samples/_tmp_phase3/end_to_end_attention_mini_v1.md` — v1 백업

---

**보고서 끝. 사용자 판단 대기.**
