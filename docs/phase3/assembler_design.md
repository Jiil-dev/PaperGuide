# assembler.py Phase 3 확장 설계

## 추가되는 것
3-Part 구조 출력 지원.

## 공개 API
기존 함수 유지 + 새 함수 추가:

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

### 1.1 핵심 주장
### 1.2 해결하려는 문제
### 1.3 핵심 기여
### 1.4 주요 결과
### 1.5 이 논문의 의의
### 1.6 읽는 법

## Part 2. 논문 따라 읽기 — 완전 해설

### 2.1 [첫 섹션 이름]
### 2.2 [다음 섹션]

## Part 3. 기초 지식 탄탄히

### 3.1 [첫 주제 제목]
### 3.2 ...
```

## ref 치환
Part 2 렌더링 **전에** ref_resolver.resolve_refs() 를 호출해서
[[REF:...]] 을 앵커 링크로 치환.
