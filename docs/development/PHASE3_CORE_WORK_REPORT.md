# Phase 3 Core 작업 보고서

**작업 일시**: 2026-04-08
**작업자**: Claude Code (자율 실행 모드, 옵션 C 풀 버전)
**시작 커밋**: 58889d9 docs: add Phase 3 skeleton preparation report

---

## 작업 결과 요약

| 단계 | 내용 | 결과 | 커밋 |
|---|---|---|---|
| 8 | verifier 6축 확장 | 완료 | d733e42 |
| 9 | expander top-down 재작성 | 완료 | 63d1279 |
| 10 | part3_writer 신규 | 완료 | 203f1d2 |
| 11 | assembler 3-Part 확장 | 완료 | 83ea2d4 |
| 12 | main.py 파이프라인 재배선 | 완료 | 29d8c5b |
| 13 | attention_mini end-to-end 테스트 | 완료 | ab729b9 |

총 커밋 수: 6 (단계 8~13)
총 Claude 호출 수: 196 (end-to-end 기준)

---

## 각 단계 상세

### 단계 8. verifier 6축 확장
- 추가된 축: paper_centric (논문 중심성), flow (흐름 유지)
- 기존 4축 (faithfulness, level, self_contained, formula) 유지
- 공개 API 유지 (Verifier.verify() 시그니처 불변)
- dry_run: 정상 (schema 기본값 반환)
- live 테스트: paper_centric=5/5, flow=4/5 (good case)
- 결과 파일: `samples/_tmp_phase3/verifier_5axis_test.json`
- 커밋: d733e42

### 단계 9. expander top-down 재작성 (★)
- 시스템 프롬프트 전면 재작성 (저자 관점, top-down, 기초 지식 위임)
- JSON 스키마 변경:
  - children: `name` → `concept` + `brief` (하위 논점)
  - `prerequisites` 필드 추가 (topic_id 리스트)
- `[[REF:topic_id]]` 플레이스홀더 삽입 규칙 적용
- `part=2` 기본 설정
- dry_run: 구조 정상
- live 테스트: attention_mini Abstract 확장, end-to-end에서 2개 섹션 모두 재귀 확장 완료
- 결과 파일: `samples/_tmp_phase3/expander_abstract_output.json`
- 커밋: 63d1279

### 단계 10. part3_writer 신규
- `src/part3_writer.py` 신규 생성
- 공개 API: `write_part3_topic(topic, section_number, client) -> PrerequisiteEntry`
- 시스템 프롬프트: 정의 → 직관 → 원리 → 예시 → 논문 연결 순
- JSON 스키마: title, intro, subsections[{concept, explanation}], connection_to_paper
- dry_run: ValueError 예상대로 (빈 subsections)
- live 테스트: vector_dot_product 주제로 8개 하위 섹션 생성
- 결과 파일: `samples/_tmp_phase3/part3_topic_output.json`
- 커밋: 203f1d2

### 단계 11. assembler 3-Part 확장
- `assemble_3part_guidebook()` 함수 추가 (기존 `assemble()` 유지)
- Part 1: PaperAnalysis → 1.1~1.6 섹션 렌더링
- Part 2: expander 트리 재귀 렌더링 (### → #### → ...)
- Part 3: part3_writer 항목 렌더링
- `ref_resolver.resolve_refs()` 호출로 `[[REF:...]]` → 앵커 링크 치환
- 단위 테스트 (가짜 데이터): 3-Part 구조 확인, REF 치환 확인
- 결과 파일: `samples/_tmp_phase3/assembler_3part_output.md`
- 커밋: 83ea2d4

### 단계 12. main.py 파이프라인 재배선
- `run_phase3_pipeline()` 함수 추가 (7단계 파이프라인)
- `--phase` CLI 플래그 (기본값 3, choices=[2,3])
- `--output`, `--cache-dir` CLI 플래그 추가
- 기존 Phase 2 로직을 `run_phase2_pipeline()`으로 보존
- RateLimitExceeded 시 부분 결과로 계속 진행
- dry_run: 전체 파이프라인 에러 없이 완주
- 커밋: 29d8c5b

### 단계 13. End-to-end 테스트
- 입력: `data/papers/attention_mini` (Abstract + Introduction)
- 모드: cache
- 결과 파일: `samples/_tmp_phase3/end_to_end_attention_mini.md`
- 파일 크기: 3,069 줄, 326,723 bytes
- Claude 호출 수: 196
  - Part 1 분석: 1
  - Part 2 확장: ~170
  - Part 3 작성: ~26 (1 topic당 1 call)
- 소요 시간: ~194 분
- 미해결 플레이스홀더: 0
- Part 3 주제 수: 26
- 커밋: ab729b9

---

## 현재 git 상태

### 최근 커밋 (단계 8~13)
```
ab729b9 test(phase3): end-to-end run on attention_mini
83ea2d4 feat(assembler): add 3-Part guidebook assembly for Phase 3
203f1d2 feat(part3_writer): add Part 3 topic writer
29d8c5b feat(main): add Phase 3 pipeline with 3-Part guidebook flow
63d1279 feat(expander): rewrite internal logic for top-down Phase 3
d733e42 feat(verifier): extend to 6-axis verification for Phase 3
```

### 생성/수정된 파일
```
src/expander.py           (수정: top-down 재작성)
src/part3_writer.py       (신규)
src/main.py               (수정: Phase 3 파이프라인)
src/assembler.py          (수정: assemble_3part_guidebook 추가)
docs/phase3/expander_design.md     (신규)
docs/phase3/part3_writer_design.md (신규)
docs/phase3/assembler_design.md    (신규)
samples/_tmp_phase3/verifier_5axis_test.json
samples/_tmp_phase3/expander_abstract_output.json
samples/_tmp_phase3/part3_topic_output.json
samples/_tmp_phase3/assembler_3part_output.md
samples/_tmp_phase3/end_to_end_attention_mini.md
samples/_tmp_phase3/end_to_end_stats.json
samples/_tmp_phase3/end_to_end_log.txt
```

---

## 실패한 작업 / 결정 필요

없음. 모든 단계 완료.

---

## 사용자에게 확인 요청

**필수 검토 사항** (사용자 판단 영역):

1. **전체 가이드북 품질**:
   `cat samples/_tmp_phase3/end_to_end_attention_mini.md` 로 읽고 판단.
   - Part 1 (큰 그림) 이 논문을 잘 요약하는가?
   - Part 2 가 top-down 으로 작성됐는가? (bottom-up 회귀 여부)
   - Part 2 에 기초 지식이 깊게 박혀있지 않은가?
   - Part 3 가 탄탄한가?
   - 전체 흐름이 자연스러운가?

2. **개별 모듈 결과물**:
   - verifier: `samples/_tmp_phase3/verifier_5axis_test.json`
   - expander: `samples/_tmp_phase3/expander_abstract_output.json`
   - part3_writer: `samples/_tmp_phase3/part3_topic_output.json`
   - assembler: `samples/_tmp_phase3/assembler_3part_output.md`

3. **다음 단계**:
   - 사용자 검토 후 만족스러우면: Attention 전체 논문으로 실행
   - 개선 필요하면: 해당 모듈 프롬프트 조정 (사용자와 함께)

---

## 전체 Claude 호출 내역

- 단계 8 verifier: 1 (live 테스트)
- 단계 9 expander: 0 (개별 테스트, end-to-end에 포함)
- 단계 10 part3_writer: 1 (live 테스트)
- 단계 11 assembler: 0 (Claude 호출 없음)
- 단계 12 main: 1 (dry_run)
- 단계 13 end-to-end: 196

**총계**: ~199 calls (개별 테스트 포함)

---

**보고서 끝. 사용자 검토 대기.**
