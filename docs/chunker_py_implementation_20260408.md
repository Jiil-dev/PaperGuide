# chunker.py 구현 결과

## 1. 작성된 코드 (src/chunker.py 전체)

```python
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
```

## 2. 검증 결과

### 2-1. import 테스트

```
$ .venv/bin/python -c "from src.chunker import split_into_sections; print('import OK')"
import OK
```

### 2-2. 실제 Attention 논문 분할 (루트·자식·손자 트리 출력)

```
루트 노드 개수: 9

# [4ee0f5905d] Abstract (depth=0, excerpt=1142자)
# [dd0dd7dcb7] Introduction (depth=0, excerpt=2127자)
# [2247b8e331] Background (depth=0, excerpt=1995자)
# [89d34c1bed] Model Architecture (depth=0, excerpt=811자)
  ## [9698225cb4] Encoder and Decoder Stacks (depth=1, excerpt=1388자)
  ## [b17b90deb1] Attention (depth=1, excerpt=337자)
    ### [c63b2a6785] Scaled Dot-Product Attention (depth=2, excerpt=1956자)
    ### [6d66e59c3b] Multi-Head Attention (depth=2, excerpt=1457자)
    ### [3433445b24] Applications of Attention in our Model (depth=2, excerpt=1259자)
  ## [becbdd0bf4] Position-wise Feed-Forward Networks (depth=1, excerpt=667자)
  ## [c75b9d90ed] Embeddings and Softmax (depth=1, excerpt=524자)
  ## [7ca422024b] Positional Encoding (depth=1, excerpt=1535자)
# [bdc4ec22c1] Why Self-Attention (depth=0, excerpt=4068자)
# [ea988d1042] Training (depth=0, excerpt=58자)
  ## [a8ba1e5955] Training Data and Batching (depth=1, excerpt=631자)
  ## [23da044fde] Hardware and Schedule (depth=1, excerpt=421자)
  ## [f3bfe0e241] Optimizer (depth=1, excerpt=548자)
  ## [bb39a24715] Regularization (depth=1, excerpt=630자)
# [e9f57b0afa] Results (depth=0, excerpt=0자)
  ## [16203c4f83] Machine Translation (depth=1, excerpt=3104자)
  ## [7cf0fd8758] Model Variations (depth=1, excerpt=3060자)
  ## [12c07a0ee8] English Constituency Parsing (depth=1, excerpt=2899자)
# [0fd41e159c] Conclusion (depth=0, excerpt=9970자)
# [437840cbfc] Attention Visualizations (depth=0, excerpt=25자)
```

- 루트 9개 (Abstract + 7개 \section + Attention Visualizations)
- References 루트 없음 (필터링됨)
- Model Architecture 자식 6개: Encoder and Decoder Stacks, Attention, Position-wise Feed-Forward Networks, Embeddings and Softmax, Positional Encoding
- Attention 손자 3개: Scaled Dot-Product Attention, Multi-Head Attention, Applications of Attention in our Model
- Results의 excerpt=0자 (빈 섹션 정상 처리)
- Abstract가 ## → # 승격되어 루트로 정상 배치

### 2-3. parent-child 일관성 검증

```
총 노드 개수: 24
parent-child 일관성: OK
```

- 모든 비루트 노드의 parent_id가 id_map에 존재
- 모든 루트 노드의 parent_id가 None

### 2-4. concept 전처리 검증

```
OK: 모든 concept이 깔끔하게 정리됨
```

- 볼드 마크(**) 없음
- 섹션 번호 없음
- 모든 concept이 깔끔한 텍스트

### 2-5. 엣지 케이스 (빈 입력, 헤더 없음)

```
빈 입력 결과: 1개 루트, concept="Document"
헤더 없는 입력 결과: 1개 루트, concept="Document", excerpt=39자
```

- 빈 입력: Document 노드 1개 (source_excerpt 빈 문자열)
- 헤더 없는 텍스트: Document 노드 1개 (전체 텍스트가 source_excerpt)

## 3. 구현 중 주의했던 점

1. **스택 기반 계층 구축**: `(depth, node)` 튜플 스택으로 현재 경로의 조상을 추적. 새 노드의 depth 이상인 스택 항목을 pop하여 올바른 부모를 찾음. `#` 없이 `##`만 있는 pymupdf4llm 출력에서는 스택이 항상 비어있어 모든 `##`가 자연스럽게 depth=0 루트가 됨.

2. **Abstract 승격 순서**: `_clean_header`로 먼저 "Abstract" 텍스트를 추출한 뒤, `.lower()`로 `_PROMOTE_TO_ROOT`에 포함되는지 확인. 이 순서가 바뀌면 `## **Abstract**`에서 볼드가 남아 매칭 실패.

3. **depth 재계산**: 스택에 부모가 있으면 `parent_depth + 1`로 depth를 재계산. 이로써 `#` 없이 `##`가 루트가 되면 depth=0, 그 아래 `###`이 depth=1이 됨. 원래 헤더 레벨과 무관하게 트리 내 상대적 깊이가 유지됨.

4. **필터링 시점**: 트리 구축 완료 후 루트에서만 필터링. 자식 노드는 필터링하지 않음. References가 자식으로 나타나는 경우는 현실적으로 없음.

5. **source_excerpt 범위**: 각 섹션의 본문은 현재 헤더 줄 끝 ~ 다음 헤더(어떤 레벨이든) 시작 직전. 하위 헤더의 내용은 하위 노드의 source_excerpt에 별도 저장되므로 부모 노드에 중복 포함되지 않음.
