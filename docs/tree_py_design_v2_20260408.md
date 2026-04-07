# src/tree.py 설계 v2

## 1. 모듈 책임 (한 줄)

**개념 트리 노드(ConceptNode)의 데이터클래스를 정의하고, 프로그램 내부에서 빠르고 안전하게 생성/조회/직렬화할 수 있는 인터페이스를 제공.**

---

## 2. 공개 인터페이스

```python
from dataclasses import dataclass
from typing import Optional, Iterator

@dataclass
class ConceptNode:
    """개념 노드 정의"""
    # 모든 필드 정의 (아래 섹션 참고)

def iter_dfs(root: ConceptNode) -> Iterator[ConceptNode]:
    """루트부터 DFS로 모든 노드를 yield. id_map 불필요."""

def build_id_map(root: ConceptNode) -> dict[str, ConceptNode]:
    """id → ConceptNode 맵 생성.
    특정 id로 O(1) 조회가 필요한 경우에만 사용.
    일반 순회는 iter_dfs로 충분."""

def count_nodes(root: ConceptNode) -> int:
    """서브트리 노드 개수. id_map 불필요."""
```

---

## 3. 데이터클래스 구조: @dataclass 선택

### 결정: **@dataclass 사용** (v1에서 변경 없음)

### 분석 및 근거

| 측면 | Pydantic | @dataclass | 결론 |
|------|----------|-----------|------|
| **생성 성능** | 검증 오버헤드 | 거의 오버헤드 없음 | @dataclass |
| **필드 할당** | 선택적 검증 가능 | 검증 없음 | @dataclass |
| **메모리** | 약간 더 무거움 (메타데이터) | 가벼움 | @dataclass |
| **사용 사례** | 외부 입력 검증 필요 시 | 내부 자료구조 (검증 불필요) | @dataclass |
| **직렬화** | model_dump_json() 내장 | 별도 구현 (checkpoint.py) | 비슷 |
| **역직렬화** | model_validate_json() 내장 | 별도 구현 (checkpoint.py) | 비슷 |
| **의존성** | pydantic import 필요 | 표준 라이브러리만 | @dataclass |
| **레이어링** | "모든 모듈이 validation 가능" (복잡) | "tree는 pure data, validation은 각 모듈" (명확) | @dataclass |

### 최종 근거

1. **내부 자료구조 특성**: tree.py는 프로그램 내부에서만 생성되고, 외부 입력을 받지 않음 (expand/verify 로직이 값 검증 담당)
2. **성능**: 수백~수천 개 노드 생성 시 @dataclass가 더 효율적
3. **직렬화 책임 분리**: checkpoint.py가 직렬화/역직렬화를 담당하므로, tree.py는 "pure data container"로 유지
4. **의존성 최소화**: tree.py가 다른 모듈의 기초 레이어이므로, 표준 라이브러리만 사용

---

## 4. ConceptNode 필드 정의 (@dataclass)

```python
from dataclasses import dataclass, field
from typing import Optional, Literal
from uuid import uuid4

@dataclass
class ConceptNode:
    """개념 노드
    
    주의: 이 클래스는 순수 데이터 컨테이너.
    JSON 직렬화는 checkpoint.py에서 담당.
    검증은 각 생성 시점의 호출자가 담당.
    """
    
    # 기본 정보
    concept: str  # 개념 이름 (예: "신경망")
    source_excerpt: str  # 원문 관련 구절 (검증용, 예: "논문 p.5의 해당 구절...")
    explanation: str = ""  # 생성된 설명 (초기: 빈 문자열)
    
    # 트리 구조
    id: str = field(default_factory=lambda: uuid4().hex[:10])  # 고유 id (자동 생성)
    depth: int = 0  # 루트에서의 깊이
    parent_id: Optional[str] = None  # 부모 노드 id (루트면 None) — 문자열
    children: list["ConceptNode"] = field(default_factory=list)  # 자식 노드 객체 리스트
    
    # 노드 상태
    is_leaf: bool = False  # 학부 1학년 수준 도달 여부
    status: Literal["pending", "done", "duplicate", "verification_failed", "failed"] = "pending"
    
    # 중복/실패 추적
    duplicate_of: Optional[str] = None  # 중복 시 원본 노드 id
    failed_errors: Optional[list[dict]] = None  # 검증 실패 에러 목록
    
    # 검증 결과
    verification: dict = field(default_factory=dict)  # 검증 결과 저장
```

### 필드별 설명 (12개)

| 필드 | 타입 | 기본값 | 용도 |
|------|------|--------|------|
| `concept` | str | 필수 | 개념명 |
| `source_excerpt` | str | 필수 | 원문 참조 (오류 추적용) |
| `explanation` | str | "" | Claude의 설명 (초기 빈 문자열, 확장 시 채워짐) |
| `id` | str | uuid4.hex[:10] | 노드 고유 id (자동 생성) |
| `depth` | int | 0 | 루트부터의 깊이 |
| `parent_id` | str\|None | None | 부모 노드 id (루트면 None) |
| `children` | list[ConceptNode] | [] | **자식 노드 객체 리스트** |
| `is_leaf` | bool | False | leaf 판정 여부 |
| `status` | Literal | "pending" | pending/done/duplicate/verification_failed/failed |
| `duplicate_of` | str\|None | None | 중복 판정 시 원본 id |
| `failed_errors` | list[dict]\|None | None | 검증 실패 에러 기록 |
| `verification` | dict | {} | 검증 결과 저장 |

---

## 5. v1 → v2 보정 사항

### 보정 1: children 필드 타입을 `list[str]` → `list["ConceptNode"]`로 변경

#### 변경 이유

v1의 `children: list[str]` (id 리스트) 설계에는 4가지 실질적 문제가 있었다:

1. **디버깅 지옥**: `node.children[0]`이 문자열 `"abc123"`으로만 보여서 디버거에서 자식 탐색이 불가능
2. **모든 순회가 id_map 의존**: expander, verifier, assembler 전부 함수 시그니처에 `(node, id_map)`을 받아야 함
3. **id_map 동기화 버그 위험**: 노드 추가/삭제 시마다 id_map 갱신을 잊으면 사고
4. **객체지향 부자연스러움**: `for child in node.children:`로 자식 탐색 불가

#### v1에서 list[str]을 선택했던 근거 반박

| v1 주장 | 실제 |
|---------|------|
| "순환 참조로 GC 부하" | Python GC는 순환 참조를 처리함. 수백 노드 규모에서 측정 불가능한 차이 |
| "직렬화 복잡" | parent_id를 문자열로 두면 parent→children 한 방향만 객체 참조. 순환 자체가 발생하지 않음 |
| "JSON 변환 시 무한 루프" | children→parent 역참조가 없으므로 재귀 직렬화가 자연스럽게 종료됨 |

#### 참조 방향과 순환 참조 부재

```
parent (ConceptNode)
  └── children: [child_a, child_b]  ← 실제 ConceptNode 객체 참조
        │
        child_a.parent_id = "abc123"  ← 문자열 (역참조 끊음)
        child_b.parent_id = "abc123"  ← 문자열 (역참조 끊음)
```

- **parent → children**: 객체 참조 (한 방향)
- **children → parent**: `parent_id` 문자열 (역참조 끊김)
- **결과**: 순환 참조가 구조적으로 불가능

#### 직렬화가 간단해지는 이유

checkpoint.py가 구현할 직렬화 방식 (예시):

```python
def to_dict(node: ConceptNode) -> dict:
    return {
        "id": node.id,
        "concept": node.concept,
        "source_excerpt": node.source_excerpt,
        "explanation": node.explanation,
        "depth": node.depth,
        "parent_id": node.parent_id,  # 문자열, 그대로
        "children": [to_dict(c) for c in node.children],  # 재귀, 순환 없음
        "is_leaf": node.is_leaf,
        "status": node.status,
        "duplicate_of": node.duplicate_of,
        "failed_errors": node.failed_errors,
        "verification": node.verification,
    }
```

- `parent → children` 한 방향만 재귀함
- `children`에는 parent 객체 참조가 없어서 무한 루프 불가능
- id_map 없이도 트리 전체를 중첩 JSON으로 자연스럽게 표현

역직렬화도 대칭적:

```python
def from_dict(d: dict) -> ConceptNode:
    node = ConceptNode(
        concept=d["concept"],
        source_excerpt=d["source_excerpt"],
        explanation=d["explanation"],
        id=d["id"],
        depth=d["depth"],
        parent_id=d["parent_id"],
        is_leaf=d["is_leaf"],
        status=d["status"],
        duplicate_of=d.get("duplicate_of"),
        failed_errors=d.get("failed_errors"),
        verification=d.get("verification", {}),
    )
    node.children = [from_dict(c) for c in d.get("children", [])]
    return node
```

### 보정 2: `__post_init__` 제거

v1에서 빈 `__post_init__` + `pass`가 있었다. YAGNI 원칙 위반이므로 제거. 나중에 정말 필요해지면 그때 추가한다.

### 보정 3: 순회 헬퍼 재설계

children이 실제 객체가 되면서 순회 헬퍼의 성격이 근본적으로 달라진다.

#### v1 → v2 변경 대조

| v1 | v2 | 이유 |
|----|----|----|
| `build_id_map(root)` | `build_id_map(root)` | 유지. 특정 id로 O(1) 조회 필요할 때만 사용 |
| `get_descendants(node, id_map)` | **제거** | `list(iter_dfs(node))[1:]`로 대체 가능 |
| `count_nodes(node, id_map)` | `count_nodes(root)` | id_map 인자 제거. 직접 순회 |
| (없음) | `iter_dfs(root)` | **신규 추가**. 가장 기본적인 DFS 순회 |

#### 최종 순회 헬퍼 3개 시그니처

```python
from typing import Iterator

def iter_dfs(root: ConceptNode) -> Iterator[ConceptNode]:
    """루트부터 DFS(전위 순회)로 모든 노드를 yield.
    
    children이 실제 ConceptNode 객체이므로 id_map 불필요.
    expander, verifier, assembler 등 모든 모듈에서
    일반 순회 용도로 사용.
    
    사용 예:
        for node in iter_dfs(root):
            print(node.concept, node.depth)
    """

def build_id_map(root: ConceptNode) -> dict[str, ConceptNode]:
    """id → ConceptNode 맵 생성.
    
    특정 id로 O(1) 조회가 필요한 경우에만 사용.
    예: parent_id로 부모 노드를 찾을 때,
        duplicate_of로 원본 노드를 찾을 때.
    일반 순회는 iter_dfs로 충분.
    
    내부적으로 iter_dfs를 사용.
    """

def count_nodes(root: ConceptNode) -> int:
    """서브트리의 총 노드 개수 반환.
    
    id_map 불필요. 내부적으로 iter_dfs를 사용.
    """
```

#### 핵심 변화

- **id_map이 필수에서 부가 도구로 격하**: 일반 순회는 `iter_dfs`로 해결. id_map은 "특정 id로 O(1) 조회"가 필요한 특수 상황에서만 사용.
- **get_descendants 제거**: 필요하면 `list(iter_dfs(node))[1:]`로 대체. 별도 함수를 만들 정도로 자주 쓰이지 않음.
- **모든 헬퍼에서 id_map 인자 제거**: children이 객체이므로 id_map 없이 직접 순회 가능.

---

## 6. id 생성 전략 (v1에서 변경 없음)

### 선택: **uuid4().hex[:10]**

| 방식 | 충돌 | 체크포인트 재로드 | 디버깅 | 선택 |
|------|------|-----------------|--------|------|
| **uuid4 hex 앞 10자리** | 극히 드문 (~10^12 정도로 안전) | id 변하지 않음 | 무작위 하지만 고유 | 선택 |
| **전역 카운터** | 없음 | 재로드 후 카운터 동기화 어려움 | 순차적이라 좋음 | 탈락 |
| **부모id+인덱스** | 없음 | 일관성 유지 가능 | 계층 구조 명시적 | 탈락 (복잡) |

### 근거

1. **UUID 충돌 확률**: 2^40 (약 1조) 공간에서 수백~수천 노드는 거의 충돌 없음
2. **체크포인트 재로드**: id는 노드의 생성 시점에 고정되는 영구 식별자. 파일에서 로드 시 그대로 복원.
3. **간결함**: 10자리 hex는 짧으면서도 충분히 고유

---

## 7. 부모-자식 링크 관리 (v2 최종)

### 결정: **children = list[ConceptNode] (실제 객체), parent_id = str (문자열)**

| 방향 | 타입 | 참조 방식 |
|------|------|----------|
| parent → children | `list[ConceptNode]` | 객체 참조 (직접 순회 가능) |
| child → parent | `parent_id: str` | 문자열 id (역참조 끊음) |

### 이 구조의 이점

1. **순환 참조 구조적 불가능**: 한 방향만 객체 참조, 역방향은 문자열
2. **직렬화 단순**: 재귀 to_dict/from_dict로 자연스럽게 중첩 JSON 생성
3. **id_map 불필요한 순회**: `for child in node.children:` 바로 사용
4. **디버깅 편의**: 디버거에서 자식 노드의 모든 필드를 즉시 확인 가능
5. **시그니처 간소화**: expander, verifier, assembler 모두 `(node, id_map)` 대신 `(node)`만으로 충분

---

## 8. 각 모듈이 자기 순회 로직을 가지는 이유 (v1에서 변경 없음)

1. **expander.py**: "확장 순회" (특정 조건의 노드만 확장) → 고유 로직 필요
2. **verifier.py**: "검증 순회" (특정 status의 노드만 검증) → 고유 로직 필요
3. **assembler.py**: "렌더링 순회" (중복/실패 노드를 특별 처리) → 고유 로직 필요

순회 자체가 비즈니스 로직과 섞여있으므로, tree.py는 "raw traverse"만 제공.

---

## 최종 설계 정리

| 항목 | v1 | v2 | 변경 이유 |
|------|----|----|----------|
| **데이터 타입** | @dataclass | @dataclass | 변경 없음 |
| **의존성** | 표준 라이브러리만 | 표준 라이브러리만 | 변경 없음 |
| **id 생성** | uuid4().hex[:10] | uuid4().hex[:10] | 변경 없음 |
| **필드 개수** | 12개 | 12개 | 변경 없음 |
| **children** | list[str] (id만) | **list[ConceptNode] (실제 객체)** | 디버깅/순회/시그니처 개선 |
| **parent_id** | str\|None (단방향) | str\|None (단방향) | 변경 없음 — 역참조 끊는 핵심 |
| **__post_init__** | 빈 메서드 존재 | **제거** | YAGNI |
| **순회 헬퍼** | build_id_map, get_descendants, count_nodes (전부 id_map 의존) | **iter_dfs, build_id_map, count_nodes (id_map 불필요)** | children 객체화로 근본 변경 |
| **직렬화** | checkpoint.py가 담당 | checkpoint.py가 담당 | 변경 없음 — 재귀 to_dict/from_dict로 더 간단해짐 |

---

**설계 일시:** 2026-04-08  
**버전:** v2 (3가지 보정 반영)  
**상태:** 검토 대기 중
