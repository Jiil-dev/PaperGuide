# checkpoint.py 구현 결과

## 1. 작성된 코드 (src/checkpoint.py 전체)

```python
# 단일 책임: ConceptNode 트리 전체를 JSON 파일로 직렬화/역직렬화한다. 세션 중단 시 복구 지점으로 사용.
from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

from src.tree import ConceptNode

CHECKPOINT_VERSION = "1"
# 체크포인트 포맷 변경 시 +1. 로드 시 불일치하면 경고.


def save(roots: list[ConceptNode], checkpoint_path: Path) -> None:
    """루트 리스트 전체를 JSON 파일로 저장한다.

    원자적 쓰기: .tmp에 먼저 쓰고, 성공하면 rename으로 교체.
    """
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

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
    tmp_path.replace(checkpoint_path)


def load(checkpoint_path: Path) -> list[ConceptNode]:
    """JSON 파일에서 루트 리스트를 복원한다.

    Raises:
        FileNotFoundError: 파일 없음.
        ValueError: JSON 형식 오류 또는 필수 필드 누락.
    """
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"체크포인트 파일을 찾을 수 없습니다: {checkpoint_path}")

    text = checkpoint_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"체크포인트 JSON 파싱 실패: {checkpoint_path}") from e

    # 버전 확인
    file_version = data.get("version", "unknown")
    if file_version != CHECKPOINT_VERSION:
        warnings.warn(
            f"체크포인트 버전 불일치: 파일={file_version}, 현재={CHECKPOINT_VERSION}"
        )

    return [_dict_to_node(d) for d in data.get("roots", [])]


def exists(checkpoint_path: Path) -> bool:
    """체크포인트 파일 존재 여부."""
    return checkpoint_path.exists()


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _node_to_dict(node: ConceptNode) -> dict:
    """ConceptNode를 dict로 변환한다. children은 재귀."""
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


def _dict_to_node(d: dict) -> ConceptNode:
    """dict를 ConceptNode로 변환한다. children은 재귀."""
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

## 2. import 테스트

```
$ .venv/bin/python -c "from src.checkpoint import save, load, exists, CHECKPOINT_VERSION; print('import OK, version=', CHECKPOINT_VERSION)"
import OK, version= 1
```

## 3. 라운드트립 테스트

```
exists before save: False
exists after save: True
파일 크기: 2310 bytes

로드 결과: 2개 루트
총 노드 수: 5

라운드트립 OK
```

| 검증 항목 | 결과 | 판정 |
|----------|------|------|
| 루트 수 | 2 | OK |
| root1.id 복원 | 일치 | OK |
| root1.concept | "Attention" | OK |
| root1.explanation | "어텐션은 ..." (한국어) | OK |
| root1.verification.confidence | 0.93 | OK |
| root1.children 수 | 2 | OK |
| child1.parent_id | root1.id | OK |
| child1.is_leaf | True | OK |
| grand.depth | 2 | OK |
| child2.status | "verification_failed" | OK |
| child2.failed_errors | [{"category": "faithfulness", ...}] | OK |
| root2.status | "duplicate" | OK |
| root2.duplicate_of | root1.id | OK |
| 총 노드 수 | 5 | OK |

## 4. 에러 케이스 테스트

```
FileNotFoundError OK: 체크포인트 파일을 찾을 수 없습니다: /tmp/nonexistent_checkpoint.json
손상 JSON ValueError OK: 체크포인트 JSON 파싱 실패: /tmp/bad.json
필드 누락 ValueError OK: 필수 필드 누락: id
버전 경고 OK: 체크포인트 버전 불일치: 파일=99, 현재=1
버전 불일치에도 로드 성공: Y

에러 케이스 전부 OK
```

## 5. 원자적 쓰기 확인

```
$ ls -la /tmp/test_checkpoint/
total 36
-rw-rw-r-- 1 engineer engineer 2310 checkpoint.json
```

.tmp 파일 없음 — rename 성공 후 자동 제거됨.

## 6. 구현 중 주의했던 점

1. **원자적 쓰기**: `.tmp` → `Path.replace()` 패턴. 쓰기 중 프로세스 종료 시 기존 체크포인트 손상 방지.

2. **id 복원**: `ConceptNode(id=d["id"], ...)`로 키워드 인자 전달. uuid4 자동 생성을 우회하여 체크포인트의 원래 id를 그대로 복원.

3. **children 생성자 밖 할당**: `node.children = [_dict_to_node(c) for ...]`로 생성 후 할당. 재귀 생성이 자연스러움.

4. **version 불일치 처리**: `warnings.warn()` 후 계속 시도. 하위 호환을 유지하되 사용자에게 경고.

5. **ensure_ascii=False**: 한국어 explanation이 이스케이프 없이 저장됨. 가독성 확보.
