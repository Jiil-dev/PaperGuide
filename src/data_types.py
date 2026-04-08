# 단일 책임: Phase 3 파이프라인의 중간 단계에서 사용되는 데이터 구조 정의
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.tree import ConceptNode


@dataclass
class RawSection:
    """chunker의 출력. 논문 1차 섹션.

    Phase 2의 ConceptNode 트리 대신 단순 섹션 리스트로 축소된 chunker 결과.
    """
    title: str          # "Abstract", "Introduction", ...
    content: str        # 섹션 내용 전체 (Markdown)
    order: int          # 1부터 시작하는 순서 번호


@dataclass
class PaperAnalysis:
    """paper_analyzer의 출력. Part 1 생성 재료.

    논문 전체를 분석해서 추출된 큰 그림.
    """
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    core_thesis: str = ""              # 핵심 주장 한 문단
    problem_statement: str = ""        # 해결하려는 문제
    key_contributions: list[str] = field(default_factory=list)
    main_results: list[str] = field(default_factory=list)
    significance: str = ""             # 의의
    reading_guide: str = ""            # 가이드북 읽는 법 안내
    paper_structure: list[str] = field(default_factory=list)
    # 논문 섹션 이름 순서대로 (예: ['Abstract', 'Introduction', 'Background', ...])


@dataclass
class PrerequisiteTopic:
    """prerequisite_collector의 출력. Part 3에 포함될 주제 하나.

    여러 Part 2 섹션에서 등장한 기초 개념을 중복 제거해 모은 것.
    """
    topic_id: str              # "vector_dot_product" 같은 고유 식별자
    title: str                 # 사람이 읽는 제목
    first_mention_in: str      # 최초 언급된 Part 2 섹션 id
    all_mentions: list[str] = field(default_factory=list)
    # 이 주제가 언급된 모든 Part 2 섹션 id 리스트 (역링크용)


@dataclass
class PrerequisiteEntry:
    """part3_writer의 출력. Part 3의 실제 항목.

    topic에 대한 완성된 해설 + 역링크 정보.
    """
    topic: PrerequisiteTopic
    section_number: str                # "3.1", "3.2", ...
    subsections: list[ConceptNode] = field(default_factory=list)
    # 이 주제의 하위 항목들 (트리 구조)
    backlinks: list[str] = field(default_factory=list)
    # Part 2의 역링크 (all_mentions 와 동일하지만 편의상 복사)
