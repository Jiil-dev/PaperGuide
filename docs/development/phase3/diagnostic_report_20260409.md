# Phase 3 진단 보고

**진단 일시**: 2026-04-09
**대상**: samples/_tmp_phase3/end_to_end_attention_mini.md

---

## 진단 1: assembler Part 2 렌더링

`_render_part2_node` (assembler.py:256-266) 코드:

```python
def _render_part2_node(lines, node, section_num, depth):
    heading_level = "#" * (3 + depth)      # depth=0 → ###, depth=4 → #######
    lines.append(f"{heading_level} {section_num} {node.concept}\n")
    if node.explanation:                    # ★ 빈 문자열이면 출력하지 않음
        lines.append(node.explanation + "\n")
    for child_idx, child in enumerate(node.children, start=1):
        child_section = f"{section_num}.{child_idx}"
        _render_part2_node(lines, child, child_section, depth + 1)  # depth + 1
```

**발견 사항:**
- `node.explanation`이 빈 문자열(`""`)이면 본문이 출력되지 않음
- `node.status`는 전혀 확인하지 않음 — `duplicate`, `failed`, `pending` 이든 무관하게 헤더만 출력
- `depth` 파라미터는 재귀 호출마다 +1 증가 — node.depth와 무관하게 assembler 자체 카운터
- `children`이 빈 리스트면 자식 렌더링 없음

**의심 지점:** Abstract 루트 노드가 `explanation=""`이고 `children=[]`인 상태로 assembler에 전달되었을 가능성.

---

## 진단 2: main.py 파이프라인

main.py:256-271 코드:

```python
part2_trees = []
for section in sections:
    root = ConceptNode(
        concept=section.title,       # "Abstract"
        source_excerpt=section.content,  # 564 chars
        depth=0,
        part=2,
    )
    try:
        expander.expand(root)        # in-place 수정
    except RateLimitExceeded as e:
        ...
        break                        # ★ break — append 전에 탈출
    part2_trees.append(root)         # expand 후 append
```

**발견 사항:**
- `expander.expand(root)`는 in-place 수정이므로 반환값 없음
- `expand()` 내부에서 노드가 `duplicate`로 판정되면 `explanation=""`인 채로 즉시 return
- `part2_trees.append(root)`는 expand 후 항상 실행됨 (RateLimitExceeded가 아닌 한)
- 따라서 Abstract 노드가 `duplicate` 상태(explanation 비어있고, children 없음)로 part2_trees에 추가되었음

**중간 checkpoint 없음** — Phase 3 파이프라인에는 checkpoint 저장/로드 로직이 없음.

---

## 진단 3: expander 재귀 제어

expander.py:235-339 코드:

```python
force_leaf = root.depth >= self._max_depth     # depth >= 4 → leaf 강제

# 캐시 중복 체크 (해시 + 임베딩)
dup_id = self._cache.lookup(root.concept, brief=root.source_excerpt[:200])
if dup_id is not None:
    root.status = "duplicate"
    root.duplicate_of = dup_id
    self._notify(root)
    return                                      # ★ explanation 생성 없이 즉시 반환

# 자식 생성 시:
child = ConceptNode(
    ...
    depth=root.depth + 1,                       # 부모 depth + 1
)
```

**발견 사항:**
- `max_depth` 체크: `root.depth >= self._max_depth` (4 이상이면 leaf 강제)
- depth 증가: 자식 생성 시 `root.depth + 1`
- root(depth=0) → child(1) → grandchild(2) → gg(3) → ggg(4=leaf)
- depth=4 노드도 explanation은 생성됨 (force_leaf은 children 생성만 막음)
- **캐시 중복 판정 시** `explanation=""`인 채로 즉시 return — 이것이 Abstract 문제의 원인

---

## 진단 4: 빈 헤더 분포

```
Level | Filled | Empty | Total
----------------------------------------
  3   |     7  |    27 |    34
  4   |   212  |     0 |   212
  5   |     8  |     7 |    15
  6   |    20  |    10 |    30
  7   |    33  |    32 |    65
```

**발견 사항:**
- Level 3 (###): 34개 중 27개가 비어있음 → Part 3의 ### 헤더(topic title)들이 비어있는 것은 아닌지 확인 필요. 하지만 Part 2의 루트 노드(depth=0)도 ### 이므로, Abstract처럼 duplicate된 노드들이 빈 헤더를 만들었을 수 있음.
- Level 4 (####): 212개 전부 채워져 있음 → 정상적인 depth=1 자식 노드들
- Level 5~7: 빈 것들이 상당수 → duplicate나 verification_failed 노드들
- **Level 7이 65개로 Level 5(15개)보다 많음** → 비정상적. 피라미드가 뒤집힘. depth=4 노드가 가장 많은 것 자체는 정상이지만 (leaf 강제 전 자식이 많이 생김), 빈 노드 비율이 높다는 것은 duplicate/failed가 많다는 의미.

---

## 진단 5: Introduction root

Introduction root(### 2.2 Introduction) 에는 **본문이 정상적으로 존재함**:

> 저자는 이 Introduction에서 하나의 명확한 논증 흐름을 전개한다: "기존 순환 모델(RNN, LSTM, GRU)이 순차 연산이라는 근본적 병목을 가지고 있고, 어텐션 메커니즘은 유망하지만 여전히 순환 네트워크에 종속되어 사용되어 왔으므로..." (4개 문단, 충분한 분량)

Introduction → 자식(#### 2.2.1) 도 정상 연결됨.

---

## 진단 6: expander 출력 트리 (개별 테스트, 55노드)

```
depth 0: 1
depth 1: 3
depth 2: 4
depth 3: 15
depth 4: 32

status:
  done: 33
  duplicate: 9
  verification_failed: 4
  pending: 9

빈 explanation: 17개 (전부 duplicate 또는 pending)
```

**발견 사항:**
- depth=4가 32개로 가장 많음 → 정상 (leaf 노드)
- duplicate=9개 → concept_cache 중복 탐지가 적극적
- pending=9개 → RateLimitExceeded로 미완성
- **빈 explanation=17개** → duplicate와 pending 노드들. 이들이 assembler에서 빈 헤더가 됨.

---

## 진단 7: checkpoint

- `data/checkpoints/`: 존재하지 않음
- `checkpoints/`: 디렉토리 존재하지만 비어있음
- Phase 3 파이프라인에 checkpoint 로직 없음 (Phase 2 전용)

---

## 진단 8: RawSection (chunker)

```
order=1 title="Abstract"     content_len=564
order=2 title="Introduction"  content_len=2127
```

정상. 2개 섹션, 각각 title과 content가 적절히 채워져 있음.

---

## 원인 가설

### 문제 1: Abstract가 최종 Markdown에서 빈 이유

**근본 원인: Phase 2에서 남은 concept_cache에 "Abstract"가 이미 등록되어 있었음.**

증거 체인:
1. `data/cache/concept_cache/concepts.jsonl`에 `{"concept": "Abstract", "id": "dcf316b41e"}` 이 이미 존재 (Phase 2 실행 잔존물)
2. end-to-end 실행 시 `--cache-dir`를 지정하지 않았으므로 config 기본값 `data/cache`를 사용
3. `ConceptCache`가 `data/cache/concept_cache/`를 로드
4. expander가 Abstract 노드를 처리할 때, `self._cache.lookup("Abstract", ...)` 호출
5. 정규화 이름 해시(`"abstract"` → MD5) 가 기존 캐시 항목과 완전 일치
6. `lookup()`이 기존 node_id (`dcf316b41e`)를 반환 → **duplicate 판정**
7. expander가 `root.status = "duplicate"`, `root.explanation = ""` (초기값 그대로), `root.children = []` (초기값 그대로) 인 상태로 즉시 return
8. main.py가 이 빈 노드를 `part2_trees`에 append
9. assembler `_render_part2_node`가 헤더(`### 2.1 Abstract`)만 출력하고, `explanation`이 빈 문자열이므로 본문 건너뜀, `children`이 빈 리스트이므로 자식 없음

**로그 증거:** end-to-end 로그에서 Abstract 줄 `depth=0 Abstract` 이후 자식 로그 없이 바로 Introduction으로 넘어감. `[status]` 부분이 rich Console의 `[duplicate]`를 마크업으로 해석하여 표시되지 않은 것으로 추정.

**Introduction이 정상인 이유:** "Introduction"이라는 concept 이름은 Phase 2 캐시에 없거나 (Phase 2에서 다른 이름으로 등록), 해시/임베딩이 일치하지 않았기 때문.

### 문제 2: 헤더 깊이가 Level 7까지 간 이유

**근본 원인: assembler의 `depth` 파라미터가 ConceptNode의 `depth` 필드가 아닌, 재귀 호출 깊이를 사용하기 때문.**

계산 구조:
- `_render_part2_node`의 `depth` 인자는 0에서 시작하여 재귀 호출마다 +1
- `heading_level = "#" * (3 + depth)` 이므로:
  - 루트 (depth=0) → `###` (Level 3)
  - 자식 (depth=1) → `####` (Level 4)
  - 손자 (depth=2) → `#####` (Level 5)
  - 증손자 (depth=3) → `######` (Level 6)
  - 고손자 (depth=4) → `#######` (Level 7)

config의 `part2.max_depth=4`는 **expander의 ConceptNode.depth 기준**이다. depth=4인 노드에서 `force_leaf=True`가 되어 더 이상 자식을 생성하지 않지만, **depth=4 노드 자체는 존재하고 explanation도 생성된다.** 이 depth=4 노드가 assembler에서 `depth` 파라미터 4로 렌더링되어 `#######` (Level 7)이 됨.

따라서 `max_depth=4`일 때 헤더가 Level 7까지 나오는 것은 **현재 코드의 정상 동작**이다. 문제는 사양(max_depth=4)의 의미를 "최대 깊이 4 → 최대 하위 헤더 레벨"로 해석할 때 발생하는 기대 불일치이다. Markdown에서 `#######`은 표준 헤더가 아니다 (표준은 `######` 까지).

**Level 5=15 < Level 7=65인 피라미드 역전 현상:**
- depth=2 노드(Level 5)는 보통 2~3개 (root의 손자)
- depth=4 노드(Level 7)는 leaf이지만, depth=3의 각 노드가 2~5개의 depth=4 자식을 생성하므로 누적으로 가장 많아짐
- 이것은 트리의 정상적 구조 (잎 노드가 가장 많음)

---

**보고서 끝. 코드 수정 없이 진단만 완료.**
