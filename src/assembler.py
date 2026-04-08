# 단일 책임: ConceptNode 트리 리스트를 받아서 최종 Markdown 가이드북 하나를 생성한다.
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from src.data_types import PaperAnalysis, PrerequisiteEntry
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


# ---------------------------------------------------------------------------
# Phase 3: 3-Part 가이드북 조립
# ---------------------------------------------------------------------------


def assemble_3part_guidebook(
    analysis: PaperAnalysis,
    part2_trees: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> str:
    """3-Part 가이드북 Markdown 생성.

    Args:
        analysis: paper_analyzer 출력.
        part2_trees: expander 출력 (각 섹션의 루트 노드 리스트).
        part3_entries: part3_writer 출력 리스트.

    Returns:
        완성된 가이드북 Markdown 문자열.
    """
    from src.ref_resolver import resolve_refs

    # Step 1: Part 2 의 [[REF:...]] 를 Part 3 링크로 치환
    resolve_refs(part2_trees, part3_entries)

    lines: list[str] = []

    # 제목
    lines.append(f"# {analysis.title} — 완전판 가이드북\n")

    # Part 1
    lines.append("## Part 1. 논문이 무엇을 주장하는가 — 큰 그림\n")

    lines.append("### 1.1 핵심 주장\n")
    lines.append(analysis.core_thesis + "\n")

    lines.append("### 1.2 해결하려는 문제\n")
    lines.append(analysis.problem_statement + "\n")

    lines.append("### 1.3 핵심 기여\n")
    for c in analysis.key_contributions:
        lines.append(f"- {c}")
    lines.append("")

    lines.append("### 1.4 주요 결과\n")
    for r in analysis.main_results:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("### 1.5 이 논문의 의의\n")
    lines.append(analysis.significance + "\n")

    lines.append("### 1.6 이 가이드북 읽는 법\n")
    lines.append(analysis.reading_guide + "\n")

    # Part 2
    lines.append("## Part 2. 논문 따라 읽기 — 완전 해설\n")

    for idx, root in enumerate(part2_trees, start=1):
        section_num = f"2.{idx}"
        _render_part2_node(lines, root, section_num, depth=0)

    # Part 3
    if part3_entries:
        lines.append("## Part 3. 기초 지식 탄탄히\n")
        for entry in part3_entries:
            _render_part3_entry(lines, entry)

    return "\n".join(lines)


def _render_part2_node(lines: list[str], node: ConceptNode, section_num: str, depth: int) -> None:
    """Part 2 노드를 재귀적으로 Markdown 으로 렌더링."""
    heading_level = "#" * (3 + depth)  # ### for depth=0, #### for depth=1, ...
    lines.append(f"{heading_level} {section_num} {node.concept}\n")

    if node.explanation:
        lines.append(node.explanation + "\n")

    for child_idx, child in enumerate(node.children, start=1):
        child_section = f"{section_num}.{child_idx}"
        _render_part2_node(lines, child, child_section, depth + 1)


def _render_part3_entry(lines: list[str], entry: PrerequisiteEntry) -> None:
    """Part 3 항목 렌더링."""
    lines.append(f"### {entry.section_number} {entry.topic.title}\n")

    for idx, sub in enumerate(entry.subsections, start=1):
        sub_num = f"{entry.section_number}.{idx}"
        lines.append(f"#### {sub_num} {sub.concept}\n")
        lines.append(sub.explanation + "\n")
