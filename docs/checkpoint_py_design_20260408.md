# src/checkpoint.py 설계

## 1. 모듈 책임 (한 줄)

**ConceptNode 트리 전체를 JSON 파일로 직렬화/역직렬화한다. 세션 중단 시 복구 지점으로 사용.**

---

## 2. 공개 API 3개

```python
from pathlib import Path
from src.tree import ConceptNode

CHECKPOINT_VERSION = "1"

def save(roots: list[ConceptNode], checkpoint_path: Path) -> None:
    """루트 리스트 전체를 JSON 파일로 저장한다.
    
    원자적 쓰기: .tmp에 먼저 쓰고, 성공하면 rename.
    """

def load(checkpoint_path: Path) -> list[ConceptNode]:
    """JSON 파일에서 루트 리스트를 복원한다.
    
    Raises:
        FileNotFoundError: 파일 없음.
        ValueError: JSON 형식 오류 또는 필수 필드 누락.
    """

def exists(checkpoint_path: Path) -> bool:
    """체크포인트 파일 존재 여부."""
```

---

## 3. JSON 포맷 상세

```json
{
  "version": "1",
  "saved_at": "2026-04-08T15:30:00",
  "roots": [
    {
      "id": "4ee0f5905d",
      "concept": "Abstract",
      "source_excerpt": "The dominant sequence...",
      "explanation": "이 논문은...",
      "depth": 0,
      "parent_id": null,
      "is_leaf": false,
      "status": "done",
      "duplicate_of": null,
      "failed_errors": null,
      "verification": {
        "passed": true,
        "confidence": 0.93,
        "errors": [],
        "notes": "",
        "passed_final": true
      },
      "children": [
        {
          "id": "abc1234567",
          "concept": "Softmax 함수",
          "source_excerpt": "...",
          "explanation": "...",
          "depth": 1,
          "parent_id": "4ee0f5905d",
          "is_leaf": true,
          "status": "done",
          "duplicate_of": null,
          "failed_errors": null,
          "verification": {},
          "children": []
        }
      ]
    }
  ]
}
```

- `version`: 포맷 버전. 불일치 시 경고 후 시도.
- `saved_at`: ISO 8601 저장 시각.
- `roots`: ConceptNode 리스트. 각 노드는 children을 재귀 포함.

---

## 4. 직렬화 로직

```python
def _node_to_dict(node: ConceptNode) -> dict:
    return {
        "id": node.id,
        "concept": node.concept,
        "source_excerpt": node.source_excerpt,
        "explanation": node.explanation,
        "depth": node.depth,
        "parent_id": node.parent_id,
        "is_leaf": node.is_leaf,
        "status": node.status,
        "duplicate_of": node.duplicate_of,
        "failed_errors": node.failed_errors,
        "verification": node.verification,
        "children": [_node_to_dict(c) for c in node.children],
    }
```

순환 참조 없음: parent→children만 객체 참조, children→parent는 parent_id 문자열. 재귀가 자연스럽게 종료.

---

## 5. 역직렬화 로직

```python
def _dict_to_node(d: dict) -> ConceptNode:
    # 필수 필드 확인
    for key in ("id", "concept", "source_excerpt"):
        if key not in d:
            raise ValueError(f"필수 필드 누락: {key}")

    node = ConceptNode(
        concept=d["concept"],
        source_excerpt=d["source_excerpt"],
        explanation=d.get("explanation", ""),
        id=d["id"],
        depth=d.get("depth", 0),
        parent_id=d.get("parent_id"),
        is_leaf=d.get("is_leaf", False),
        status=d.get("status", "pending"),
        duplicate_of=d.get("duplicate_of"),
        failed_errors=d.get("failed_errors"),
        verification=d.get("verification", {}),
    )
    node.children = [_dict_to_node(c) for c in d.get("children", [])]
    return node
```

- `id`를 명시적으로 전달하여 uuid4 자동 생성을 우회 — 체크포인트의 id를 그대로 복원.
- 누락 가능한 필드는 `.get(key, default)`로 방어.

---

## 6. 원자적 쓰기

```python
def save(roots, checkpoint_path):
    data = {
        "version": CHECKPOINT_VERSION,
        "saved_at": datetime.now().isoformat(),
        "roots": [_node_to_dict(r) for r in roots],
    }
    tmp_path = checkpoint_path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(checkpoint_path)  # 원자 교체
```

- `.tmp` 파일에 먼저 완전히 쓰고, `Path.replace()`로 원자 교체.
- 쓰기 중 프로세스 종료 시 기존 체크포인트는 손상되지 않음.
- `checkpoint_path.parent.mkdir(parents=True, exist_ok=True)` 추가.

---

## 7. 에러 처리

| 상황 | 처리 |
|------|------|
| 파일 없음 (`load`) | `FileNotFoundError` 발생 |
| JSON 파싱 실패 | `ValueError("체크포인트 JSON 파싱 실패: {path}")` |
| 필수 필드 누락 (id, concept, source_excerpt) | `ValueError("필수 필드 누락: {key}")` |
| version 불일치 | `warnings.warn(...)` 후 계속 시도 |
| `exists` | `checkpoint_path.exists()` 반환 |

---

## 8. 테스트 전략

- **할당량 0** (Claude 호출 없음)
- **save → load 라운드트립**:
  1. 트리 생성 (루트 + 자식 + 손자)
  2. `save(roots, path)`
  3. `loaded = load(path)`
  4. 원본과 비교: id, concept, status, depth, children 수, parent_id
- **손상 파일**: 깨진 JSON 문자열 → `ValueError`
- **누락 필드**: `{"concept": "X"}` (id 없음) → `ValueError`
- **version 불일치**: `{"version": "99", ...}` → 경고 + 정상 로드

---

## 9. 까다로운 부분

### ① ConceptNode 생성자의 id 기본값 우회

ConceptNode의 `id` 필드는 `field(default_factory=lambda: uuid4().hex[:10])`로 자동 생성됨. 역직렬화 시 체크포인트의 id를 복원하려면 생성자에 `id=d["id"]`를 명시적으로 전달해야 함. dataclass의 생성자가 키워드 인자를 받으므로 문제없지만, `id`가 필수 필드가 아닌 기본값 필드라서 위치가 `concept`, `source_excerpt` 뒤에 있음 → 반드시 키워드 인자로 전달.

### ② children 복원 순서

`_dict_to_node`에서 children을 생성자 밖에서 할당 (`node.children = [...]`). 이유: ConceptNode의 children 기본값은 `field(default_factory=list)`이고, 재귀 생성 시점에 자식 노드들이 아직 dict 상태이므로 생성 후 할당이 자연스러움.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
