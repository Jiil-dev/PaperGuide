# assembler.py 구현 결과

## 1. 작성된 코드 (src/assembler.py 전체)

```python
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
        _render_node(root, prefix=f"{i}", header_level=2, sections=parts, id_map=id_map)
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
) -> None:
    """노드를 Markdown 섹션으로 렌더링하고 sections에 추가한다."""
    hashes = "#" * header_level
    header = f"{hashes} {prefix}. {node.concept}"
    body = _render_status(node, id_map)
    sections.append(f"\n{header}\n\n{body}")

    for j, child in enumerate(node.children, 1):
        child_prefix = f"{prefix}.{j}"
        _render_node(child, child_prefix, header_level + 1, sections, id_map)


def _render_status(node: ConceptNode, id_map: dict[str, ConceptNode]) -> str:
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
            orig = id_map.get(node.duplicate_of or "")
            if orig:
                return (
                    f'> [중복] "{orig.concept}"과 동일 개념입니다. '
                    f"위쪽 설명을 참조하세요."
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
```

## 2. import 테스트

```
$ .venv/bin/python -c "from src.assembler import assemble; print('import OK')"
import OK
```

## 3. 종합 테스트

### 출력 전문

```markdown
# 테스트 가이드북

생성 일시: 2026-04-08 06:52

---

## 목차

- [1. Abstract](#1-abstract)
  - [1.1. Softmax 함수](#11-softmax-함수)
- [2. Introduction](#2-introduction)
- [3. Model Architecture](#3-model-architecture)
  - [3.1. Duplicate concept](#31-duplicate-concept)
  - [3.2. Ancestor Cycle Example](#32-ancestor-cycle-example)
  - [3.3. Failed Concept](#33-failed-concept)
- [4. Deep Root](#4-deep-root)
  - [4.1. Level 1](#41-level-1)
    - [4.1.1. Level 2](#411-level-2)
      - [4.1.1.1. Level 3](#4111-level-3)
        - [4.1.1.1.1. Level 4](#41111-level-4)

---

## 1. Abstract

어텐션 메커니즘은 ... $\mathrm{Attention}(Q,K,V) = ...$

### 1.1. Softmax 함수

소프트맥스는 각 값을 0~1 사이 확률로 변환합니다.

---

## 2. Introduction

딥러닝(심층 학습)에서 시퀀스 처리는...

---

## 3. Model Architecture

> [검증 실패] 다음 항목이 확인되지 않았습니다:
> - [faithfulness] 원문과 일치하지 않음

### 3.1. Duplicate concept

> [중복] "Abstract"과 동일 개념입니다. 위쪽 설명을 참조하세요.

### 3.2. Ancestor Cycle Example

> [중복] "Ancestor Cycle Example"이 조상 경로에 이미 있어 순환이 감지되었습니다.

### 3.3. Failed Concept

> [생성 실패] Claude CLI timeout

---

## 4. Deep Root

루트

### 4.1. Level 1

레벨1

#### 4.1.1. Level 2

레벨2

##### 4.1.1.1. Level 3

레벨3

###### 4.1.1.1.1. Level 4

레벨4
```

### 검증 항목

| 항목 | 결과 | 판정 |
|------|------|------|
| 책 제목 `# 테스트 가이드북` | 레벨 1 | OK |
| 루트 `## 1. Abstract` | 레벨 2 (보정 A) | OK |
| 자식 `### 1.1. Softmax 함수` | 레벨 3 | OK |
| 깊이 4 `###### 4.1.1.1.1. Level 4` | 레벨 6 (Markdown 한계) | OK |
| 목차 앵커 | `(#1-abstract)` 등 | OK |
| duplicate 원본 조회 | "Abstract"과 동일 (보정 B) | OK |
| ancestor-cycle 처리 | "조상 경로에 이미 있어" | OK |
| verification_failed | 경고 블록 + errors | OK |
| failed | "[생성 실패] Claude CLI timeout" | OK |
| 수식 보존 | `\mathrm{Attention}` 그대로 | OK |
| 루트 간 `---` 구분선 | 있음 | OK |
| 빈 트리 | 제목 + 빈 목차만 | OK |

## 4. 구현 중 주의했던 점

1. **보정 A — 루트 레벨 2**: `_render_node` 첫 호출에 `header_level=2` 전달. 책 제목 `#`(레벨 1) 아래에 루트가 위치.

2. **보정 B — 전역 id_map**: `_build_global_id_map`이 모든 루트의 `build_id_map`을 합침. `_render_status`가 `id_map`을 받아 duplicate 원본 조회.

3. **번호 체계**: `prefix` 문자열을 재귀적으로 구축 (`"1"` → `"1.1"` → `"1.1.1"`). 헤더 형식: `{hashes} {prefix}. {concept}`.

4. **수식 무간섭**: explanation의 LaTeX를 그대로 출력. 이스케이프, 래핑, 변환 없음.

5. **금지 모듈**: pandoc, weasyprint, reportlab, jinja2 등 import 없음. 순수 문자열 조합.
