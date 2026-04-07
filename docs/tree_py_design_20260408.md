# src/tree.py 설계

## 1. 모듈 책임 (한 줄)

**개념 트리 노드(ConceptNode)의 데이터클래스를 정의하고, 프로그램 내부에서 빠르고 안전하게 생성/조회/직렬화할 수 있는 인터페이스를 제공.**

---

## 2. 공개 인터페이스

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ConceptNode:
    """개념 노드 정의"""
    # 모든 필드 정의 (아래 섹션 참고)

def generate_node_id() -> str:
    """고유 노드 id 자동 생성"""

def build_id_map(root: ConceptNode) -> dict[str, ConceptNode]:
    """트리를 DFS로 순회하며 id → node 맵 생성 (checkpoint 재로드 시 사용)"""

def get_descendants(node: ConceptNode, id_map: dict[str, ConceptNode]) -> list[ConceptNode]:
    """노드의 모든 후손 노드 반환 (DFS 순회용 헬퍼)"""

def count_nodes(node: ConceptNode, id_map: dict[str, ConceptNode]) -> int:
    """트리의 총 노드 개수 계산"""
```

---

## 3. 데이터클래스 구조: @dataclass 선택

### 결정: **@dataclass 사용 권장**

### 분석 및 근거

| 측면 | Pydantic | @dataclass | 결론 |
|------|----------|-----------|------|
| **생성 성능** | 검증 오버헤드 (v2는 完化o 개선) | 거의 오버헤드 없음 | ✅ @dataclass |
| **필드 할당** | ConfigDict(validate_assignment=False) 기본이지만 선택적 검증 가능 | 검증 없음 | ✅ @dataclass |
| **메모리** | 약간 더 무거움 (메타데이터) | 가벼움 | ✅ @dataclass |
| **사용 사례** | 외부 입력 검증 필요 시 | 내부 자료구조 (검증 불필요) | ✅ @dataclass |
| **직렬화** | model_dump_json() 내장 | 별도 구현 (json.dumps + custom encoder) | ✅ 비슷 |
| **역직렬화** | model_validate_json() 내장 | 별도 구현 (json.loads + constructor) | ✅ 비슷 |
| **순환 참조** | 복잡 (exclude 옵션 필요) | 단순 (id만 저장하면 됨) | ✅ @dataclass |
| **의존성** | pydantic import 필요 | 표준 라이브러리만 | ✅ @dataclass |
| **레이어링** | "모든 모듈이 validation 가능" (복잡) | "tree는 pure data, validation은 각 모듈" (명확) | ✅ @dataclass |

### 최종 근거

1. **내부 자료구조 특성**: tree.py는 프로그램 내부에서만 생성되고, 외부 입력을 받지 않은 (expand/verify 로직이 값 검증 담당)
2. **성능**: 수백~수천 개 노드 생성 시 @dataclass가 더 효율적
3. **직렬화 책임 분리**: checkpoint.py가 직렬화/역직렬화를 담당하므로, tree.py는 "pure data container"로 유지
4. **의존성 최소화**: tree.py가 다른 모듈의 기초 레이어이므로, 표준 라이브러리만 사용

### Pydantic이 필요한 경우는 언제인가?

외부 입력(config.yaml, CLI args) 검증용. tree.py는 해당 없음.

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
    parent_id: Optional[str] = None  # 부모 노드 id (루트면 None)
    children: list[str] = field(default_factory=list)  # 자식 노드 id 리스트
    
    # 노드 상태
    is_leaf: bool = False  # 학부 1학년 수준 도달 여부
    status: Literal["pending", "done", "duplicate", "verification_failed", "failed"] = "pending"
    
    # 중복/실패 추적
    duplicate_of: Optional[str] = None  # 중복 시 원본 노드 id
    failed_errors: Optional[list[dict]] = None  # 검증 실패 에러 목록
    
    # 검증 결과
    verification: dict = field(default_factory=dict)  # 검증 결과 저장
    
    def __post_init__(self):
        """객체 생성 후 부작용 처리 (필요하면)"""
        # 아직은 특별한 검증 불필요 (각 모듈에서 담당)
        pass
```

### 필드별 설명

| 필드 | 타입 | 기본값 | 용도 |
|------|------|--------|------|
| `concept` | str | ❌ 필수 | 개념명 |
| `source_excerpt` | str | ❌ 필수 | 원문 참조 (오류 추적용) |
| `explanation` | str | "" | Claude의 설명 (초기 빔, 확장 시 채워짐) |
| `id` | str | uuid4.hex[:10] | 노드 고유id (자동 생성) |
| `depth` | int | 0 | 루트부터의 깊이 |
| `parent_id` | str\|None | None | 부모 노드 id (루트면 None) |
| `children` | list[str] | [] | 자식 노드 id 리스트 |
| `is_leaf` | bool | False | leaf 판정 여부 |
| `status` | Literal | "pending" | pending→done→duplicate/verification_failed/failed |
| `duplicate_of` | str\|None | None | 중복 판정 시 원본 id |
| `failed_errors` | list[dict]\|None | None | 검증 실패 에러 기록 |
| `verification` | dict | {} | 검증 결과 저장 |

---

## 5. id 생성 전략

### 선택: **uuid4().hex[:10]**

### 각 방식 비교

| 방식 | 충돌 | 체크포인트 재로드 | 디버깅 | 선택 |
|------|------|-----------------|--------|------|
| **uuid4 hex 앞 10자리** | 극히 드문 (~10^12 정도로 안전) | id 변하지 않음 ✅ | 무작위 하지만 고유 | ✅ 선택 |
| **전역 카운터** | 없음 | 재로드 후 카운터 동기화 어려움 ❌ | 순차적이라 좋음 | ❌ 탈락 |
| **부모id+인덱스** (예: "root_3_2") | 없음 | 일관성 유지 가능 | 계층 구조 명시적 | △ 너무 복잡 |

### 최종 선택 근거

1. **UUID 충돌 확률**: 2^40 (약 1조) 공간에서 수백~수천 노드는 거의 충돌 없음
2. **체크포인트 재로드**: uuid는 비결정적이지만, "id는 노드의 영구 식별자"로 간주하면 문제 없음
   - 파일에서 로드 후 id 맵을 재구성 (checkpoint.py의 역할)
3. **간결함**: 10자리 hex는 짧으면서도 충분히 고유
4. **다른 모듈과의 호환성**: 문자열이므로 어디서나 사용 가능

---

## 6. 부모-자식 링크 관리

### 선택: **children은 list[str] (id 리스트만), parent_id는 단방향**

### 각 방식 비교

#### Option A: children = list[ConceptNode] (실제 객체)

**장점:**
- 순회 편함: `for child in node.children`로 바로 접근
- 메모리: 참조만 저장, 복제 없음

**단점:**
- 순환 참조: child.parent_id → parent, parent.children → [child] 순환
- 직렬화 복잡: JSON 변환 시 exclude 옵션 필요 (Pydantic, 또는 커스텀 encoder)
- 메모리: 큰 트리에서 순환 참조로 GC 부하 증가 가능

#### Option B: children = list[str] (id 리스트만)

**장점:**
- 순환 참조 없음: parent_id만 역참조, children은 id만 저장
- 직렬화 단순: JSON에서 그냥 문자열 리스트 → 직렬화 간단
- 메모리: 참조 그래프 단순 (부모→자식 단방향)

**단점:**
- 순회 시 id → node 해석 필요 (id_map 필요)
- 약간의 조회 오버헤드: `id_map[child_id]`

### 최종 선택 근거

**Option B 선택** (children = list[str])

1. **직렬화 간단**: checkpoint.py에서 JSON 변환 시 복잡성 낮음
2. **순환 참조 회피**: GC 부하 없음, 메모리 누수 가능성 제거
3. **명확한 책임 분리**: tree.py는 id 기반 DAG, checkpoint.py는 id → node 매핑 관리
4. **성능**: 순회 헬퍼(id_map) 매번 생성하므로 O(1) 조회

### parent_id는 단방향만 유지

역참조(자식들을 찾기)는 checkpoint 재로드 시 미리 id_map을 구성할 때만 필요 → 런타임에 자주 필요 없음.

---

## 7. 순회 함수 필요성

### 선택: **tree.py에 간단한 헬퍼 2개만, 복잡한 순회는 각 모듈이 구현**

### 제공할 헬퍼

```python
def build_id_map(root: ConceptNode) -> dict[str, ConceptNode]:
    """트리를 DFS로 순회하며 id → node 맵 생성.
    
    checkpoint에서 재로드할 때 id 기반 링크를 복구하는 데 사용.
    런타임에도 언제든 호출 가능.
    """

def get_descendants(node: ConceptNode, id_map: dict[str, ConceptNode]) -> list[ConceptNode]:
    """노드의 모든 후손 노드 반환 (DFS)"""

def count_nodes(node: ConceptNode, id_map: dict[str, ConceptNode]) -> int:
    """서브트리 노드 개수 계산"""
```

### 각 모듈이 자기 순회 로직을 가지는 이유

1. **expander.py**: "확장 순회" (특정 조건의 노드만 확장) → 고유 로직 필요
2. **verifier.py**: "검증 순회" (특정 status의 노드만 검증) → 고유 로직 필요
3. **assembler.py**: "렌더링 순회" (중복/실패 노드를 특별 처리) → 고유 로직 필요

순회 자체가 비즈니스 로직과 섞여있으므로, tree.py는 "raw traverse"만 제공.

---

## 8. 가장 까다로울 것 같은 부분

### ① 순환 참조 방지와 직렬화

**문제:**
- Option A (children = list[ConceptNode])를 선택하면 parent ↔ child 순환 참조 발생
- JSON 직렬화 시 무한 루프 가능

**해결책:**
- Option B (children = list[str])로 선택해서 순환 참조 제거
- 재로드 시 checkpoint에서 id → node 맵 구성

### ② id 유일성과 비결정성의 균형

**문제:**
- uuid4는 비결정적 (재로드해도 같은 id 유지 안 됨)
- 하지만 전역 카운터는 체크포인트 재로드 후 동기화 어려움

**해결책:**
- "id는 노드의 생성 시점에 고정되는 영구 식별자"로 정의
- 체크포인트 파일에 id를 저장하고, 재로드 시 그 id를 그대로 사용
- 따라서 비결정적인 uuid4도 문제없음

---

## 최종 설계 정리

| 항목 | 결정 |
|------|------|
| **데이터 타입** | @dataclass (Pydantic 아님) |
| **의존성** | 표준 라이브러리만 (pathlib, uuid, dataclasses, typing) |
| **id 생성** | uuid4().hex[:10] |
| **children** | list[str] (id만 저장) |
| **parent_id** | str\|None (단방향) |
| **순회 헬퍼** | build_id_map, get_descendants, count_nodes |
| **직렬화** | checkpoint.py가 담당 |

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
