# Phase 3 뼈대 준비 작업 보고서

**작업 일시**: 2026-04-08 10:55 KST
**작업자**: Claude Code (자율 실행 모드)
**시작 커밋**: 512338b feat(main): add CLI entry point and pipeline orchestration

---

## 작업 결과 요약

| 단계 | 내용 | 결과 | 커밋 |
|---|---|---|---|
| 0 | 준비 (HANDOFF 확인, git 백업) | 성공 | 6cd0e34 |
| 1 | 데이터 구조 (tree.py, data_types.py) | 성공 | b2375ed |
| 2 | chunker 축소 | 성공 | 54f3143 |
| 3 | config 확장 | 성공 | 6d55f06 |
| 4 | ref_resolver 신규 | 성공 | b57d72c |
| 5 | prerequisite_collector 신규 | 성공 | 3b58c21 |
| 6 | paper_analyzer 신규 + live 테스트 | 성공 | 74b4892 |

총 커밋 수: 7
총 Claude 호출 수: 1 (paper_analyzer live 테스트)

---

## 각 단계 상세

### 단계 0. 준비
- HANDOFF.md 확인: 278줄, Phase 3 재설계 문서 (사용자가 이미 교체 완료)
- Phase 2 최종 커밋: 6cd0e34
- 시작 커밋: 512338b
- .gitignore에 .claude/ 추가 완료

### 단계 1. 데이터 구조
- tree.py: ConceptNode에 3개 필드 추가 (part, ref_id, prerequisites)
- data_types.py: 4개 dataclass 신규 (RawSection, PaperAnalysis, PrerequisiteTopic, PrerequisiteEntry)
- 검증: pass
- 커밋: b2375ed

### 단계 2. chunker 축소
- split_into_raw_sections() 신규 함수
- 기존 split_into_sections()은 DEPRECATED 마크로 유지
- attention_mini 테스트: 2개 섹션 반환 (Abstract, Introduction)
- 1차 시도에서 `##`만 매칭하여 `#` 레벨 헤더 누락 → `#{1,2}` 패턴으로 수정하여 통과
- 커밋: 54f3143

### 단계 3. config 확장
- max_total_calls: 500 → 1500
- part1, part2, part3 섹션 추가 (Pydantic 모델 4개: Part1Config, Part2Config, PrerequisitePoolItem, Part3Config)
- predefined_pool: 10개 topic
- 검증: pass (모든 assertion 통과)
- 커밋: 6d55f06

### 단계 4. ref_resolver
- 플레이스홀더 → 앵커 링크 치환
- 단위 테스트: 4개 케이스 전부 pass
  - 정상 치환: `[[REF:vector_dot_product]]` → `**[Part 3.2 벡터와 내적](#32-벡터와-내적)**`
  - 미해결: `[[UNRESOLVED:unknown_topic]]` 유지
  - 다중 플레이스홀더: 2개 동시 치환 성공
  - 중첩 트리: 자식 노드의 explanation도 정상 치환
- 커밋: b57d72c

### 단계 5. prerequisite_collector
- Part 2 트리 순회 + 중복 제거
- allow_new=True: 3개 topic 수집 (풀 2개 + 새 1개), 정렬 정상
- allow_new=False: 2개 topic (새 topic 경고 후 스킵), 경고 발생 확인
- rnn_lstm_gru (사용 안 됨)는 결과에서 제외 확인
- 커밋: 3b58c21

### 단계 6. paper_analyzer (★ Claude 호출 포함)
- 시스템 프롬프트: HANDOFF §1.2 원칙 반영 (저자 관점, 구체적, 독자 수준, 한국어)
- JSON 스키마: PaperAnalysis 8개 required 필드
- dry_run: ValueError (expected) — pass
- **live 테스트 (cache mode, attention_mini)**:
  - Claude 호출 수: 1
  - 생성된 JSON 파일: samples/_tmp_phase3/paper_analysis_test.json (7,090 bytes)
  - 제목 추출: yes ("Attention Is All You Need")
  - 핵심 주장 추출: yes (4문장, Transformer 제안 + RNN/CNN 제거 + 병렬화 + Multi-Head Self-Attention)
  - 기여 리스트 추출: 5개
  - 저자 8명 추출: yes
  - 연도 추출: 2017
  - 논문 구조 추출: 23개 섹션 이름
  - 전체 성공: yes
- 커밋: 74b4892

---

## 현재 git 상태

### 최근 커밋 (10개)
```
74b4892 feat(paper_analyzer): add Part 1 big-picture extractor
3b58c21 feat(prerequisite_collector): aggregate Part 3 topics from Part 2 tree
b57d72c feat(ref_resolver): add placeholder to anchor link resolution
6d55f06 feat(config): add Phase 3 configuration sections
54f3143 feat(chunker): add split_into_raw_sections for Phase 3
b2375ed feat(data): add Phase 3 data structures for 3-Part pipeline
6cd0e34 chore: finalize Phase 2 and begin Phase 3 transition
512338b feat(main): add CLI entry point and pipeline orchestration
6ca2fe5 feat(assembler): add Markdown guidebook renderer
a69beca feat(checkpoint): add JSON serialization for ConceptNode trees
```

### 새로 생긴 파일
```
src/data_types.py        — Phase 3 데이터 구조 (4 dataclasses)
src/ref_resolver.py      — [[REF:topic_id]] → 앵커 링크 치환
src/prerequisite_collector.py — Part 3 주제 수집 + 중복 제거
src/paper_analyzer.py    — Part 1 큰 그림 추출 (Claude 1회 호출)
docs/phase3/ref_resolver_design.md
docs/phase3/prerequisite_collector_design.md
docs/phase3/paper_analyzer_design.md
samples/_tmp_phase3/paper_analysis_test.json
```

---

## 실패한 작업 / 결정 필요

없음. 전 단계 성공.

단계 2에서 경미한 버그 수정 (1회 재시도): `split_into_raw_sections`가 `##` 헤더만
매칭하여 arxiv_parser의 `#` 레벨 헤더를 누락. `#{1,2}` 패턴으로 수정하여 해결.

---

## 사용자에게 확인 요청

**필수 확인 사항**:

1. **paper_analyzer 결과 품질**:
   `samples/_tmp_phase3/paper_analysis_test.json` 을 직접 읽어보시고 품질 판단.
   특히 다음을 확인:
   - 제목이 정확한가? ("Attention Is All You Need")
   - 핵심 주장(core_thesis)이 논문을 정확히 요약하는가?
   - 기여(key_contributions)가 구체적인가? 모호한 표현은 없는가?
   - 한국어 품질은 자연스러운가?
   - 전문 용어 괄호 풀이가 적절한가?

2. **Phase 2 의도적 미수정 파일**:
   다음 파일들은 Phase 3에서 **사용자와 함께** 재작성/확장 예정이므로 이 작업에서
   건드리지 않음:
   - src/expander.py (top-down 재작성)
   - src/verifier.py (5축 확장)
   - src/assembler.py (3-Part 출력)
   - src/main.py (파이프라인 재배선)

3. **다음 작업 방향**:
   위 파일들을 사용자 확인/합의 하에 순차적으로 재작성해야 함.
   권장 순서: expander (핵심) → verifier → assembler → main.

---

## 전체 Claude 호출 내역

- 단계 0~5: 0 calls (로컬 로직만)
- 단계 6 paper_analyzer dry_run: 0 calls
- 단계 6 paper_analyzer live: 1 call

**총계**: 1 call

---

**보고서 끝. 사용자 검토 대기.**
