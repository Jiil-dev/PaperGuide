# 단일 책임: 개념 트리 노드(ConceptNode) 데이터클래스와 기본 순회 헬퍼 정의
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Literal, Optional
from uuid import uuid4


@dataclass
class ConceptNode:
    """개념 노드

    이 클래스는 순수 데이터 컨테이너.
    JSON 직렬화는 checkpoint.py에서 담당.
    검증은 각 생성 시점의 호출자가 담당.
    """

    # 기본 정보
    concept: str  # 개념 이름 (예: "신경망")
    source_excerpt: str  # 원문 관련 구절 (검증용)
    explanation: str = ""  # 생성된 설명 (초기: 빈 문자열)

    # 트리 구조
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    depth: int = 0
    parent_id: Optional[str] = None  # 부모 노드 id (루트면 None) — 문자열
    children: list[ConceptNode] = field(default_factory=list)  # 자식 노드 객체 리스트

    # 노드 상태
    is_leaf: bool = False  # 학부 1학년 수준 도달 여부
    status: Literal["pending", "done", "duplicate", "verification_failed", "failed"] = "pending"

    # 중복/실패 추적
    duplicate_of: Optional[str] = None  # 중복 시 원본 노드 id
    failed_errors: Optional[list[dict]] = None  # 검증 실패 에러 목록

    # 검증 결과
    verification: dict = field(default_factory=dict)


def iter_dfs(root: ConceptNode) -> Iterator[ConceptNode]:
    """루트부터 DFS(전위 순회)로 모든 노드를 yield.

    children이 실제 ConceptNode 객체이므로 id_map 불필요.
    expander, verifier, assembler 등 모든 모듈에서
    일반 순회 용도로 사용.

    사용 예:
        for node in iter_dfs(root):
            print(node.concept, node.depth)
    """
    yield root
    for child in root.children:
        yield from iter_dfs(child)


def build_id_map(root: ConceptNode) -> dict[str, ConceptNode]:
    """id → ConceptNode 맵 생성.

    특정 id로 O(1) 조회가 필요한 경우에만 사용.
    예: parent_id로 부모 노드를 찾을 때,
        duplicate_of로 원본 노드를 찾을 때.
    일반 순회는 iter_dfs로 충분.

    사용 예:
        id_map = build_id_map(root)
        parent = id_map[node.parent_id]
    """
    return {node.id: node for node in iter_dfs(root)}


def count_nodes(root: ConceptNode) -> int:
    """서브트리의 총 노드 개수 반환.

    id_map 불필요. 내부적으로 iter_dfs를 사용.

    사용 예:
        total = count_nodes(root)
        print(f"트리에 {total}개 노드")
    """
    return sum(1 for _ in iter_dfs(root))
