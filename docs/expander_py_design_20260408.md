# src/expander.py 설계

## 1. 모듈 책임 (한 줄)

**ConceptNode 트리를 DFS로 재귀 확장한다. 각 pending 노드에 대해 Claude로 explanation + children을 생성하고, verifier로 검증하며, concept_cache로 중복을 차단하고, on_node_done 콜백으로 진행 상황을 알린다.**

---

## 2. Expander 클래스 시그니처 + 내부 상태

### 생성자

```python
from typing import Callable
from src.tree import ConceptNode
from src.claude_client import ClaudeClient
from src.verifier import Verifier
from src.concept_cache import ConceptCache

class Expander:
    def __init__(
        self,
        client: ClaudeClient,
        verifier: Verifier,
        cache: ConceptCache,
        max_depth: int = 4,
        max_children_per_node: int = 5,
        max_retries: int = 1,
        on_node_done: Callable[[ConceptNode], None] | None = None,
    ):
        """트리 확장기.

        Args:
            client: ClaudeClient 인스턴스.
            verifier: Verifier 인스턴스.
            cache: ConceptCache 인스턴스.
            max_depth: 최대 트리 깊이. 이 이상은 leaf로 강제.
            max_children_per_node: 새 자식 생성 시 최대 개수.
            max_retries: 검증 실패 시 재시도 횟수 (0이면 재시도 없음).
            on_node_done: 노드 확장 완료 시 호출되는 콜백.
        """
```

### 내부 상태

| 필드 | 타입 | 설명 |
|------|------|------|
| `_client` | ClaudeClient | Claude 호출 래퍼 |
| `_verifier` | Verifier | 검증기 |
| `_cache` | ConceptCache | 중복/순환 캐시 |
| `_max_depth` | int | 최대 깊이 (기본 4) |
| `_max_children` | int | 새 자식 최대 개수 (기본 5) |
| `_max_retries` | int | 검증 실패 재시도 (기본 1) |
| `_on_node_done` | Callable \| None | 콜백 |

checkpoint 모듈은 import하지 않음 (HANDOFF.md §3-1 항목 6).

---

## 3. expand() 메서드 전체 흐름

```python
def expand(self, root: ConceptNode, ancestor_path: list[str] | None = None) -> None:
    """root와 그 하위를 DFS로 재귀 확장한다. 트리를 in-place 수정.

    Args:
        root: 확장할 루트 노드.
        ancestor_path: 현재 노드까지의 조상 concept 이름 리스트.
            순환 감지에 사용. 최초 호출 시 None → 빈 리스트로 초기화.
    """
```

### pseudo-code (상세)

```
expand(node, ancestor_path=[]):
    # === 가드 체크 ===
    if node.status != "pending":
        return  # 이미 처리된 노드 (체크포인트 재개 시)

    # 1. 깊이 초과 → leaf로 강제
    if node.depth >= max_depth:
        node.is_leaf = True
        node.status = "done"
        _notify(node)
        return

    # 2. 조상 경로 순환 체크
    if cache.check_ancestor_cycle(node.concept, ancestor_path):
        node.status = "duplicate"
        node.duplicate_of = "ancestor-cycle"
        _notify(node)
        return

    # 3. 캐시 중복 체크 (해시 + 임베딩)
    dup_id = cache.lookup(node.concept, brief=node.source_excerpt[:200])
    if dup_id is not None:
        node.status = "duplicate"
        node.duplicate_of = dup_id
        _notify(node)
        return

    # === Claude 호출 + 검증 루프 ===
    # chunker가 이미 자식을 만들었는가?
    has_existing_children = len(node.children) > 0
    allow_new_children = not has_existing_children

    previous_errors = None
    last_explanation = ""

    try:
        for attempt in range(max_retries + 1):
            # Claude 호출
            result = _call_expand(node, allow_new_children, previous_errors)
            node.explanation = result["explanation"]
            last_explanation = result["explanation"]

            if result.get("is_leaf", False):
                node.is_leaf = True

            # 새 자식 생성 (chunker 기존 자식이 없을 때만)
            if allow_new_children and not node.is_leaf:
                new_children = result.get("children", [])[:max_children]
                for child_data in new_children:
                    child = ConceptNode(
                        concept=child_data["name"],
                        source_excerpt=child_data.get("brief", ""),
                        depth=node.depth + 1,
                        parent_id=node.id,
                    )
                    node.children.append(child)

            # 검증
            verify_result = verifier.verify(node)
            node.verification = verify_result

            if verify_result["passed_final"]:
                node.status = "done"
                break
            else:
                previous_errors = verify_result.get("errors", [])

        else:
            # max_retries 소진
            node.status = "verification_failed"
            node.failed_errors = previous_errors
            node.explanation = last_explanation  # 마지막 시도 유지

    except RateLimitExceeded:
        raise  # 상위로 전파 (main.py가 처리)

    except Exception as e:
        node.status = "failed"
        node.failed_errors = [{"category": "runtime", "description": str(e)}]
        _notify(node)
        return  # 자식 확장 중단

    # === 캐시 등록 ===
    cache.add(node.id, node.concept, brief=node.source_excerpt[:200])

    # === 콜백 (노드 자체 완료) ===
    _notify(node)

    # === 자식 재귀 확장 ===
    child_path = ancestor_path + [node.concept]
    for child in node.children:
        expand(child, child_path)

    # === 콜백 (자식 확장 완료 후 — 상태 업데이트 반영) ===
    _notify(node)
```

---

## 4. _call_expand 내부 로직과 system_prompt

### system_prompt 전문

```python
_SYSTEM_PROMPT = """\
당신은 AI 논문 해설서의 저자입니다.
주어진 개념을 목표 독자가 완벽히 이해할 수 있도록 설명하십시오.

## 목표 독자
고등학교 수학2(미적분 기초), 물리1, 기초 프로그래밍을 이수한 대학교 1학년.
선형대수, 확률론, 머신러닝, 딥러닝 지식은 전혀 없습니다.

## 작성 규칙
1. **전문 용어 풀어쓰기**: 전문 용어가 처음 등장하면 반드시 괄호 안에
   학부 1학년이 이해할 수 있는 풀이를 병기하십시오.
   예: "softmax(각 값을 0~1 사이 확률로 변환하는 함수)"

2. **원문 충실**: source_excerpt에 없는 정보를 지어내지 마십시오.
   배경 지식이 필요하면 children에 별도 개념으로 분리하십시오.

3. **자기충족 설명**: 설명은 다른 섹션을 참조하지 않고 독립적으로
   이해할 수 있어야 합니다.

4. **수식 보존**: 원문의 수식은 LaTeX 형식 그대로 유지하십시오.

5. **leaf 판정**: 이 개념이 목표 독자가 추가 설명 없이 바로 이해할 수
   있는 수준이면 is_leaf=true로 판정하십시오.

6. **children 생성**: is_leaf=false인 경우, 이 개념을 이해하기 위해
   필요한 선행 개념을 children에 나열하십시오.
   각 child는 name(개념명)과 brief(한 줄 설명)를 포함합니다.

반드시 지정된 JSON 형식으로만 응답하십시오.\
"""
```

### _call_expand 로직

```python
def _call_expand(self, node, allow_new_children, previous_errors=None):
    user_prompt = _build_user_prompt(node, allow_new_children, previous_errors)
    schema = _EXPAND_SCHEMA if allow_new_children else _EXPAND_SCHEMA_NO_CHILDREN

    result = self._client.call(
        user_prompt=user_prompt,
        system_prompt=_SYSTEM_PROMPT,
        json_schema=schema,
    )
    return result
```

---

## 5. user_prompt 템플릿

### 첫 호출용

```python
_USER_PROMPT_TEMPLATE = """\
다음 개념에 대한 설명을 생성해 주세요.

## 개념 이름
{concept}

## 원문 (source_excerpt)
{source_excerpt}

## 현재 트리 깊이
{depth} (최대 {max_depth})

{children_instruction}

위 규칙에 따라 JSON으로 응답하세요.\
"""
```

`children_instruction` 분기:
- `allow_new_children=True`:
  ```
  ## 하위 개념 생성
  이 개념을 이해하기 위해 필요한 선행 개념이 있다면 children에 나열하세요.
  목표 독자가 이미 알 것으로 기대되는 기초 개념은 제외하세요.
  더 이상 분해가 필요 없으면 is_leaf=true, children=[]로 응답하세요.
  ```
- `allow_new_children=False`:
  ```
  ## 하위 개념
  이 개념의 하위 구조는 이미 정해져 있습니다. children=[]로 응답하세요.
  explanation만 생성하면 됩니다.
  ```

### 재시도용 (previous_errors 추가)

```python
_RETRY_SECTION = """\

## 이전 시도의 문제점
{error_list}

위 문제를 수정하여 다시 생성해 주세요.\
"""
```

`error_list` 형식:
```
- [faithfulness] 원문에 없는 scaling 이유를 추가함
- [level] softmax 용어를 풀어쓰지 않음
```

---

## 6. JSON schema 전체

### allow_new_children=True

```python
_EXPAND_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "목표 독자 수준의 한국어 설명"
        },
        "is_leaf": {
            "type": "boolean",
            "description": "더 이상 분해 불필요 시 true"
        },
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "하위 개념 이름"},
                    "brief": {"type": "string", "description": "한 줄 설명"}
                },
                "required": ["name", "brief"]
            },
            "description": "이해에 필요한 선행 개념 리스트"
        }
    },
    "required": ["explanation", "is_leaf", "children"]
}
```

### allow_new_children=False

```python
_EXPAND_SCHEMA_NO_CHILDREN = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "목표 독자 수준의 한국어 설명"
        },
        "is_leaf": {
            "type": "boolean",
            "description": "더 이상 분해 불필요 시 true"
        },
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "brief": {"type": "string"}
                },
                "required": ["name", "brief"]
            },
            "description": "이미 하위 구조가 있으므로 빈 배열로 응답"
        }
    },
    "required": ["explanation", "is_leaf", "children"]
}
```

두 schema의 구조는 동일. 차이는 user_prompt의 지시 텍스트에서만 발생. schema를 분리하는 이유: 캐시 해시가 schema를 포함하므로, allow_new_children 여부에 따라 캐시를 구분해야 함.

---

## 7. chunker 기존 자식 vs expander 새 자식 구분

| 상황 | 판정 | 동작 |
|------|------|------|
| `node.children` 비어있음 | 새 자식 생성 허용 | allow_new_children=True. Claude가 children 반환. 최대 max_children개. |
| `node.children` 비어있지 않음 | chunker가 이미 만든 자식 | allow_new_children=False. Claude에게 children=[] 지시. explanation만 생성. 기존 자식 순회 재귀. |

chunker가 만든 자식은 논문의 원래 섹션 구조. expander가 만든 자식은 이해를 위해 분해한 하위 개념. 두 유형이 동일한 ConceptNode이지만, 생성 경로가 다름.

---

## 8. 상태 전이 다이어그램

```
              ┌─────────────┐
              │   pending    │  ← 초기 상태
              └──────┬───────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  ┌──────────┐ ┌──────────┐ ┌──────────────┐
  │ duplicate │ │  depth   │ │ Claude 호출  │
  │           │ │  ≥ max   │ │ + 검증 루프  │
  └──────────┘ └────┬─────┘ └──────┬───────┘
                    │              │
                    ▼        ┌─────┴─────┐
              ┌──────────┐   │           │
              │   done   │   ▼           ▼
              │ (is_leaf)│ passed?    retries
              └──────────┘   │        exhausted?
                             ▼           ▼
                       ┌──────────┐ ┌───────────────────┐
                       │   done   │ │ verification_failed│
                       └──────────┘ └───────────────────┘

  예외 발생 시:
              ┌──────────┐
              │  failed   │  ← RuntimeError, ValueError 등
              └──────────┘
```

---

## 9. 가드 체크 순서와 근거

```
1. depth ≥ max_depth    → 가장 저렴 (비교 1회)
2. ancestor cycle       → 저렴 (문자열 비교 N회, N=조상 수)
3. cache lookup         → 약간 비쌈 (해시 O(1) + 임베딩 O(N))
```

비용이 낮은 순서대로 체크. 깊이 초과나 순환은 임베딩 계산 없이 즉시 판정 가능.

---

## 10. 재시도 프롬프트 증분

첫 호출 실패 후 previous_errors가 있으면 user_prompt 끝에 추가:

```
## 이전 시도의 문제점
- [faithfulness] 원문에 없는 scaling 이유를 추가함
- [level] softmax 용어를 풀어쓰지 않음

위 문제를 수정하여 다시 생성해 주세요.
```

재시도 시에도 같은 schema를 사용하므로, 캐시 해시는 user_prompt가 바뀌어 자동으로 달라짐 → 이전 캐시가 재사용되지 않음.

---

## 11. 에러 처리

### RateLimitExceeded

```python
except RateLimitExceeded:
    raise  # 상위로 전파. main.py가 잡아서 체크포인트 저장 후 종료.
```

재시도 불가. 즉시 전파.

### 개별 노드 실패 (RuntimeError, ValueError 등)

```python
except Exception as e:
    node.status = "failed"
    node.failed_errors = [{"category": "runtime", "description": str(e)}]
    _notify(node)
    return  # 이 노드의 자식 확장 중단, 상위는 계속
```

한 노드의 실패가 전체 트리 확장을 중단시키지 않음. 해당 서브트리만 건너뜀.

---

## 12. 콜백 on_node_done 호출 타이밍

| 시점 | 호출 | 이유 |
|------|------|------|
| 가드 체크 실패 (duplicate, depth) | 1회 | 노드 상태가 확정됨 |
| Claude 호출 + 검증 완료 | 1회 | explanation이 채워짐 |
| 개별 노드 실패 (exception) | 1회 | failed 상태 확정 |
| 모든 자식 확장 완료 후 | 1회 | 자식 상태가 반영됨 |

노드당 최대 2회 호출 (자체 완료 + 자식 완료). main.py의 체크포인트 콜백은 매 호출 시 전체 트리를 저장하므로, 빈번한 호출은 안전장치 역할.

```python
def _notify(self, node: ConceptNode) -> None:
    if self._on_node_done is not None:
        self._on_node_done(node)
```

---

## 13. 외부 의존성

### 생성자 주입

| 인스턴스 | 모듈 |
|---------|------|
| ClaudeClient | src.claude_client |
| Verifier | src.verifier |
| ConceptCache | src.concept_cache |

### import

| 모듈 | 용도 |
|------|------|
| src.tree.ConceptNode | 노드 타입 |
| src.claude_client.RateLimitExceeded | 예외 전파용 |
| typing.Callable | 콜백 타입 |

### 절대 금지

- checkpoint 모듈 import
- config 모듈 import
- anthropic, httpx, requests import

---

## 14. 테스트 전략

### 단계별

1. **dry_run** (할당량 0):
   - 간단한 2레벨 트리 (루트 1개 + 기존 자식 2개) 생성
   - `expand(root)` 실행
   - 모든 노드가 verification_failed가 되는지 확인 (dry_run은 항상 검증 실패)
   - 상태 전이, 콜백 호출 횟수, depth 갱신 확인

2. **작은 서브트리, cache 모드** (사용자 허락):
   - Attention 논문의 한 섹션(예: "Scaled Dot-Product Attention")만 잘라서 확장
   - 1~2 depth만 확장하고 결과 관찰
   - 캐시 히트 확인

3. **전체 트리** (나중 단계):
   - 전체 Attention 논문 chunker 결과로 확장
   - 호출 수 모니터링 (max_total_calls=500 이내)

---

## 15. 가장 까다로운 부분

### ① 검증 실패 재시도 시 자식 노드 초기화

첫 시도에서 children이 생성됐는데 검증 실패 → 재시도에서 children이 또 생성되면 중복됨.

**해결**: 재시도 전에 `node.children = []`로 초기화. 재시도에서 새 children을 받으면 기존 것을 교체.

단, `allow_new_children=False`인 경우(chunker 기존 자식)는 children을 건드리지 않음 — explanation만 재생성.

### ② 콜백 호출과 체크포인트의 일관성

`_notify(node)` 후 main.py가 체크포인트를 저장. 이때 트리의 일부 노드는 "pending"이고 일부는 "done"일 수 있음. 체크포인트 재로드 후 `expand()`를 다시 호출하면, `node.status != "pending"` 가드가 이미 처리된 노드를 건너뜀 → 재개 가능.

핵심은 `expand()` 최상단의 `if node.status != "pending": return` 가드.

### ③ 깊이 계산의 일관성

chunker가 만든 노드는 `depth=0,1,2`. expander가 만든 자식은 `parent.depth + 1`. max_depth=4이면 depth 4 이상에서 leaf로 강제. 하지만 chunker가 이미 depth=2인 노드를 만들었으면, expander는 depth=3,4까지만 확장 가능 (2개 레벨). 이는 의도된 동작 — 논문 원래 구조가 깊을수록 확장 여유가 줄어듦.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
