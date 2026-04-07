# src/assembler.py 설계

## 1. 모듈 책임 (한 줄)

**ConceptNode 트리 리스트를 받아서 최종 Markdown 가이드북 하나를 생성한다.**

---

## 2. 공개 API

```python
from pathlib import Path
from src.tree import ConceptNode

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
```

---

## 3. Markdown 출력 구조 (예시)

```markdown
# Attention Is All You Need 해설

생성 일시: 2026-04-08 15:30

---

## 목차

- [1. Abstract](#1-abstract)
  - [1.1 Softmax 함수](#11-softmax-함수)
- [2. Introduction](#2-introduction)
- [3. Model Architecture](#3-model-architecture)
  - [3.1 Encoder and Decoder Stacks](#31-encoder-and-decoder-stacks)
  - [3.2 Attention](#32-attention)
    - [3.2.1 Scaled Dot-Product Attention](#321-scaled-dot-product-attention)

---

# 1. Abstract

어텐션 메커니즘은 시퀀스 변환 모델에서 인코더와 디코더를 연결하는 ...

## 1.1 Softmax 함수

Softmax 함수는 임의의 실수 여러 개를 입력받아 ...

---

# 2. Introduction

딥러닝(심층 학습, 여러 층의 신경망을 쌓아 학습하는 방법)에서 ...

---

# 3. Model Architecture

> [중복] "Encoder and Decoder Stacks"와 동일 개념입니다. 위쪽 설명을 참조하세요.

## 3.1 Encoder and Decoder Stacks

인코더(입력을 처리하는 부분)와 디코더(출력을 생성하는 부분)는 ...

## 3.2 Attention

> [검증 실패] 다음 항목이 확인되지 않았습니다:
> - [faithfulness] 원문에 없는 scaling 이유를 추가함

어텐션은 ...

### 3.2.1 Scaled Dot-Product Attention

Scaled Dot-Product Attention(스케일링된 내적 어텐션)은 ...

$$\mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V$$
```

---

## 4. 노드 상태별 렌더링 규칙

| status | 렌더링 |
|--------|--------|
| `done` | explanation을 그대로 출력 |
| `duplicate` | `> [중복] "{duplicate_of 또는 원본 concept}"과 동일 개념입니다. 위쪽 설명을 참조하세요.` |
| `verification_failed` | explanation 출력 + `> [검증 실패] 다음 항목이 확인되지 않았습니다:` + errors 리스트 |
| `failed` | `> [생성 실패] {failed_errors[0].description}` |
| `pending` | `> [미완료] 이 섹션은 아직 생성되지 않았습니다.` |

duplicate 노드의 원본 이름 결정:
- `duplicate_of`가 `"ancestor-cycle"`이면 → 조상 순환. concept 이름 사용.
- `duplicate_of`가 node id이면 → id_map으로 원본 concept 검색. 못 찾으면 id 표시.

---

## 5. 번호 체계 알고리즘

DFS 순회 + 카운터 스택:

```python
def _render_body(roots):
    sections = []
    for i, root in enumerate(roots, 1):
        _render_node(root, prefix=f"{i}", header_level=1, sections=sections)
    return "\n\n---\n\n".join(sections)

def _render_node(node, prefix, header_level, sections):
    # 헤더: "# 1. Abstract" 또는 "## 1.1 Softmax"
    hashes = "#" * header_level
    header = f"{hashes} {prefix}. {node.concept}"
    body = _render_status(node)
    sections.append(f"{header}\n\n{body}")

    for j, child in enumerate(node.children, 1):
        child_prefix = f"{prefix}.{j}"
        _render_node(child, child_prefix, header_level + 1, sections)
```

- 루트: `1.`, `2.`, `3.`
- 자식: `1.1`, `1.2`
- 손자: `1.1.1`, `1.1.2`
- `---` 구분선은 루트 간에만 삽입

---

## 6. 앵커 생성 함수

```python
def _make_anchor(numbered_title: str) -> str:
    """Markdown 앵커를 생성한다.

    예: "1.1 Softmax 함수" → "11-softmax-함수"
    """
    anchor = numbered_title.lower()
    anchor = re.sub(r"[^\w\s가-힣-]", "", anchor)  # 영숫자, 한글, 공백, 하이픈만
    anchor = re.sub(r"\s+", "-", anchor.strip())    # 공백 → 하이픈
    anchor = re.sub(r"\.+", "", anchor)              # 점 제거
    return anchor
```

GitHub Flavored Markdown 규칙 기반. 한국어 문자 보존.

---

## 7. 목차 생성 로직

```python
def _build_toc(roots):
    lines = ["## 목차", ""]
    for i, root in enumerate(roots, 1):
        _toc_node(root, prefix=f"{i}", depth=0, lines=lines)
    return "\n".join(lines)

def _toc_node(node, prefix, depth, lines):
    indent = "  " * depth
    title = f"{prefix}. {node.concept}"
    anchor = _make_anchor(title)
    lines.append(f"{indent}- [{title}](#{anchor})")
    for j, child in enumerate(node.children, 1):
        _toc_node(child, f"{prefix}.{j}", depth + 1, lines)
```

---

## 8. 본문 생성 로직

각 노드를 Markdown 섹션으로 변환:

```python
def _render_status(node):
    if node.status == "done":
        return node.explanation
    elif node.status == "duplicate":
        orig = node.duplicate_of or "알 수 없는 원본"
        return f'> [중복] "{orig}"과 동일 개념입니다. 위쪽 설명을 참조하세요.'
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

---

## 9. 수식/특수문자 처리

- explanation에 LaTeX 수식(`$...$`, `$$...$$`, `\begin{equation}...`)이 포함되어 있으면 **그대로 출력**
- assembler는 수식 렌더링 책임 없음 — Markdown 뷰어(GitHub, VSCode 등)가 처리
- 수식 변환, 이스케이프, 래핑 금지
- 한국어 문자도 그대로 출력 (`ensure_ascii=False` 불필요 — 문자열 직접 쓰기)

---

## 10. 외부 의존성

### 사용

| 모듈 | 용도 |
|------|------|
| `pathlib.Path` | 출력 파일 경로 |
| `datetime` | 생성 일시 |
| `re` | 앵커 생성 |
| `src.tree.ConceptNode` | 노드 타입 |
| `src.tree.iter_dfs` | DFS 순회 (id_map 구축용, duplicate_of 원본 이름 조회) |
| `src.tree.build_id_map` | duplicate 원본 조회 |

### 절대 금지

pandoc, weasyprint, reportlab, markdown, jinja2, pdfkit — Markdown 이외 형식 변환 금지.

---

## 11. 테스트 전략

- **할당량 0** (Claude 호출 없음)
- **다양한 status 조합**: done, duplicate, verification_failed, failed, pending 노드가 섞인 트리
- **깊이 4 트리**: 번호 체계 1.1.1.1까지 정상 출력
- **한국어 + 수식**: explanation에 한국어 텍스트와 `$\mathrm{Attention}(Q,K,V)$` 수식이 섞인 노드
- **목차 앵커 검증**: 목차의 링크가 본문 헤더와 일치하는지
- **빈 트리**: `roots=[]` → 제목과 빈 목차만 출력
- **실제 expander 결과**: `/tmp/test_expander_real`의 캐시를 재활용할 수 있다면 사용

---

## 12. 까다로운 부분

### ① duplicate 노드의 원본 이름 조회

`duplicate_of`가 node id인데, 그 id의 concept 이름을 표시하려면 전체 트리에서 해당 id를 찾아야 함. `build_id_map`으로 전체 트리의 id→node 맵을 미리 구축한 뒤, `id_map.get(node.duplicate_of)`로 원본 노드의 concept을 조회.

`duplicate_of == "ancestor-cycle"`인 경우는 id가 아닌 문자열이므로 별도 처리.

### ② 헤더 레벨과 번호 체계의 일관성

루트는 `#` (레벨 1)이고 번호는 `1.`. 자식은 `##` (레벨 2)이고 번호는 `1.1`. 만약 트리가 깊어서 depth=4이면 `#####`(레벨 5)까지 가는데, Markdown에서 `######`(레벨 6)까지만 지원. max_depth=4이면 루트(0)+자식(1)+손자(2)+증손자(3)+leaf(4) = 최대 `#####`(레벨 5)로 충분.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
