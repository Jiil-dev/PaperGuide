# assembler.py Phase 3 확장 설계

## 추가되는 것
3-Part 구조 출력 지원.

## 공개 API
기존 `assemble()` 유지 + 새 함수 추가:

```python
def assemble_3part_guidebook(
    analysis: PaperAnalysis,
    part2_trees: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> str:
    """3-Part 가이드북 Markdown 생성."""
```

## 출력 구조

```
# [논문 제목] — 완전판 가이드북

## Part 1. 논문이 무엇을 주장하는가 — 큰 그림
### 1.1~1.6 (PaperAnalysis 필드)

## Part 2. 논문 따라 읽기 — 완전 해설
### 2.1 [섹션] → 재귀 렌더링

## Part 3. 기초 지식 탄탄히
### 3.1 [주제] → 하위 섹션 렌더링
```

## ref 치환
Part 2 렌더링 전에 ref_resolver.resolve_refs() 를 호출해서
[[REF:...]] 을 앵커 링크로 치환.
