# 단일 책임: Part 2 트리의 [[REF:topic_id]] 플레이스홀더를 Part 3 앵커 링크로 치환
from __future__ import annotations

import re

from src.data_types import PrerequisiteEntry
from src.tree import ConceptNode, iter_dfs


_REF_PATTERN = re.compile(r"\[\[REF:([a-z_][a-z0-9_]*)\]\]")


def _make_anchor(numbered_title: str) -> str:
    """Markdown 앵커 생성. assembler.py 의 _make_anchor 와 동일 로직."""
    anchor = numbered_title.lower()
    anchor = re.sub(r"[^\w\s가-힣-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor.strip())
    anchor = re.sub(r"\.+", "", anchor)
    return anchor


def resolve_refs(
    part2_nodes: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> list[ConceptNode]:
    """플레이스홀더를 앵커 링크로 치환한다. in-place 수정 + 반환.

    Args:
        part2_nodes: Part 2 트리 루트 노드 리스트.
        part3_entries: Part 3 항목 리스트.

    Returns:
        치환 완료된 part2_nodes.
    """
    # topic_id → (section_number, title) 맵
    ref_map: dict[str, tuple[str, str]] = {}
    for entry in part3_entries:
        ref_map[entry.topic.topic_id] = (entry.section_number, entry.topic.title)

    def _replace(match: re.Match) -> str:
        topic_id = match.group(1)
        if topic_id not in ref_map:
            return f"[[UNRESOLVED:{topic_id}]]"
        section_num, title = ref_map[topic_id]
        numbered = f"{section_num}. {title}"
        anchor = _make_anchor(numbered)
        return f"**[Part {section_num} {title}](#{anchor})**"

    # 모든 노드 DFS 순회
    for root in part2_nodes:
        for node in iter_dfs(root):
            if node.explanation:
                node.explanation = _REF_PATTERN.sub(_replace, node.explanation)

    return part2_nodes
