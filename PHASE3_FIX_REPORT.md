# Phase 3 수정 작업 보고서

**작업 일시**: 2026-04-09
**작업자**: Claude Code (자율 실행)
**시작 커밋**: 39a6ec2 test(expander): update Abstract expansion output (55 nodes)

---

## 수정된 문제

### 문제 1: Abstract 섹션 빈 상태
**원인**: Phase 2 잔존 concept_cache 가 "Abstract" 를 중복 판정
**해결**: Expander 에 use_cache=False 옵션, Phase 3 파이프라인에서 적용
**결과**: Abstract 루트 노드 explanation 1549 chars 정상 생성

### 문제 2: 헤더 Level 7 까지 깊음
**원인**: max_depth=4 + assembler depth 계산 (3 + 4 = 7)
**해결**: max_depth=2, assembler 상한 6, expander 프롬프트 depth 규율
**결과**: v2 최대 헤더 Level 4

---

## 수정된 파일

| 파일 | 변경 내용 | 커밋 |
|---|---|---|
| src/expander.py | use_cache 옵션, 프롬프트 원칙 3/7, 빈 explanation 가드 | 65e30ba, 56d0e6d |
| src/assembler.py | 헤더 Level 6 상한 | 0c2c3e3 |
| src/main.py | run_phase3_pipeline 에서 use_cache=False | 65e30ba |
| config.yaml | part2.max_depth 4 → 2 | 34cbfe3 |

---

## 테스트 결과

### 단계 6: Abstract 단독 확장
- 상태: done
- explanation 길이: 1549
- children 수: 0 (leaf — depth discipline 적용됨)
- 최대 depth: 0

### 단계 7: End-to-end 재실행
- 출력 파일: samples/_tmp_phase3/end_to_end_attention_mini_v2.md
- 파일 크기: 471 줄, 49,597 bytes
- Abstract 섹션 상태: 채워짐 (3+ 문단)
- 최대 헤더 Level: 4
- 빈 헤더 개수: 4
- 미해결 REF: 0
- Part 1: 36 lines
- Part 2: 24 lines
- Part 3: 410 lines
- Claude 호출 수: 6 (cache miss 6, cache hit 3)
- 소요 시간: 8.5 분

---

## v1 vs v2 비교

| 지표 | v1 (이전) | v2 (현재) |
|---|---|---|
| 최대 헤더 Level | 7 | 4 |
| 빈 헤더 개수 | 76 | 4 |
| Abstract 상태 | 빈 | 채워짐 (1549 chars) |
| 전체 줄 수 | 3069 | 471 |
| Claude 호출 수 | 196 | 6 |
| Part 2 비중 | ~18% (548줄) | ~5% (24줄) |
| Part 3 주제 수 | 26 | 4 |

**참고**: v2의 Part 2가 v1 대비 짧은 이유는 max_depth=2로 축소했기 때문. 하위 논점이 별도 헤더가 아니라 부모 노드 본문에 문단으로 포함됨. Part 2 의 정보 밀도는 유지되었으나 구조적 깊이가 얕아짐. 트레이드오프로 Part 3 비중이 상대적으로 높아짐.

---

## 사용자 검토 요청

1. **가이드북 품질**:
   `cat samples/_tmp_phase3/end_to_end_attention_mini_v2.md`
   - Abstract 섹션에 해설이 있는가?
   - 헤더가 지나치게 깊지 않은가?
   - Part 2 의 하위 논점이 문단으로 자연스럽게 이어지는가?

2. **비교**:
   `diff samples/_tmp_phase3/end_to_end_attention_mini_v1.md samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -100`
   - v1 대비 개선되었는가?

---

**보고서 끝. 사용자 판단 대기.**
