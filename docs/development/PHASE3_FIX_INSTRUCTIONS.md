# Phase 3 수정 지시 — 두 가지 구조적 문제 해결

**작성자**: 웹 Claude (설계)
**작성일**: 2026-04-09
**실행자**: Claude Code
**전제**: docs/phase3/diagnostic_report_20260409.md 의 진단 완료된 상태
**예상 소요**: 2~4 시간 (cache 클리어 후 재실행 포함)

---

## 해결해야 할 두 문제 (진단 결과 확정)

### 문제 1: Abstract 가 최종 Markdown 에서 빈 상태
**원인**: Phase 2 잔존 `concept_cache` 가 "Abstract" 를 중복으로 판정.

Phase 2 의 bottom-up 구조에서 "Abstract" 는 기초 개념이었지만, Phase 3 의 top-down 구조에서는 **논문 섹션 이름** (구조적 마커) 이다. 섹션 이름은 중복 감지 대상이 아니다. 같은 논문 안에서 저자의 하위 논점이 반복되는 것도 정상이다.

**해결**: Phase 3 Part 2 처리에서 concept_cache 를 비활성화한다. Part 3 (기초 지식) 은 그대로 유지 — 거기서는 중복 감지가 의미 있다.

### 문제 2: 헤더가 Level 7 (`#######`) 까지 깊어짐
**원인**: `assembler._render_part2_node` 의 `heading_level = "#" * (3 + depth)` 와 `part2.max_depth = 4` 가 결합되어 depth=4 노드가 Level 7 헤더가 됨. Markdown 표준은 Level 6 까지이고, 책 읽는 경험상 Level 7 은 독자가 "지금 어디 있는지" 를 잃게 만든다.

**해결**: 
- `part2.max_depth: 4 → 2` 로 축소
- expander 프롬프트에 "하위 논점은 자식 노드가 아니라 본문 문단으로" 원칙 추가
- assembler 에 방어적 상한 `min(3+depth, 6)` 추가

---

## 절대 규칙

1. **수정 범위 엄격 제한** — 아래 명시된 4 개 파일만 수정:
   - `src/expander.py`
   - `src/assembler.py`
   - `config.yaml`
   - (선택) `src/main.py` — 재실행 시 cache_dir 플래그 확인용

   그 외 파일 수정 금지.

2. **기존 API 유지** — 공개 함수 시그니처 변경 금지. 내부 로직만 수정.

3. **수정 후 작은 테스트 먼저** — 전체 end-to-end 전에 Abstract 섹션만 단독 테스트.

4. **에러 처리**:
   - 수정 중 문법 오류 → 즉시 롤백 후 다시 시도
   - 테스트 실패 → 보고서에 기록 후 중단 (전체 재실행 금지)
   - 3 단계 연속 실패 → 전체 중단

5. **커밋 메시지 단어 제한**: "verified", "success", "perfect" 사용 금지. "tested", "implemented", "fixed" 사용.

6. **재실행 시 반드시 Phase 2 cache 클리어**: `data/cache/concept_cache/` 를 백업 후 삭제. 이게 이번 문제의 근본 원인이었음.

---

## 단계 1. concept_cache Phase 3 Part 2 비활성화

### 1.1. 현재 expander 확인

```bash
cd /home/engineer/j0061/paper-analyzer
cat src/expander.py | grep -B 2 -A 10 "self._cache.lookup\|cache.lookup"
```

`_cache.lookup()` 호출이 어디에서 일어나는지 정확히 파악.

### 1.2. Expander 클래스에 `use_cache` 파라미터 추가

`src/expander.py` 의 `Expander.__init__` 에 파라미터 추가:

```python
class Expander:
    def __init__(
        self,
        client,
        verifier,
        cache,                    # 기존
        max_depth,
        max_children_per_node,
        max_retries,
        on_node_done=None,
        use_cache: bool = True,   # 신규 — Phase 3 Part 2 에서는 False
    ):
        self._client = client
        self._verifier = verifier
        self._cache = cache
        self._max_depth = max_depth
        self._max_children_per_node = max_children_per_node
        self._max_retries = max_retries
        self._on_node_done = on_node_done
        self._use_cache = use_cache  # 신규
```

그리고 `expand()` 함수 내에서 cache lookup 부분을 조건부로 변경:

**기존 (추측)**:
```python
# 캐시 중복 체크
dup_id = self._cache.lookup(root.concept, brief=root.source_excerpt[:200])
if dup_id is not None:
    root.status = "duplicate"
    root.duplicate_of = dup_id
    self._notify(root)
    return
```

**수정 후**:
```python
# 캐시 중복 체크 (Phase 3 Part 2 에서는 use_cache=False 로 비활성화)
if self._use_cache:
    dup_id = self._cache.lookup(root.concept, brief=root.source_excerpt[:200])
    if dup_id is not None:
        root.status = "duplicate"
        root.duplicate_of = dup_id
        self._notify(root)
        return
```

또한 expand() 내부에서 `self._cache.add()` 같은 캐시 추가 호출이 있다면 그것도 `if self._use_cache:` 로 감쌀 것. 정확한 위치는 `grep -n "self._cache" src/expander.py` 로 확인.

### 1.3. main.py 에서 Phase 3 호출 시 `use_cache=False` 전달

`src/main.py` 의 `run_phase3_pipeline()` 에서 Expander 생성 부분을 찾아 `use_cache=False` 추가:

```bash
grep -B 2 -A 15 "Expander(" src/main.py
```

기존:
```python
expander = Expander(
    client=client,
    verifier=verifier,
    cache=concept_cache,
    max_depth=config.part2.max_depth,
    max_children_per_node=config.part2.max_children_per_node,
    max_retries=config.verification.max_retries,
    on_node_done=...,
)
```

수정 후 (Phase 3 파이프라인에서만):
```python
expander = Expander(
    client=client,
    verifier=verifier,
    cache=concept_cache,
    max_depth=config.part2.max_depth,
    max_children_per_node=config.part2.max_children_per_node,
    max_retries=config.verification.max_retries,
    on_node_done=...,
    use_cache=False,  # Phase 3: Part 2 는 논문 섹션이므로 중복 감지 불필요
)
```

**주의**: 만약 main.py 에 `run_phase2_pipeline` 도 있다면 그 안의 Expander 는 건드리지 말 것. Phase 2 호환성 유지.

### 1.4. 단위 테스트

```bash
.venv/bin/python -c "
from pathlib import Path
from src.claude_client import ClaudeClient
from src.config import load_config
from src.concept_cache import ConceptCache
from src.verifier import Verifier
from src.expander import Expander

client = ClaudeClient(mode='dry_run')
config = load_config('config.yaml')
cache = ConceptCache(
    cache_dir=Path('/tmp/test_cache'),
    model_name=config.dedup.embedding_model,
    threshold=config.dedup.similarity_threshold,
)
verifier = Verifier(client=client, min_confidence=config.verification.min_confidence)

# use_cache=False 로 생성 가능한지
expander_no_cache = Expander(
    client=client, verifier=verifier, cache=cache,
    max_depth=2, max_children_per_node=5, max_retries=2,
    use_cache=False,
)
print(f'use_cache=False 로 생성 OK')
print(f'_use_cache 속성: {expander_no_cache._use_cache}')

# 기본값 True 인지
expander_default = Expander(
    client=client, verifier=verifier, cache=cache,
    max_depth=2, max_children_per_node=5, max_retries=2,
)
print(f'기본값 _use_cache: {expander_default._use_cache}')
assert expander_default._use_cache == True, 'default should be True for Phase 2 compat'
print('expander use_cache 옵션 OK')
"
```

### 1.5. 커밋 1

```bash
git add src/expander.py src/main.py
git commit -m "fix(expander): add use_cache flag to disable dedup for Phase 3 Part 2

- new parameter use_cache (default True for Phase 2 compat)
- Phase 3 run_phase3_pipeline passes use_cache=False
- reason: Part 2 root nodes are paper section names (Abstract, Introduction,
  etc.), not concepts. They should not be deduplicated across runs.
- fixes issue where Phase 2 leftover cache marked 'Abstract' as duplicate,
  causing empty root node in Part 2 rendering
- Phase 2 run_phase2_pipeline unchanged (use_cache defaults to True)"
git log --oneline -3
```

---

## 단계 2. config.yaml max_depth 축소

### 2.1. 수정

`config.yaml` 의 `part2.max_depth` 값 변경:

```bash
# 현재 값 확인
grep -A 5 "^part2:" config.yaml
```

`max_depth: 4` → `max_depth: 2` 로 변경.

수정 후:
```yaml
part2:
  max_depth: 2                # 이전 4 → 2 (헤더 Level 3~5 로 제한)
  max_children_per_node: 5
  use_placeholders: true
```

### 2.2. 효과 계산

- depth=0 (루트, 논문 섹션) → assembler Level 3 (`###`)
- depth=1 (논문 subsection 또는 섹션 내 큰 흐름) → assembler Level 4 (`####`)
- depth=2 (leaf, 중간 논점) → assembler Level 5 (`#####`)
- depth=3+ 는 만들어지지 않음

결과: 헤더 최대 Level 5. 그 이하 세부 논점은 expander 프롬프트 변경으로 본문 문단 처리.

### 2.3. 검증

```bash
.venv/bin/python -c "
from src.config import load_config
config = load_config('config.yaml')
print(f'part2.max_depth: {config.part2.max_depth}')
assert config.part2.max_depth == 2
print('config.yaml max_depth OK')
"
```

### 2.4. 커밋 2

```bash
git add config.yaml
git commit -m "fix(config): reduce part2.max_depth from 4 to 2

- old: max_depth=4 produced headers up to Level 7 (#######)
  which exceeds Markdown standard (Level 6 max) and breaks reading flow
- new: max_depth=2 limits headers to Level 5 (#####)
- deeper sub-arguments should be expressed as paragraphs within parent
  node explanation (see expander prompt update in next commit)"
git log --oneline -3
```

---

## 단계 3. expander 프롬프트 "헤더 얕게" 원칙 추가

### 3.1. 현재 프롬프트 확인

```bash
grep -A 100 "_SYSTEM_PROMPT = " src/expander.py | head -130
```

### 3.2. 프롬프트 수정

`src/expander.py` 의 `_SYSTEM_PROMPT` 상수에 다음 원칙을 **기존 원칙 3 (하위 논점 분해) 을 교체**하는 형태로 추가. 원칙 번호는 그대로 유지.

**교체할 부분 (기존 원칙 3)**:
```
### 원칙 3 — 하위 논점 분해
각 섹션을 2~5 개의 "저자가 하는 하위 논점" 으로 분해하십시오.
각 논점이 자식 노드가 됩니다. 각 자식은 다시 재귀적으로 분해됩니다.
```

**새 내용**:
```
### 원칙 3 — 하위 논점은 문단으로, 자식 노드는 얕게

중요: 독자는 책을 읽는 것이지 사양서를 읽는 것이 아닙니다.
3 단계 이상의 목차 구조는 독자가 "지금 어디 있는지" 를 잃게 만듭니다.

자식 노드를 만드는 기준은 매우 엄격합니다:
- 논문이 **명시적으로 subsection 을 나눈 경우만** (예: "3.1 Encoder", "3.2 Attention")
- 또는 섹션이 매우 길어서 **독립된 여러 주제** 를 다루는 경우
- 각 자식은 **200 자 이상의 충분한 explanation** 을 가져야 함

자식 노드를 만들면 안 되는 경우:
- 단순히 "세 가지 관점", "네 가지 한계" 를 나열
- 짧은 하위 논점 (100 자 미만으로 설명 가능한 것)
- 부모 문단 안에서 자연스럽게 이어지는 흐름

**올바른 방식**: 하위 논점이 여러 개 있으면 **부모 노드의 explanation 안에서
문단으로 전개**하십시오. 각 논점의 시작은 **굵은 글씨** 로 표시할 수 있습니다.

예시 — 나쁨 (자식 노드 3 개):
  부모 explanation: "저자는 세 가지 한계를 지적한다."
  자식 1: "첫째 한계: 순차 연산"
  자식 2: "둘째 한계: 병렬화 불가"
  자식 3: "셋째 한계: 장거리 의존성"

예시 — 좋음 (부모 안에 문단):
  부모 explanation: "저자는 RNN 의 세 가지 구조적 한계를 연속적으로 지적한다.

  **첫째, 순차 의존 구조.** 저자가 가장 먼저 지목하는 것은 은닉 상태 연쇄다.
  시간 t 의 상태 h_t 를 계산하려면 반드시 h_{t-1} 이 먼저 계산되어야 하고,
  이 의존성은 건너뛸 수 없다...

  **둘째, GPU 병렬화 불가.** 이 순차 의존 때문에 저자는 GPU 의 병렬 연산 능력을
  활용할 수 없다고 주장한다...

  **셋째, 장거리 의존성 학습 곤란.** 마지막으로 저자는 시퀀스가 길수록 먼 위치 간의
  의미 관계를 학습하기 어려움을 지적한다..."

depth 제한:
- 현재 depth 가 0 이면 자식 생성 허용 (논문 subsection 해설)
- 현재 depth 가 1 이면 자식 생성 신중하게 (꼭 필요한 경우만)
- 현재 depth 가 2 이상이면 자식 생성 금지. is_leaf=true, children=[] 로 응답.

explanation 분량:
- depth=0 (논문 섹션 루트): 3~6 문단, 각 문단 3~5 문장
- depth=1 (subsection): 2~4 문단, 각 문단 3~5 문장
- depth=2 (leaf): 1~3 문단, 충실하게
```

### 3.3. 추가 원칙 — 섹션 스킵 금지 (원칙 N 신규)

`_SYSTEM_PROMPT` 의 기존 원칙들 뒤에 **새 원칙 7** 추가:

```
### 원칙 7 — 논문의 모든 섹션은 빠짐없이 해설

논문에 Abstract 가 있다면 Part 2 에도 Abstract 해설이 반드시 있어야 합니다.
"Part 1 에서 이미 다뤘으니 생략" 은 **절대 금지**.

Part 1 은 논문 전체의 큰 그림이고, Part 2 각 섹션은 **저자가 그 섹션을 어떻게 썼는지**
에 대한 해설입니다. 역할이 다릅니다.

예시 — Abstract 해설:
- 저자가 Abstract 에 **무엇을 강조** 하고 있는가? (전체 논문 중 어느 부분을 골라냈는가)
- 저자가 어떤 **순서** 로 주장을 배치했는가?
- 특정 문구 (예: "based solely on attention mechanisms") 가 왜 그런 표현인가?

explanation 이 비어 있으면 안 됩니다. 최소 3 문단 이상.

만약 섹션 내용이 Part 1 과 겹치는 부분이 있으면, "이 부분의 핵심 내용은 Part 1 의
핵심 주장 부분에서 다룬 것과 겹친다. 여기서는 저자가 Abstract 에서 선택한 '표현 방식' 과
'순서' 에 집중한다" 와 같이 **명시적으로** 독자에게 안내한 뒤 해당 섹션 고유의 관점으로
해설하십시오.
```

### 3.4. explanation 빈 값 방어 로직 추가

`src/expander.py` 의 `expand()` 함수에서 Claude 응답 파싱 후 `explanation` 이 비어 있으면 에러 발생시키도록 수정.

**기존 (추측)**:
```python
result = self._call_expand(root, allow_new_children, previous_errors)
root.explanation = result.get("explanation", "")
root.prerequisites = result.get("prerequisites", [])
```

**수정 후**:
```python
result = self._call_expand(root, allow_new_children, previous_errors)
explanation = result.get("explanation", "").strip()

# 빈 explanation 방어
if not explanation:
    raise ValueError(
        f"expander: empty explanation returned for node '{root.concept}' "
        f"(depth={root.depth}). This indicates a prompt issue or Claude error."
    )

root.explanation = explanation
root.prerequisites = result.get("prerequisites", [])
```

이렇게 하면 만약 Claude 가 빈 응답을 내면 **재시도 루프** 가 돌거나 (max_retries 내에서) 결국 에러로 중단됩니다. 조용히 빈 노드가 저장되는 일은 없어집니다.

### 3.5. 단위 테스트

```bash
.venv/bin/python -c "
import src.expander as e
# 프롬프트에 새 원칙이 포함됐는지 확인
assert '원칙 3' in e._SYSTEM_PROMPT
assert '문단' in e._SYSTEM_PROMPT
assert '원칙 7' in e._SYSTEM_PROMPT or '모든 섹션' in e._SYSTEM_PROMPT
assert 'Abstract' in e._SYSTEM_PROMPT
print('expander prompt updated OK')
print(f'prompt length: {len(e._SYSTEM_PROMPT)} chars')
"
```

### 3.6. 커밋 3

```bash
git add src/expander.py
git commit -m "fix(expander): add depth discipline and no-skip principles to prompt

- principle 3 rewritten: sub-arguments as paragraphs not child nodes
  - strict criteria for creating child nodes
  - explicit good/bad examples
  - depth-based guidance: depth>=2 must be leaf
- new principle 7: every paper section must be fully explained
  - forbids 'already covered in Part 1' skip
  - requires minimum 3 paragraphs explanation
- added defensive check: empty explanation raises ValueError
  - prevents silent empty nodes from slipping through
  - caught by verify-retry loop"
git log --oneline -3
```

---

## 단계 4. assembler 헤더 상한 방어 (선택, 권장)

### 4.1. 수정

`src/assembler.py` 의 `_render_part2_node` 에서 heading_level 계산 수정:

**기존**:
```python
def _render_part2_node(lines, node, section_num, depth):
    heading_level = "#" * (3 + depth)
    lines.append(f"{heading_level} {section_num} {node.concept}\n")
    ...
```

**수정 후**:
```python
_MAX_HEADER_LEVEL = 6  # Markdown 표준 상한

def _render_part2_node(lines, node, section_num, depth):
    level = min(3 + depth, _MAX_HEADER_LEVEL)
    heading_level = "#" * level
    lines.append(f"{heading_level} {section_num} {node.concept}\n")
    ...
```

이제 max_depth=2 로 축소했으므로 실제로는 Level 5 까지만 나오지만, 방어적 상한을 두어 향후 설정이 바뀌어도 Markdown 표준을 벗어나지 않도록 한다.

### 4.2. 단위 테스트

```bash
.venv/bin/python << 'PYEOF'
from pathlib import Path
from src.tree import ConceptNode
from src.data_types import PaperAnalysis
from src.assembler import assemble_3part_guidebook

# 극단적으로 깊은 트리 (depth 7) 만들어 상한 테스트
analysis = PaperAnalysis(
    title='Test', core_thesis='x', problem_statement='x',
    key_contributions=['x'], main_results=['x'],
    significance='x', reading_guide='x', paper_structure=['S'],
)

# 수동으로 매우 깊은 체인 생성
root = ConceptNode(concept='root', source_excerpt='x', explanation='root body', part=2)
cur = root
for i in range(10):
    child = ConceptNode(concept=f'd{i+1}', source_excerpt='x',
                        explanation=f'depth {i+1} body', part=2)
    cur.children = [child]
    cur = child

md = assemble_3part_guidebook(analysis, [root], [])

# Level 7+ 헤더가 없는지 확인
import re
max_level = 0
for line in md.split('\n'):
    m = re.match(r'^(#+) ', line)
    if m:
        max_level = max(max_level, len(m.group(1)))

print(f'max header level in output: {max_level}')
assert max_level <= 6, f'header exceeded Markdown standard: Level {max_level}'
print('assembler header level cap OK')
PYEOF
```

### 4.3. 커밋 4

```bash
git add src/assembler.py
git commit -m "fix(assembler): cap header level at Markdown max (Level 6)

- defensive cap: min(3 + depth, 6)
- prevents #######+ headers that exceed Markdown standard
- with current config (max_depth=2) this cap is not reached,
  but protects against future config changes"
git log --oneline -3
```

---

## 단계 5. 재실행 전 cache 클리어

### 5.1. 기존 cache 백업 + 삭제

```bash
cd /home/engineer/j0061/paper-analyzer

# Phase 2 concept_cache 백업
if [ -d data/cache/concept_cache ]; then
    mkdir -p backups
    tar -czf backups/concept_cache_phase2_$(date +%Y%m%d_%H%M%S).tar.gz data/cache/concept_cache/
    echo "Phase 2 concept_cache 백업 완료"
    ls -la backups/
fi

# 삭제 — Phase 3 Part 2 는 use_cache=False 라서 영향 없지만, Part 3 에서도 깨끗한 상태로 시작
rm -rf data/cache/concept_cache/
echo "data/cache/concept_cache/ 삭제됨"

# samples 쪽도 깨끗이
rm -rf samples/_tmp_phase3/cache/concept_cache/
echo "samples/_tmp_phase3/cache/concept_cache/ 삭제됨"

# 기존 end-to-end 결과 백업
if [ -f samples/_tmp_phase3/end_to_end_attention_mini.md ]; then
    cp samples/_tmp_phase3/end_to_end_attention_mini.md \
       samples/_tmp_phase3/end_to_end_attention_mini_v1.md
    cp samples/_tmp_phase3/end_to_end_stats.json \
       samples/_tmp_phase3/end_to_end_stats_v1.json
    echo "v1 결과 백업 완료"
fi

# Claude 응답 cache 는 유지 — paper_analyzer 결과 재사용 가능
ls -la samples/_tmp_phase3/cache/ 2>&1
```

### 5.2. 커밋

```bash
git add backups/ samples/_tmp_phase3/end_to_end_attention_mini_v1.md samples/_tmp_phase3/end_to_end_stats_v1.json 2>/dev/null
git status
# 커밋할 것이 있으면
git commit -m "chore: backup v1 output and Phase 2 concept_cache before re-run" 2>/dev/null || echo "nothing to commit"
```

---

## 단계 6. 작은 테스트 — Abstract 단독 확장

전체 재실행 전에 Abstract 섹션만 단독으로 expander 돌려서 수정이 제대로 작동하는지 확인.

```bash
.venv/bin/python << 'PYEOF'
import json
from pathlib import Path
from src.claude_client import ClaudeClient
from src.config import load_config
from src.arxiv_parser import parse_arxiv
from src.chunker import split_into_raw_sections
from src.tree import ConceptNode
from src.concept_cache import ConceptCache
from src.verifier import Verifier
from src.expander import Expander

client = ClaudeClient(
    mode='cache',
    cache_dir=Path('samples/_tmp_phase3/cache'),
    max_total_calls=20,
    sleep_between_calls=2,
)
config = load_config('config.yaml')

print(f'config.part2.max_depth: {config.part2.max_depth}')
assert config.part2.max_depth == 2, 'max_depth should be 2'

result = parse_arxiv(Path('data/papers/attention_mini'))
sections = split_into_raw_sections(result.markdown)
abstract_section = sections[0]
print(f'테스트 입력: {abstract_section.title} ({len(abstract_section.content)} chars)')

root = ConceptNode(
    concept=abstract_section.title,
    source_excerpt=abstract_section.content,
    depth=0,
    part=2,
)

# fresh cache
cache = ConceptCache(
    cache_dir=Path('/tmp/test_abstract_cache'),
    model_name=config.dedup.embedding_model,
    threshold=config.dedup.similarity_threshold,
)
verifier = Verifier(client=client, min_confidence=config.verification.min_confidence)

# use_cache=False 로 expander 생성
expander = Expander(
    client=client, verifier=verifier, cache=cache,
    max_depth=config.part2.max_depth,
    max_children_per_node=config.part2.max_children_per_node,
    max_retries=config.verification.max_retries,
    on_node_done=lambda n: print(f'  [{n.status}] depth={n.depth} {n.concept} (exp_len={len(n.explanation or "")})'),
    use_cache=False,
)

print('Abstract 확장 시작 (use_cache=False, max_depth=2)...')
try:
    expander.expand(root)
except Exception as e:
    print(f'에러: {type(e).__name__}: {e}')

# 결과 저장
def tree_to_dict(node):
    return {
        'concept': node.concept,
        'explanation': node.explanation,
        'prerequisites': node.prerequisites,
        'depth': node.depth,
        'status': node.status,
        'is_leaf': node.is_leaf,
        'children': [tree_to_dict(c) for c in node.children],
    }

tree_data = tree_to_dict(root)
output_path = Path('samples/_tmp_phase3/expander_abstract_v2.json')
output_path.write_text(json.dumps(tree_data, ensure_ascii=False, indent=2))
print(f'\n결과 저장: {output_path}')

# 핵심 검증
print(f'\n=== 검증 ===')
print(f'Abstract 루트 status: {root.status}')
print(f'Abstract 루트 explanation 길이: {len(root.explanation or "")}')
print(f'Abstract 루트 children 수: {len(root.children)}')

def get_max_depth(n, d=0):
    if not n.children:
        return d
    return max(get_max_depth(c, d+1) for c in n.children)

max_d = get_max_depth(root)
print(f'트리 최대 depth: {max_d}')

# 검증
if root.status == 'duplicate':
    print('❌ 여전히 duplicate — use_cache=False 가 적용 안 됐거나 다른 문제')
elif not root.explanation or not root.explanation.strip():
    print('❌ explanation 이 비어있음')
elif max_d > 2:
    print(f'❌ max_depth 초과: {max_d}')
else:
    print('✅ 모든 체크 통과')

stats = client.get_stats()
print(f'\nstats: {stats}')
PYEOF
```

**예상 결과**:
- `status: done` (duplicate 아님)
- `explanation 길이: 500+` (비어있지 않음)
- `children 수: 2~5` (적절한 자식)
- `트리 최대 depth: <= 2` (헤더 Level 3~5)

만약 하나라도 실패하면 **end-to-end 재실행 금지**. 보고서에 기록하고 중단.

### 6.1. 결과 커밋

```bash
git add samples/_tmp_phase3/expander_abstract_v2.json 2>/dev/null
git commit -m "test(expander): verify Abstract expansion after fixes

- cache disabled (use_cache=False)
- max_depth=2 enforced
- empty explanation guard active
- output saved for review" 2>/dev/null || echo "nothing new to commit"
```

---

## 단계 7. 전체 end-to-end 재실행

단계 6 이 성공한 경우에만 진행.

### 7.1. 실행

```bash
time .venv/bin/python -m src.main \
    --input data/papers/attention_mini \
    --output samples/_tmp_phase3/end_to_end_attention_mini_v2.md \
    --mode cache \
    --cache-dir samples/_tmp_phase3/cache \
    --phase 3 2>&1 | tee samples/_tmp_phase3/end_to_end_log_v2.txt
```

**중요**: `--cache-dir samples/_tmp_phase3/cache` 를 명시해야 Phase 2 잔존 cache 가 절대 안 쓰임.

### 7.2. 결과 검증

```bash
# 파일 크기
wc -l samples/_tmp_phase3/end_to_end_attention_mini_v2.md
wc -c samples/_tmp_phase3/end_to_end_attention_mini_v2.md

# Abstract 가 채워졌는지 확인 (핵심)
echo "=== Abstract (2.1) 내용 ==="
sed -n '/^### 2\.1 Abstract/,/^### 2\.2/p' samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -20

# Introduction (2.2) 정상 확인
echo ""
echo "=== Introduction (2.2) 앞부분 ==="
sed -n '/^### 2\.2 Introduction/,/^#### 2\.2\.1/p' samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -10

# 헤더 분포 (Level 7 이 없어야 함)
echo ""
echo "=== 헤더 분포 ==="
for i in 2 3 4 5 6 7 8; do
  hashes=$(printf '#%.0s' $(seq 1 $i))
  count=$(grep -c "^${hashes} " samples/_tmp_phase3/end_to_end_attention_mini_v2.md 2>/dev/null || echo 0)
  echo "  Level $i: $count"
done

# 빈 헤더 수
echo ""
echo "=== 빈 헤더 개수 ==="
.venv/bin/python << 'PYCHK'
from pathlib import Path
import re
content = Path('samples/_tmp_phase3/end_to_end_attention_mini_v2.md').read_text()
lines = content.split('\n')
empty_by_level = {}
filled_by_level = {}
for i, line in enumerate(lines):
    m = re.match(r'^(#{3,}) ', line)
    if m:
        level = len(m.group(1))
        next_content = []
        for j in range(i+1, min(i+10, len(lines))):
            if re.match(r'^#{3,} ', lines[j]):
                break
            next_content.append(lines[j])
        body = '\n'.join(next_content).strip()
        if body:
            filled_by_level[level] = filled_by_level.get(level, 0) + 1
        else:
            empty_by_level[level] = empty_by_level.get(level, 0) + 1
print("Level | Filled | Empty")
for lvl in sorted(set(list(empty_by_level) + list(filled_by_level))):
    f = filled_by_level.get(lvl, 0)
    e = empty_by_level.get(lvl, 0)
    print(f"  {lvl}   |  {f:4}  |  {e:4}")
total_empty = sum(empty_by_level.values())
print(f"총 빈 헤더: {total_empty}")
PYCHK

# 미해결 REF 확인
echo ""
echo "=== 미해결 REF ==="
grep -c "\[\[UNRESOLVED:" samples/_tmp_phase3/end_to_end_attention_mini_v2.md || echo "0"
grep -c "\[\[REF:" samples/_tmp_phase3/end_to_end_attention_mini_v2.md || echo "0"

# Part 2/3 비중
echo ""
echo "=== 섹션 비중 ==="
part2_start=$(grep -n "^## Part 2" samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -1 | cut -d: -f1)
part3_start=$(grep -n "^## Part 3" samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -1 | cut -d: -f1)
total_lines=$(wc -l < samples/_tmp_phase3/end_to_end_attention_mini_v2.md)
if [ -n "$part2_start" ] && [ -n "$part3_start" ]; then
    part2_lines=$((part3_start - part2_start))
    part3_lines=$((total_lines - part3_start))
    part1_lines=$((part2_start - 1))
    echo "  Part 1: $part1_lines lines"
    echo "  Part 2: $part2_lines lines"
    echo "  Part 3: $part3_lines lines"
fi
```

### 7.3. 통계 저장

```bash
cat > samples/_tmp_phase3/end_to_end_stats_v2.json << EOF
{
  "timestamp": "$(date -Iseconds)",
  "paper": "attention_mini",
  "version": "v2",
  "output_file": "samples/_tmp_phase3/end_to_end_attention_mini_v2.md",
  "output_lines": $(wc -l < samples/_tmp_phase3/end_to_end_attention_mini_v2.md),
  "output_bytes": $(wc -c < samples/_tmp_phase3/end_to_end_attention_mini_v2.md),
  "fixes_applied": [
    "concept_cache disabled for Phase 3 Part 2",
    "part2.max_depth reduced from 4 to 2",
    "expander prompt: depth discipline + no-skip principles",
    "expander: empty explanation raises ValueError",
    "assembler: header level capped at 6"
  ],
  "log_file": "samples/_tmp_phase3/end_to_end_log_v2.txt"
}
EOF
cat samples/_tmp_phase3/end_to_end_stats_v2.json
```

### 7.4. 커밋

```bash
git add samples/_tmp_phase3/end_to_end_attention_mini_v2.md \
        samples/_tmp_phase3/end_to_end_stats_v2.json \
        samples/_tmp_phase3/end_to_end_log_v2.txt
git commit -m "test(phase3): end-to-end v2 run after fixes

- applied 5 fixes: cache disable, max_depth=2, prompt depth discipline,
  empty explanation guard, header level cap
- cache_dir explicitly set to samples/_tmp_phase3/cache (no Phase 2 leak)
- output for user review
- no quality judgment made here"
git log --oneline -5
```

---

## 단계 8. 최종 보고서

### 8.1. PHASE3_FIX_REPORT.md 작성

프로젝트 루트에 `PHASE3_FIX_REPORT.md` 생성:

```markdown
# Phase 3 수정 작업 보고서

**작업 일시**: [date 결과]
**작업자**: Claude Code (자율 실행)
**시작 커밋**: [단계 0 시작 커밋 해시]

---

## 수정된 문제

### 문제 1: Abstract 섹션 빈 상태
**원인**: Phase 2 잔존 concept_cache 가 "Abstract" 를 중복 판정
**해결**: Expander 에 use_cache=False 옵션, Phase 3 파이프라인에서 적용
**결과**: Abstract 루트 노드 explanation 정상 생성 [v2 결과]

### 문제 2: 헤더 Level 7 까지 깊음
**원인**: max_depth=4 + assembler depth 계산
**해결**: max_depth=2, assembler 상한 6, expander 프롬프트 depth 규율
**결과**: v2 최대 헤더 Level [N]

---

## 수정된 파일

| 파일 | 변경 내용 | 커밋 |
|---|---|---|
| src/expander.py | use_cache 옵션, 프롬프트 원칙 3/7, 빈 explanation 가드 | [해시] |
| src/assembler.py | 헤더 Level 6 상한 | [해시] |
| src/main.py | run_phase3_pipeline 에서 use_cache=False | [해시] |
| config.yaml | part2.max_depth 4 → 2 | [해시] |

---

## 테스트 결과

### 단계 6: Abstract 단독 확장
- 상태: [done/duplicate/기타]
- explanation 길이: [N]
- children 수: [N]
- 최대 depth: [N]

### 단계 7: End-to-end 재실행
- 출력 파일: samples/_tmp_phase3/end_to_end_attention_mini_v2.md
- 파일 크기: [N 줄]
- Abstract 섹션 상태: [비어있음/채워짐]
- 최대 헤더 Level: [N]
- 빈 헤더 개수: [N]
- 미해결 REF: [N]
- Part 1 줄 수: [N]
- Part 2 줄 수: [N]
- Part 3 줄 수: [N]
- Claude 호출 수: [N]

---

## v1 vs v2 비교

| 지표 | v1 (이전) | v2 (현재) |
|---|---|---|
| 최대 헤더 Level | 7 | [N] |
| 빈 헤더 개수 | 76 | [N] |
| Abstract 상태 | 빈 | [N] |
| 전체 줄 수 | 3069 | [N] |
| Part 2 비중 | 18% | [N%] |

---

## 사용자 검토 요청

1. **가이드북 품질**:
   `cat samples/_tmp_phase3/end_to_end_attention_mini_v2.md`
   - Abstract 섹션에 해설이 있는가?
   - 헤더가 지나치게 깊지 않은가?
   - Part 2 의 하위 논점이 문단으로 자연스럽게 이어지는가?

2. **비교**:
   `diff samples/_tmp_phase3/end_to_end_attention_mini_v1.md \
        samples/_tmp_phase3/end_to_end_attention_mini_v2.md | head -100`
   - v1 대비 개선되었는가?

---

**보고서 끝. 사용자 판단 대기.**
```

위 템플릿의 `[N]` 을 실제 값으로 채워서 저장.

### 8.2. 커밋 + 최종 출력

```bash
git add PHASE3_FIX_REPORT.md
git commit -m "docs: add Phase 3 fix report

- documents 2 fixes applied
- v1 vs v2 comparison
- user review checklist"
git log --oneline -15

echo ""
echo "════════════════════════════════════════════════════════════"
echo "    Phase 3 수정 작업 완료"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "사용자 검토 필요:"
echo "  ★ samples/_tmp_phase3/end_to_end_attention_mini_v2.md"
echo "  - PHASE3_FIX_REPORT.md"
echo ""
echo "핵심 비교:"
echo "  v1: samples/_tmp_phase3/end_to_end_attention_mini_v1.md"
echo "  v2: samples/_tmp_phase3/end_to_end_attention_mini_v2.md"
echo ""
echo "════════════════════════════════════════════════════════════"
```

---

## 실패 시 롤백 방법

만약 수정 중 치명적 문제 발생:

```bash
# 시작 지점으로 되돌리기 (진단 전 상태)
git log --oneline | grep "docs: add Phase 3 Core work report" | head -1
# 위 명령의 커밋 해시로
# git reset --hard <해시>
```

또는 개별 커밋만 되돌리기:
```bash
git revert <커밋 해시>
```

---

**지시 끝. 단계 1~8 순차 실행. 중간 확인 없이 자율 진행. 단계 6 실패 시 단계 7 금지.**
