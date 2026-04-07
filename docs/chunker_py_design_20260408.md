# src/chunker.py 설계

## 1. 모듈 책임 (한 줄)

**Markdown 문자열을 헤더 기준으로 섹션 분할하여 `list[ConceptNode]` 루트 노드 리스트를 반환한다.**

---

## 2. 공개 인터페이스

### 입력 타입 판단

**str (markdown 문자열)만 받는다.** ParseResult 전체를 받지 않는다.

| 대안 | 장점 | 단점 | 선택 |
|------|------|------|------|
| `ParseResult` 전체 | 메타데이터 접근 가능 | pdf_parser import 필요, chunker의 의존성 증가 | 탈락 |
| `str` (markdown만) | 독립적, 테스트 용이 | 메타데이터 접근 불가 | **선택** |

근거: chunker는 Markdown 텍스트만 분석하면 된다. title, page_count 같은 메타데이터는 chunker의 관심사가 아님. 호출자(main.py)가 `result.markdown`을 넘기면 됨.

### 함수 시그니처

```python
from src.tree import ConceptNode

def split_into_sections(markdown: str) -> list[ConceptNode]:
    """Markdown 문자열을 헤더 기준으로 분할하여 ConceptNode 리스트로 반환한다.

    # 헤더를 루트 노드, ## 헤더를 자식, ### 헤더를 손자로 구성.
    Abstract는 ## 레벨이지만 별도 루트 노드로 승격.

    Args:
        markdown: #, ##, ### 헤더가 포함된 Markdown 문자열.

    Returns:
        list[ConceptNode]: 루트 노드 리스트.
            각 루트의 children에 하위 섹션이 ConceptNode 객체로 포함됨.
    """
```

### 예상 사용 예시 (main.py)

```python
from pathlib import Path
from src.pdf_parser import parse_pdf
from src.arxiv_parser import parse_arxiv
from src.chunker import split_into_sections

# 파서에서 Markdown 획득
result = parse_arxiv(Path("data/papers/attention"))

# chunker에 Markdown만 전달
roots = split_into_sections(result.markdown)

print(f"루트 노드 {len(roots)}개")
for root in roots:
    print(f"  # {root.concept} (depth={root.depth}, children={len(root.children)})")
    for child in root.children:
        print(f"    ## {child.concept} (depth={child.depth})")
```

---

## 3. 헤더 레벨 처리 전략

### 3가지 선택지 분석

#### (a) 평면 리스트 — 모든 헤더를 독립 루트(depth=0)

**장점:**
- 구현 단순
- pymupdf4llm 출력과 호환 (모두 `##`로 나옴)

**단점:**
- 계층 구조 정보 손실: "Scaled Dot-Product Attention"이 "Attention" 섹션의 하위 개념이라는 정보 소멸
- expander가 이미 존재하는 하위 구조를 모르고 중복 확장할 위험
- Attention 논문 기준 24개 루트 → 너무 많음

#### (b) 계층 트리 — #를 루트, ##를 자식, ###를 손자

**장점:**
- 원본 논문의 논리 구조를 반영
- expander가 "이 개념 아래 이미 하위 섹션이 있다"는 것을 알 수 있음
- Attention 논문 기준 7개 루트 → 적절한 수

**단점:**
- pymupdf4llm 출력은 계층 없음 (모두 `##`) → 특별 처리 필요
- 구현 약간 복잡

#### (c) # 레벨만 루트 — ## 이하는 source_excerpt에 포함

**장점:**
- 루트 개수 최소화

**단점:**
- source_excerpt가 매우 길어짐 (수천 자)
- 하위 구조 정보가 비구조화된 텍스트로 묻힘
- expander가 이미 구조화된 섹션을 다시 분석해야 함 → 비효율

### 결정: **(b) 계층 트리**

근거:
1. **expander의 효율성**: expander가 각 노드를 DFS로 확장할 때, 이미 존재하는 자식 노드를 인식할 수 있음. "Model Architecture" 아래에 "Attention", "Feed-Forward Networks" 등이 이미 자식으로 있으면, expander는 이를 확장 출발점으로 활용 가능.
2. **루트 수 적절**: Attention 논문 기준 `#` 레벨 7개(Introduction, Background, Model Architecture, Why Self-Attention, Training, Results, Conclusion) + Abstract 1개 = 8개 루트. 적절.
3. **pymupdf4llm 호환**: pymupdf4llm 출력은 모든 헤더가 `##`로 나오므로, 이 경우 모든 섹션이 depth=0 루트가 됨. 사실상 (a)와 동일하게 동작. 계층 정보가 없으면 평면으로 자연스럽게 폴백.

### Abstract 특별 처리

arxiv_parser의 출력에서 Abstract는 `## Abstract`로 나옴 (##는 subsection 레벨). 하지만 Abstract는 논문의 최상위 섹션으로 취급해야 함. 따라서 `## Abstract`는 `#` 레벨로 승격하여 루트 노드로 만든다.

### pymupdf4llm 출력의 처리

pymupdf4llm은 모든 헤더를 `##`로 추출함 (예: `## **1 Introduction**`). 이 경우:
- 모든 `##` 헤더가 루트 노드(depth=0)가 됨
- `###` 이하가 없으므로 자식 없는 평면 리스트가 됨
- 이는 계층 트리 알고리즘의 자연스러운 결과이며, 별도 분기 불필요

---

## 4. 섹션 분할 알고리즘

### 정규식 패턴

```python
HEADER_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
```

### 알고리즘

```
1. 정규식으로 모든 헤더 위치와 레벨을 수집
2. 각 헤더의 본문 범위 = 헤더 끝 ~ 다음 헤더 시작 (또는 문서 끝)
3. "## Abstract"를 발견하면 # 레벨로 승격
4. # 헤더 → 새 루트 ConceptNode (depth=0)
5. ## 헤더 → 직전 # 루트의 children에 추가 (depth=1)
6. ### 헤더 → 직전 ## 노드의 children에 추가 (depth=2)
7. 필터링 규칙 적용 (References, Acknowledgments 제외)
```

### 첫 헤더 앞 본문 처리

Attention 논문의 경우, 첫 `## Abstract` 앞에 173자의 저작권 고지가 있음.

**결정: 첫 헤더 앞 본문은 버린다.** 이 부분은 대부분 저작권 고지, 제목 반복, 저자 정보 등이며 개념 설명이 아님.

### 헤더 뒤 본문 범위

현재 헤더의 본문 = 현재 헤더 줄 끝 ~ 같거나 높은 레벨의 다음 헤더 시작.

단, 하위 헤더는 본문에 포함하지 않음. 예를 들어 `# Model Architecture` 아래에 `## Attention`이 있으면:
- `# Model Architecture`의 source_excerpt = `#` 헤더와 첫 `##` 사이의 본문만
- `## Attention`의 source_excerpt = `##` 헤더와 다음 `##` 또는 `#` 사이의 본문

---

## 5. ConceptNode 필드 매핑

| 필드 | 값 | 비고 |
|------|------|------|
| `concept` | 헤더 텍스트, 전처리 적용 | 아래 전처리 규칙 참조 |
| `source_excerpt` | 해당 섹션의 본문 (strip 적용) | 하위 헤더 이전까지 |
| `explanation` | `""` (빈 문자열) | expander가 나중에 채움 |
| `id` | 자동 생성 (uuid4().hex[:10]) | ConceptNode 기본값 |
| `depth` | `#`=0, `##`=1, `###`=2 | 계층 트리 기준 |
| `parent_id` | 부모 노드의 id (루트는 None) | 계층 트리 기준 |
| `children` | 하위 레벨 ConceptNode 리스트 | 계층 트리 기준 |
| `is_leaf` | False | expander가 판정 |
| `status` | "pending" | 초기값 |
| `duplicate_of` | None | 초기값 |
| `failed_errors` | None | 초기값 |
| `verification` | {} | 초기값 |

### concept 전처리 규칙

헤더 텍스트에서 다음을 제거:

1. **볼드 마크 `**`**: `## **Multi-Head Attention**` → `Multi-Head Attention`
2. **섹션 번호**: `## **1 Introduction**` → `Introduction`, `## **2.1 Matching logits...**` → `Matching logits...`
3. **앞뒤 공백**: strip

```python
def _clean_header(text: str) -> str:
    text = text.strip()
    text = text.replace("**", "")  # 볼드 제거
    text = re.sub(r"^\d+(\.\d+)*\s+", "", text)  # 섹션 번호 제거
    return text.strip()
```

근거: concept은 "개념 이름"으로 사용됨. 볼드 마크와 섹션 번호는 포맷팅 잔재이지 개념의 일부가 아님. pymupdf4llm 출력에서 `## **2.1 Matching logits is a special case of distillation**` 같은 헤더가 나오므로 전처리 필수.

---

## 6. 필터링 규칙

### chunker에서 필터링한다

| 결정 | 근거 |
|------|------|
| chunker에서 필터 | main.py의 책임을 줄임. chunker가 "의미 있는 섹션"만 반환하는 것이 단일 책임에 부합 |

### 제외 대상 (대소문자 무시)

```python
_EXCLUDED_SECTIONS = {
    "references",
    "bibliography",
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
}
```

이 집합에 포함되는 concept(전처리 후)을 가진 루트 노드는 결과에서 제외.

### 포함 대상 (필터링 안 함)

Abstract, Introduction, Background, Related Work, Method, Model Architecture, Experiments, Results, Discussion, Conclusion, Appendix — 이름에 관계없이 위 제외 목록에 없으면 모두 포함.

### Appendix 처리

Appendix는 제외하지 않음. AI 논문의 appendix에는 모델 세부 사항, 추가 실험, 수학 유도 등 학부생에게 유용한 내용이 있을 수 있음. expander가 개별적으로 "이 개념은 leaf"라고 판정하면 됨.

### "Attention Visualizations" 같은 짧은 섹션

25자(Attention 논문 기준)밖에 안 되는 이 섹션은 제외할지? **제외하지 않는다.** 짧다는 것 자체가 문제가 아니며, expander가 "내용이 부족하니 leaf"로 판정할 수 있음. chunker는 내용의 양이나 질로 필터링하지 않고, 이름 기반 필터만 적용.

---

## 7. 엣지 케이스

### 헤더가 0개

```python
if not headers:
    # Markdown 전체를 하나의 루트 노드로 (concept="전체 문서")
    return [ConceptNode(concept="전체 문서", source_excerpt=markdown.strip())]
```

가능성 낮지만 방어 필요. 모든 텍스트가 헤더 없이 연속되는 경우.

### 첫 헤더 앞 본문이 긴 경우

버린다 (§4에서 결정). 논문의 도입부/저작권 고지/제목 반복이 대부분.

### 빈 섹션 (헤더만 있고 본문 없음)

source_excerpt가 빈 문자열이 됨. 문제없음. expander가 이 노드를 만나면 concept 이름만으로 설명을 생성할 수 있음. `# Results` 아래에 바로 `## Machine Translation`이 나오는 Attention 논문의 실제 패턴 (0자).

### 너무 짧은 섹션 (50자 미만)

필터링하지 않는다. chunker는 길이로 판단하지 않음.

### 중복 섹션 제목

ConceptNode의 id는 uuid4로 자동 생성되므로 중복 제목이 있어도 문제없음. concept_cache가 나중에 중복 개념을 감지하는 역할.

### ## 가 # 없이 시작되는 경우 (pymupdf4llm)

pymupdf4llm 출력은 모든 헤더가 `##`임. `#` 루트가 없는 상태에서 `##`가 나오면:
- `##`를 루트(depth=0)로 승격
- 이는 계층 트리 알고리즘에서 "현재 루트가 없으면 새 루트를 만든다" 규칙으로 자연스럽게 처리됨

---

## 8. 가장 까다로울 것 같은 부분

### ① 두 파서의 헤더 형식 차이

arxiv_parser 출력과 pymupdf4llm 출력의 헤더 형식이 다르다:

| 파서 | 예시 헤더 | 특징 |
|------|----------|------|
| arxiv_parser | `# Introduction` | 계층적 (#, ##, ###), 깔끔 |
| pymupdf4llm | `## **1 Introduction**` | 모두 ##, 볼드, 번호 포함 |

chunker는 두 형식을 모두 처리해야 함. `_clean_header`로 볼드와 번호를 제거하면 통합 가능. 계층 트리 알고리즘은 `#`이 없으면 `##`를 루트로 승격하므로 pymupdf4llm 출력도 자연스럽게 처리됨.

### ② 상위 레벨 없이 하위 레벨이 나오는 경우의 부모 결정

예를 들어 `# Model Architecture` 다음에 바로 `### Scaled Dot-Product Attention`이 나오면 (## 없이), 이 `###`의 부모는 누구인가?

**결정: 직전의 가장 가까운 상위 레벨 노드를 부모로 한다.** 즉 `###`의 부모가 `#`이 됨 (depth=1로 승격). 실제로는 이 케이스가 거의 발생하지 않지만, 방어 코드 필요.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
