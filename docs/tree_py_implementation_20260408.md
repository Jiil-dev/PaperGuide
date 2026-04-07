# tree.py 구현 결과

## 1. 작성된 코드 (src/tree.py 전체)

```python
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
```

## 2. 검증 결과

### 2-1. import 테스트

```
$ python -c "from src.tree import ConceptNode, iter_dfs, build_id_map, count_nodes; print('import OK')"
import OK
```

### 2-2. 종합 기능 테스트

```
$ python -c "
from src.tree import ConceptNode, iter_dfs, build_id_map, count_nodes
root = ConceptNode(concept='root', source_excerpt='origin')
child1 = ConceptNode(concept='child1', source_excerpt='c1', depth=1, parent_id=root.id)
child2 = ConceptNode(concept='child2', source_excerpt='c2', depth=1, parent_id=root.id)
grand = ConceptNode(concept='grand', source_excerpt='g', depth=2, parent_id=child1.id)
root.children = [child1, child2]
child1.children = [grand]
names = [n.concept for n in iter_dfs(root)]
print('iter_dfs:', names)
print('count:', count_nodes(root))
id_map = build_id_map(root)
print('id_map keys:', len(id_map))
parent_of_grand = id_map[grand.parent_id]
print('grand parent:', parent_of_grand.concept)
"

iter_dfs: ['root', 'child1', 'grand', 'child2']
count: 4
id_map keys: 4
grand parent: child1
```

## 3. 구현 중 주의했던 점

1. **`from __future__ import annotations` 적용**: 파일 최상단에 추가하여 `list[ConceptNode]` 타입 힌트가 forward reference 없이 동작하도록 함. 이로써 `list["ConceptNode"]` 대신 `list[ConceptNode]`으로 깔끔하게 표기.

2. **`failed_errors` 기본값 `None` 유지**: `field(default_factory=list)`가 아닌 `None`으로 설정. "아직 실패 기록 없음"(`None`)과 "검증을 거쳤으나 에러 없음"(`[]`)을 의미적으로 구분하기 위함.

3. **`iter_dfs`는 순수 제너레이터**: `yield root` + `yield from iter_dfs(child)` 패턴으로 구현. 중간에 리스트로 모아두지 않아 메모리 효율적이고, 호출자가 조기 종료(`break`)할 수 있음.

4. **`build_id_map`과 `count_nodes`는 `iter_dfs` 재사용**: 동일한 DFS 로직을 중복 구현하지 않고 `iter_dfs`를 내부적으로 호출. 단일 진실 원천(single source of truth) 유지.

5. **`__post_init__` 미포함**: v2 설계의 보정 2에 따라 빈 메서드 제거. YAGNI 원칙 준수.

6. **순환 참조 구조적 불가능 확인**: `children`은 `list[ConceptNode]` 객체 참조, `parent_id`는 `str` 문자열. parent→children 한 방향만 객체 참조이므로 직렬화 시 무한 루프 불가능.
