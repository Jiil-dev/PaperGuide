# 단일 책임: Markdown 문자열을 헤더 기준으로 섹션 분할하여 list[ConceptNode] 루트 노드 리스트를 반환한다.
from __future__ import annotations

import re

from src.tree import ConceptNode

# ## Abstract 등 하위 레벨이지만 루트로 승격할 섹션 이름 (소문자)
_PROMOTE_TO_ROOT = {"abstract"}

# 결과에서 제외할 섹션 이름 (소문자)
_EXCLUDED_SECTIONS = {
    "references",
    "bibliography",
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
}

# 헤더 패턴: #, ##, ### 레벨
_HEADER_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _clean_header(text: str) -> str:
    """헤더 텍스트에서 볼드 마크와 섹션 번호를 제거한다.

    예: '**2.1 Matching logits...**' → 'Matching logits...'
    """
    text = text.strip()
    text = text.replace("**", "")
    text = re.sub(r"^\d+(\.\d+)*\s+", "", text)
    return text.strip()


def split_into_sections(markdown: str) -> list[ConceptNode]:
    """Markdown 문자열을 헤더 기준으로 분할하여 ConceptNode 리스트로 반환한다.

    # 헤더를 루트 노드, ## 헤더를 자식, ### 헤더를 손자로 구성.
    Abstract는 ## 레벨이지만 루트 노드로 승격.
    pymupdf4llm 출력(모두 ##)에서는 각 ##가 depth=0 루트가 된다.

    Args:
        markdown: #, ##, ### 헤더가 포함된 Markdown 문자열.

    Returns:
        list[ConceptNode]: 루트 노드 리스트.
            각 루트의 children에 하위 섹션이 ConceptNode 객체로 포함됨.
            References, Acknowledgments 등은 필터링되어 제외.
    """
    if not markdown or not markdown.strip():
        return [ConceptNode(concept="Document", source_excerpt="")]

    # 모든 헤더 수집
    matches = list(_HEADER_PATTERN.finditer(markdown))

    if not matches:
        return [ConceptNode(concept="Document", source_excerpt=markdown.strip())]

    # 각 헤더의 (level, cleaned_concept, body) 추출
    sections: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))  # # → 1, ## → 2, ### → 3
        concept = _clean_header(m.group(2))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[body_start:body_end].strip()
        sections.append((level, concept, body))

    # 스택 기반 계층 트리 구축
    roots: list[ConceptNode] = []
    stack: list[tuple[int, ConceptNode]] = []  # (depth, node)

    for level, concept, body in sections:
        # depth 결정: 기본값은 level - 1 (# → 0, ## → 1, ### → 2)
        depth = level - 1

        # 승격 판정: 전처리된 concept이 _PROMOTE_TO_ROOT에 있으면 depth=0
        if concept.lower() in _PROMOTE_TO_ROOT:
            depth = 0

        node = ConceptNode(concept=concept, source_excerpt=body, depth=depth)

        # 스택에서 depth 이상인 것 pop
        while stack and stack[-1][0] >= depth:
            stack.pop()

        if not stack:
            # 최상위 → roots에 추가
            node.depth = 0
            node.parent_id = None
            roots.append(node)
        else:
            parent_depth, parent_node = stack[-1]
            node.depth = parent_depth + 1
            node.parent_id = parent_node.id
            parent_node.children.append(node)

        stack.append((node.depth, node))

    # 필터링: 루트 중 제외 대상 제거
    roots = [r for r in roots if r.concept.lower() not in _EXCLUDED_SECTIONS]

    return roots
