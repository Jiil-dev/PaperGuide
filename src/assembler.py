# 단일 책임: ConceptNode 트리 리스트를 받아서 최종 Markdown 가이드북 하나를 생성한다.
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from src.tree import ConceptNode, build_id_map


def assemble(
    roots: list[ConceptNode],
    title: str,
    output_path: Path,
) -> None:
    """트리를 Markdown 가이드북으로 렌더링하여 파일에 쓴다.

    Args:
        roots: 확장 완료된 ConceptNode 루트 리스트.
        title: 책 제목 (예: "Attention Is All You Need 해설").
        output_path: 출력 .md 파일 경로.
    """
    id_map = _build_global_id_map(roots)
    prefix_map = _build_prefix_map(roots)

    parts = []

    # 책 제목
    parts.append(f"# {title}")
    parts.append(f"\n생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    parts.append("\n---\n")

    # 목차
    parts.append(_build_toc(roots))
    parts.append("\n---\n")

    # 본문
    for i, root in enumerate(roots, 1):
        _render_node(root, prefix=f"{i}", header_level=2, sections=parts, id_map=id_map, prefix_map=prefix_map)
        # 루트 간 구분선 (마지막 루트 뒤에는 넣지 않음)
        if i < len(roots):
            parts.append("\n---\n")

    content = "\n".join(parts) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _build_global_id_map(roots: list[ConceptNode]) -> dict[str, ConceptNode]:
    """모든 루트의 id_map을 합쳐서 전역 id_map을 생성한다."""
    global_map: dict[str, ConceptNode] = {}
    for root in roots:
        global_map.update(build_id_map(root))
    return global_map


def _build_prefix_map(roots: list[ConceptNode]) -> dict[str, tuple[str, str]]:
    """각 노드 id에 번호 prefix와 concept을 매핑한다.

    예: {"abc123": ("1.2.1", "Softmax 함수")}

    duplicate 노드가 원본의 번호를 찾을 때 사용.
    """
    prefix_map: dict[str, tuple[str, str]] = {}

    def _walk(node: ConceptNode, prefix: str) -> None:
        prefix_map[node.id] = (prefix, node.concept)
        for j, child in enumerate(node.children, 1):
            _walk(child, f"{prefix}.{j}")

    for i, root in enumerate(roots, 1):
        _walk(root, f"{i}")

    return prefix_map


def _make_anchor(numbered_title: str) -> str:
    """Markdown 앵커를 생성한다.

    예: "1.1 Softmax 함수" → "11-softmax-함수"
    """
    anchor = numbered_title.lower()
    anchor = re.sub(r"[^\w\s가-힣-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor.strip())
    anchor = re.sub(r"\.+", "", anchor)
    return anchor


def _build_toc(roots: list[ConceptNode]) -> str:
    """목차를 생성한다."""
    lines = ["## 목차", ""]
    for i, root in enumerate(roots, 1):
        _toc_node(root, prefix=f"{i}", depth=0, lines=lines)
    return "\n".join(lines)


def _toc_node(
    node: ConceptNode, prefix: str, depth: int, lines: list[str]
) -> None:
    """목차 항목을 재귀적으로 추가한다."""
    indent = "  " * depth
    title = f"{prefix}. {node.concept}"
    anchor = _make_anchor(title)
    lines.append(f"{indent}- [{title}](#{anchor})")
    for j, child in enumerate(node.children, 1):
        _toc_node(child, f"{prefix}.{j}", depth + 1, lines)


def _render_node(
    node: ConceptNode,
    prefix: str,
    header_level: int,
    sections: list[str],
    id_map: dict[str, ConceptNode],
    prefix_map: dict[str, tuple[str, str]],
) -> None:
    """노드를 Markdown 섹션으로 렌더링하고 sections에 추가한다."""
    hashes = "#" * header_level
    header = f"{hashes} {prefix}. {node.concept}"
    body = _render_status(node, id_map, prefix_map)
    sections.append(f"\n{header}\n\n{body}")

    for j, child in enumerate(node.children, 1):
        child_prefix = f"{prefix}.{j}"
        _render_node(child, child_prefix, header_level + 1, sections, id_map, prefix_map)


def _render_status(
    node: ConceptNode,
    id_map: dict[str, ConceptNode],
    prefix_map: dict[str, tuple[str, str]],
) -> str:
    """노드 상태에 따라 본문을 렌더링한다."""
    if node.status == "done":
        return node.explanation

    elif node.status == "duplicate":
        if node.duplicate_of == "ancestor-cycle":
            return (
                f'> [중복] "{node.concept}"이 조상 경로에 이미 있어 '
                f"순환이 감지되었습니다."
            )
        else:
            orig_entry = prefix_map.get(node.duplicate_of or "")
            if orig_entry:
                orig_prefix, orig_concept = orig_entry
                orig_numbered = f"{orig_prefix}. {orig_concept}"
                anchor = _make_anchor(orig_numbered)
                return (
                    f"> [중복] 이 개념은 "
                    f"[§{orig_prefix} {orig_concept}](#{anchor})와 "
                    f"동일합니다. 위 섹션을 참조하세요."
                )
            else:
                return (
                    f"> [중복] id={node.duplicate_of} 원본을 찾을 수 없습니다."
                )

    elif node.status == "verification_failed":
        warning = "> [검증 실패] 다음 항목이 확인되지 않았습니다:\n"
        if node.failed_errors:
            for err in node.failed_errors:
                cat = err.get("category", "unknown")
                desc = err.get("description", "")
                warning += f"> - [{cat}] {desc}\n"
        return warning + "\n" + node.explanation

    elif node.status == "failed":
        desc = ""
        if node.failed_errors:
            desc = node.failed_errors[0].get("description", "알 수 없는 에러")
        return f"> [생성 실패] {desc}"

    else:  # pending
        return "> [미완료] 이 섹션은 아직 생성되지 않았습니다."
