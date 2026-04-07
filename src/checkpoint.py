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
