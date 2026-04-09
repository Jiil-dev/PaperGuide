# Phase 3 뼈대 준비 작업 — 자율 실행 지시

**작성자**: 웹 Claude (설계 담당)
**작성일**: 2026-04-08
**실행자**: Claude Code (자율 실행 모드)
**예상 소요**: 2~3시간
**사용자 개입**: 없음 (사용자가 자리 비운 동안 자율 진행)

---

## 이 문서의 역할

이 파일은 Claude Code가 **자율 실행 모드**에서 수행할 Phase 3 뼈대 준비 작업 전체를
담고 있다. 사용자가 약 3시간 자리를 비운 동안 이 지시에 따라 끝까지 진행하고,
완료되면 `PHASE3_WORK_REPORT.md` 를 작성한다.

**중요**: 이 문서는 "방향" 이 아니라 "실행 지시" 다. HANDOFF.md 의 절대 규칙을
준수하되, 이 파일의 구체적 지시는 그대로 따라라.

---

## 배경 맥락

이 작업은 Phase 2 → Phase 3 전환의 뼈대 준비다.

- **Phase 2**: "bottom-up 기초 지식 추출기" 로 동작했다. 논문 섹션을 받으면
  "이해에 필요한 선행 개념" 을 자식으로 분해하는 구조. 결과는 "가이드북의 90%가
  신경망 기초 강의" 가 되어 논문 분석이 부족했다.

- **Phase 3**: "top-down 논문 해설 + 완전판 기초" 로 재설계 중. 논문을 먼저
  분석하고, 기초 지식은 별도 Part로 위임한다.

네가 지금 할 일은 Phase 3에 필요한 **뼈대** 를 준비하는 것이다. 핵심 모듈
(expander, verifier, assembler) 의 철학 재작성은 **사용자가 돌아온 후** 대화로
진행한다. 너는 거기까지 건드리지 않는다.

---

## 절대 규칙 (위반 시 즉시 중단)

### 규칙 1. HANDOFF.md 의 절대 규칙 준수

작업 시작 시 `cat HANDOFF.md` 로 새 HANDOFF 를 읽고 §1.3 절대 규칙을 확인하라.
그 6가지 규칙은 이 작업 전체에 적용된다.

요약:
- Anthropic API 사용 금지 (`import anthropic`, `httpx`, `requests` 금지)
- Claude 호출은 JSON 모드 + 스키마 강제
- 출력은 Markdown 단일 파일
- 한 번에 한 모듈만 작업
- dry_run / cache 모드 기본
- 자의적 설계 변경 금지

### 규칙 2. 건드리지 않을 파일 목록

이 작업에서 **절대 수정하지 마라**. 사용자가 돌아온 후 대화로 진행할 파일들이다.

- `src/expander.py` — Phase 3의 top-down 재작성은 사용자와 함께
- `src/verifier.py` — 5축 확장은 사용자와 함께
- `src/assembler.py` — 3-Part 출력 확장은 사용자와 함께
- `src/main.py` — 파이프라인 재배선은 사용자와 함께

이 파일들은 `cat` 으로 읽는 것은 허용된다. **수정은 금지**.

### 규칙 3. 자의적 판단 금지

이 문서에 명시되지 않은 구조 변경 금지. 애매하면:
1. 해당 작업을 스킵
2. 보고서에 "결정 필요" 로 기록
3. 다음 단계 진행

추측으로 코드를 작성하지 마라. 특히 프롬프트 설계 시 HANDOFF §1.2 원칙
(top-down, 흐름 우선, 기초는 얕지 않게) 을 반영하되, 임의로 원칙을 추가하지 마라.

### 규칙 4. 에러 처리 정책

- **첫 시도 실패**: 에러 메시지 확인 → 명백한 수정 (import 누락, 오타, 파일 경로 등)
  → 재시도
- **두 번째 실패**: 해당 단계를 스킵하고 보고서에 기록. 나머지 단계 진행.
- **세 단계 연속 실패**: 전체 작업 중단. 보고서에 상태 기록.

절대 하지 말 것:
- 에러를 숨기거나 무시
- `try/except` 로 에러 삼키기
- 테스트를 생략하고 "성공" 선언

---

## 단계 0. 작업 시작 준비

### 0.1. 작업 디렉터리 확인

```bash
cd /home/engineer/j0061/paper-analyzer
pwd
git status
git branch --show-current
```

현재 브랜치와 상태 확인. 결과를 기록해두라.

### 0.2. git 안전장치

현재 커밋 해시를 기록. 나중에 되돌릴 수 있게:

```bash
git log --oneline -1 > /tmp/phase3_start_commit.txt
cat /tmp/phase3_start_commit.txt
```

### 0.3. HANDOFF.md 교체

사용자가 업로드한 새 HANDOFF.md (278줄) 를 프로젝트 루트로 복사.

먼저 사용자 업로드 경로 확인:

```bash
ls -la /mnt/user-data/uploads/ 2>&1
```

새 HANDOFF.md 를 찾으면 (파일명이 `HANDOFF.md`):

```bash
# 기존 HANDOFF 백업
cp HANDOFF.md HANDOFF_phase2_backup.md

# 새 HANDOFF 복사
cp /mnt/user-data/uploads/HANDOFF.md ./HANDOFF.md

# 교체 확인
wc -l HANDOFF.md  # 약 278줄이어야 함
head -20 HANDOFF.md  # 제목과 메타 확인
```

**만약 `/mnt/user-data/uploads/HANDOFF.md` 가 없으면**:
- 이 단계만 스킵
- 보고서에 "HANDOFF 교체 실패: 업로드 파일 없음" 기록
- 나머지 단계는 **기존 HANDOFF.md** 기준으로 진행

### 0.4. Phase 2 최종 상태 커밋

`git status` 에서 확인한 미커밋 변경사항을 먼저 정리한다. 현재 예상되는 상태:
- `src/assembler.py` (수정됨) — Phase 2 duplicate 링크 개선
- `src/expander.py` (수정됨) — Phase 2 depth 가드 수정
- `samples/` (untracked) — Phase 2 최종 샘플
- `docs/main_py_commit_20260408.md` (untracked)
- `.claude/` (untracked, Claude Code 로컬 설정 — .gitignore 추가)

```bash
# .gitignore 에 .claude/ 추가 (없으면)
if ! grep -q "^\.claude/" .gitignore; then
    echo "" >> .gitignore
    echo "# Claude Code local settings" >> .gitignore
    echo ".claude/" >> .gitignore
fi

# 스테이징
git add HANDOFF.md HANDOFF_phase2_backup.md
git add src/assembler.py src/expander.py
git add samples/
git add docs/main_py_commit_20260408.md
git add .gitignore

git status

git commit -m "chore: finalize Phase 2 and begin Phase 3 transition

- HANDOFF.md: replaced with Phase 3 redesign document (278 lines, top-down)
- HANDOFF_phase2_backup.md: preserve Phase 2 HANDOFF for history
- src/assembler.py: Phase 2 duplicate link rendering (previous pending change)
- src/expander.py: Phase 2 depth guard with force_leaf (previous pending change)
- samples/: Phase 2 final output (regression comparison reference)
- .gitignore: exclude .claude/ local settings"

git log --oneline -5
```

만약 위 파일 중 일부가 없으면 해당 파일만 빼고 `git add` 하라.

### 0.5. Phase 3 작업 디렉터리 생성

```bash
mkdir -p docs/phase3
mkdir -p samples/_tmp_phase3
```

---

## 단계 1. 데이터 구조 준비 (할당량 0)

### 1.1. `src/tree.py` 에 Phase 3 필드 추가

먼저 현재 파일 확인:

```bash
cat src/tree.py
```

`ConceptNode` dataclass 를 찾아서, 기존 필드 **뒤에** 세 필드 추가. 기존 필드는
절대 건드리지 마라.

추가할 필드:

```python
    # === Phase 3 신규 필드 ===
    part: int = 2              # 1, 2, 3 중 하나 (어느 Part에 속하는지)
    ref_id: str | None = None  # Part 3 항목용 고유 ID (topic_id)
    prerequisites: list[str] = field(default_factory=list)
    # 이 노드가 explanation에서 참조한 topic_id 리스트
```

`field` 가 이미 import 되어 있는지 확인. 없으면 `from dataclasses import dataclass, field` 로 수정.

편집 후 파일 다시 확인:

```bash
cat src/tree.py
```

**검증**:

```bash
.venv/bin/python -c "
from src.tree import ConceptNode
n = ConceptNode(concept='test', source_excerpt='x')
print(f'part={n.part}, ref_id={n.ref_id}, prereq={n.prerequisites}')
assert n.part == 2
assert n.ref_id is None
assert n.prerequisites == []
# 기존 필드도 정상 동작하는지
assert n.concept == 'test'
assert n.status == 'pending'
print('tree.py Phase 3 fields OK')
"
```

### 1.2. `src/data_types.py` 신규 작성

`src/data_types.py` 파일을 생성:

```python
# 단일 책임: Phase 3 파이프라인의 중간 단계에서 사용되는 데이터 구조 정의
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.tree import ConceptNode


@dataclass
class RawSection:
    """chunker의 출력. 논문 1차 섹션.

    Phase 2의 ConceptNode 트리 대신 단순 섹션 리스트로 축소된 chunker 결과.
    """
    title: str          # "Abstract", "Introduction", ...
    content: str        # 섹션 내용 전체 (Markdown)
    order: int          # 1부터 시작하는 순서 번호


@dataclass
class PaperAnalysis:
    """paper_analyzer의 출력. Part 1 생성 재료.

    논문 전체를 분석해서 추출된 큰 그림.
    """
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    core_thesis: str = ""              # 핵심 주장 한 문단
    problem_statement: str = ""        # 해결하려는 문제
    key_contributions: list[str] = field(default_factory=list)
    main_results: list[str] = field(default_factory=list)
    significance: str = ""             # 의의
    reading_guide: str = ""            # 가이드북 읽는 법 안내
    paper_structure: list[str] = field(default_factory=list)
    # 논문 섹션 이름 순서대로 (예: ['Abstract', 'Introduction', 'Background', ...])


@dataclass
class PrerequisiteTopic:
    """prerequisite_collector의 출력. Part 3에 포함될 주제 하나.

    여러 Part 2 섹션에서 등장한 기초 개념을 중복 제거해 모은 것.
    """
    topic_id: str              # "vector_dot_product" 같은 고유 식별자
    title: str                 # 사람이 읽는 제목
    first_mention_in: str      # 최초 언급된 Part 2 섹션 id
    all_mentions: list[str] = field(default_factory=list)
    # 이 주제가 언급된 모든 Part 2 섹션 id 리스트 (역링크용)


@dataclass
class PrerequisiteEntry:
    """part3_writer의 출력. Part 3의 실제 항목.

    topic에 대한 완성된 해설 + 역링크 정보.
    """
    topic: PrerequisiteTopic
    section_number: str                # "3.1", "3.2", ...
    subsections: list[ConceptNode] = field(default_factory=list)
    # 이 주제의 하위 항목들 (트리 구조)
    backlinks: list[str] = field(default_factory=list)
    # Part 2의 역링크 (all_mentions 와 동일하지만 편의상 복사)
```

파일 생성 후 확인:

```bash
cat src/data_types.py
```

**검증**:

```bash
.venv/bin/python -c "
from src.data_types import RawSection, PaperAnalysis, PrerequisiteTopic, PrerequisiteEntry
from src.tree import ConceptNode

# 각 클래스 인스턴스 생성 테스트
rs = RawSection(title='Abstract', content='test content', order=1)
pa = PaperAnalysis(title='Test Paper', authors=['A', 'B'], year=2024,
                   core_thesis='This is a thesis.', problem_statement='problem',
                   key_contributions=['c1', 'c2'])
pt = PrerequisiteTopic(topic_id='vector_dot_product', title='벡터와 내적',
                       first_mention_in='2.4.1', all_mentions=['2.4.1', '2.5.2'])
pe = PrerequisiteEntry(topic=pt, section_number='3.1',
                       subsections=[], backlinks=['2.4.1', '2.5.2'])

print(f'RawSection: {rs.title} / {rs.order}')
print(f'PaperAnalysis: {pa.title}')
print(f'PrerequisiteTopic: {pt.topic_id}')
print(f'PrerequisiteEntry: {pe.section_number}')
assert rs.order == 1
assert pa.title == 'Test Paper'
assert pt.topic_id == 'vector_dot_product'
assert pe.section_number == '3.1'
print('data_types.py OK')
"
```

### 1.3. 커밋 1

```bash
git add src/tree.py src/data_types.py
git status
git commit -m "feat(data): add Phase 3 data structures for 3-Part pipeline

- tree.py: add part, ref_id, prerequisites fields to ConceptNode
- data_types.py: new module with 4 dataclasses
  - RawSection: chunker output
  - PaperAnalysis: paper_analyzer output (Part 1 source)
  - PrerequisiteTopic: prerequisite_collector output
  - PrerequisiteEntry: part3_writer output"
git log --oneline -3
```

---

## 단계 2. chunker 축소 (할당량 0)

### 2.1. 현재 chunker 분석

```bash
cat src/chunker.py
```

기존 `split_into_sections()` 함수의 구조를 이해하라. 특히:
- `_EXCLUDED_SECTIONS` 상수
- 헤더 파싱 로직
- `_PROMOTE_TO_ROOT` 같은 상수가 있는지

### 2.2. 새 함수 추가

`split_into_sections()` 는 **삭제하지 말고 유지**. 대신 새 함수 `split_into_raw_sections()`
를 추가. 기존 로직을 참고해서 간단한 1차 섹션 분할만 수행하도록.

파일 상단에 import 추가 (없으면):

```python
from src.data_types import RawSection
```

그리고 새 함수 추가 (기존 `split_into_sections` 바로 아래 또는 위):

```python
def split_into_raw_sections(markdown: str) -> list[RawSection]:
    """Markdown 문자열을 1차 섹션 리스트로 분할한다.

    Phase 3의 chunker. 기존 split_into_sections() 와 달리 계층 트리를 만들지 않고
    `## 섹션명` 레벨로만 분할한다.

    Args:
        markdown: 논문 전체의 Markdown 문자열.

    Returns:
        RawSection 리스트. 각각 title, content, order.

    규칙:
        - `## 섹션명` (레벨 2) 헤더 기준으로 분할
        - `# 제목` (레벨 1) 은 논문 제목으로 간주하여 skip
        - `### 하위` 이하는 분할하지 않고 상위 섹션 content에 포함
        - _EXCLUDED_SECTIONS (references, acknowledgments 등) 는 제외
    """
    import re

    lines = markdown.split("\n")
    sections: list[RawSection] = []
    current_title: str | None = None
    current_content: list[str] = []
    order_counter = 0

    for line in lines:
        # 레벨 2 헤더 감지 (## 로 시작, ### 는 제외)
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            # 직전 섹션 저장
            if current_title is not None:
                title_lower = current_title.lower().strip()
                if title_lower not in _EXCLUDED_SECTIONS:
                    order_counter += 1
                    sections.append(RawSection(
                        title=current_title.strip(),
                        content="\n".join(current_content).strip(),
                        order=order_counter,
                    ))
            current_title = m.group(1)
            current_content = []
        else:
            if current_title is not None:
                current_content.append(line)

    # 마지막 섹션 저장
    if current_title is not None:
        title_lower = current_title.lower().strip()
        if title_lower not in _EXCLUDED_SECTIONS:
            order_counter += 1
            sections.append(RawSection(
                title=current_title.strip(),
                content="\n".join(current_content).strip(),
                order=order_counter,
            ))

    return sections
```

**주의**: `_EXCLUDED_SECTIONS` 상수가 기존 chunker.py 에 이미 있을 것이다. 없으면
추가하라:

```python
_EXCLUDED_SECTIONS = {
    "references",
    "acknowledgments",
    "acknowledgements",
    "bibliography",
    "appendix",
}
```

기존 chunker.py 의 `_EXCLUDED_SECTIONS` 와 충돌하지 않도록 확인하라. 이미 있으면
그대로 사용.

또한 기존 `split_into_sections()` 함수의 docstring 에 deprecated 표시 추가:

```python
def split_into_sections(markdown: str) -> list[ConceptNode]:
    """DEPRECATED (Phase 2 legacy).

    Phase 3에서는 split_into_raw_sections() 를 사용하라.
    이 함수는 Phase 2 main.py 와의 호환을 위해 유지되며, 새 코드에서는 쓰지 않는다.

    [기존 docstring 내용 유지]
    """
    # [기존 코드 그대로]
```

### 2.3. 검증

```bash
.venv/bin/python -c "
from pathlib import Path
from src.arxiv_parser import parse_arxiv
from src.chunker import split_into_raw_sections, split_into_sections
from src.data_types import RawSection

# Phase 3 함수 테스트
result = parse_arxiv(Path('data/papers/attention_mini'))
sections = split_into_raw_sections(result.markdown)

print(f'섹션 수: {len(sections)}')
for s in sections:
    print(f'  {s.order}. {s.title} ({len(s.content)} chars)')

assert len(sections) == 2, f'expected 2 sections, got {len(sections)}'
assert all(isinstance(s, RawSection) for s in sections)
assert sections[0].title.lower() == 'abstract'
assert sections[1].title.lower() == 'introduction'
assert sections[0].order == 1
assert sections[1].order == 2

# 기존 함수도 여전히 동작하는지 (호환성)
old_result = split_into_sections(result.markdown)
print(f'legacy split_into_sections: {len(old_result)} roots')
assert len(old_result) >= 1

print('chunker Phase 3 OK')
"
```

### 2.4. 커밋 2

```bash
git add src/chunker.py
git commit -m "feat(chunker): add split_into_raw_sections for Phase 3

- new function returns List[RawSection] instead of ConceptNode tree
- 1st-level section split only (## headers)
- hierarchical sub-section splitting now handled by Claude analysis in Phase 3
- legacy split_into_sections() kept with DEPRECATED marker for backward compat"
git log --oneline -5
```

---

## 단계 3. config 확장 (할당량 0)

### 3.1. 현재 config 파악

```bash
cat config.yaml
cat src/config.py
```

기존 구조를 이해하라. 특히 Pydantic 모델 클래스 이름 (예: `AppConfig`, `Settings`,
`Config` 등) 과 기존 필드.

### 3.2. `config.yaml` 확장

파일을 직접 편집해서 기존 필드는 유지하고 추가한다.

**기존 `claude:` 섹션의 `max_total_calls` 를 수정**:

현재 `max_total_calls: 500` (또는 비슷한 값) 을 찾아서 `max_total_calls: 1500` 으로 변경.
기존 주석이 있으면 유지.

**파일 끝에 신규 섹션 3개 추가**:

```yaml
# === Phase 3 신규 섹션 ===

part1:
  max_key_contributions: 4
  max_main_results: 5

part2:
  max_depth: 4                # 섹션 내 최대 세부 단계
  max_children_per_node: 5    # 한 노드의 최대 하위 논점 수
  use_placeholders: true      # 기초 지식 플레이스홀더 사용

part3:
  min_topics: 5               # 최소 주제 수
  max_topics: 15              # 최대 주제 수
  subsections_per_topic: 6    # 주제당 평균 하위 항목 수
  allow_claude_to_add: true   # Claude가 사전 풀에 없는 주제 추가 허용
  predefined_pool:
    - id: "neural_network_basics"
      title: "신경망의 기초"
    - id: "vector_dot_product"
      title: "벡터와 내적"
    - id: "matrix_multiplication"
      title: "행렬 곱셈"
    - id: "softmax"
      title: "softmax 함수"
    - id: "rnn_lstm_gru"
      title: "RNN, LSTM, GRU"
    - id: "cnn_basics"
      title: "CNN의 기초"
    - id: "encoder_decoder"
      title: "Encoder-Decoder 패러다임"
    - id: "attention_history"
      title: "Attention 메커니즘의 역사"
    - id: "optimization_basics"
      title: "최적화 기법"
    - id: "regularization"
      title: "Regularization 기법"
```

편집 후 확인:

```bash
cat config.yaml
```

### 3.3. `src/config.py` 에 Pydantic 모델 추가

기존 Pydantic 모델 파일에 새 클래스들을 추가한다. 기존 클래스 구조를 파악하고
비슷한 스타일로 작성하라.

추가할 클래스 (파일 상단의 다른 모델 정의 근처에):

```python
class Part1Config(BaseModel):
    max_key_contributions: int = 4
    max_main_results: int = 5


class Part2Config(BaseModel):
    max_depth: int = 4
    max_children_per_node: int = 5
    use_placeholders: bool = True


class PrerequisitePoolItem(BaseModel):
    id: str
    title: str


class Part3Config(BaseModel):
    min_topics: int = 5
    max_topics: int = 15
    subsections_per_topic: int = 6
    allow_claude_to_add: bool = True
    predefined_pool: list[PrerequisitePoolItem] = Field(default_factory=list)
```

그리고 기존 최상위 설정 클래스 (예: `AppConfig` 또는 `Settings`) 에 새 필드 추가:

```python
    part1: Part1Config = Field(default_factory=Part1Config)
    part2: Part2Config = Field(default_factory=Part2Config)
    part3: Part3Config = Field(default_factory=Part3Config)
```

만약 기존 클래스 이름을 파악하기 어려우면 `cat src/config.py` 결과를 바탕으로
판단하라. 기존 코드 스타일 (field 기본값 방식, import 방식 등) 을 그대로 따라라.

### 3.4. 검증

```bash
.venv/bin/python -c "
from pathlib import Path
from src.config import load_config

config = load_config(Path('config.yaml'))
print(f'max_total_calls: {config.claude.max_total_calls}')
print(f'part1: {config.part1}')
print(f'part2: {config.part2}')
print(f'part3 topics: {len(config.part3.predefined_pool)}')

# 첫 풀 항목 확인
first_topic = config.part3.predefined_pool[0]
print(f'first topic: {first_topic.id} / {first_topic.title}')

assert config.claude.max_total_calls == 1500, f'expected 1500, got {config.claude.max_total_calls}'
assert config.part1.max_key_contributions == 4
assert config.part2.max_depth == 4
assert config.part2.max_children_per_node == 5
assert config.part2.use_placeholders == True
assert config.part3.min_topics == 5
assert config.part3.max_topics == 15
assert len(config.part3.predefined_pool) == 10
assert config.part3.predefined_pool[0].id == 'neural_network_basics'
print('config Phase 3 OK')
"
```

### 3.5. 커밋 3

```bash
git add config.yaml src/config.py
git commit -m "feat(config): add Phase 3 configuration sections

- claude.max_total_calls: 500 -> 1500 (10~15x quota for 3-Part generation)
- part1: Part 1 generation limits (key contributions, main results)
- part2: top-down depth, children, placeholder toggle
- part3: topic count limits, predefined prerequisite pool (10 topics)
  includes: neural_network_basics, vector_dot_product, matrix_multiplication,
  softmax, rnn_lstm_gru, cnn_basics, encoder_decoder, attention_history,
  optimization_basics, regularization"
git log --oneline -5
```

---

## 단계 4. ref_resolver 신규 모듈 (할당량 0)

### 4.1. 설계 문서 작성

`docs/phase3/ref_resolver_design.md` 파일 생성:

```markdown
# ref_resolver.py 설계

## 단일 책임
Part 2 ConceptNode 트리의 explanation에 삽입된 `[[REF:topic_id]]` 플레이스홀더를
실제 Markdown 앵커 링크로 치환한다.

## 공개 API

```python
def resolve_refs(
    part2_nodes: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> list[ConceptNode]:
    """플레이스홀더를 앵커 링크로 치환한다. in-place 수정 + 반환.

    Args:
        part2_nodes: Part 2 트리의 루트 노드 리스트.
        part3_entries: Part 3 항목 리스트.

    Returns:
        치환 완료된 part2_nodes (편의상 반환).
    """
```

## 동작
1. part3_entries 에서 topic_id → (section_number, title) 맵 생성.
2. 모든 Part 2 노드를 DFS로 순회.
3. 각 노드 explanation 에서 정규식 `[[REF:([a-z_][a-z0-9_]*)]]` 매칭.
4. 매칭된 topic_id 가 맵에 있으면 `**[Part {section} {title}](#{anchor})**` 로 치환.
5. 맵에 없으면 `[[UNRESOLVED:topic_id]]` 로 남김 (경고 목적).

## 앵커 생성
앵커 규칙은 assembler.py 의 _make_anchor 와 동일:
- 소문자 변환
- 공백 → 하이픈
- 점 제거
- 영숫자, 한글, 공백, 하이픈만 유지

순환 import 방지를 위해 _make_anchor 함수를 로컬 복사한다.

## 의존성
- re (표준)
- src.tree.ConceptNode, iter_dfs
- src.data_types.PrerequisiteEntry

## 테스트
- 가짜 part2 노드 + 가짜 part3 엔트리로 치환 확인
- 미해결 topic_id 가 [[UNRESOLVED:...]] 로 남는지 확인
```

### 4.2. `src/ref_resolver.py` 구현

```python
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
```

**주의**: `iter_dfs` 가 `src/tree.py` 에 정의되어 있다고 가정. 없으면 `cat src/tree.py`
로 확인하고 실제 DFS 순회 함수 이름을 사용하라 (예: `dfs_iter`, `walk` 등).
없으면 로컬에 간단한 DFS 헬퍼를 추가해도 된다:

```python
def _walk(node: ConceptNode):
    yield node
    for child in node.children:
        yield from _walk(child)
```

### 4.3. 단위 테스트

```bash
.venv/bin/python -c "
from src.tree import ConceptNode
from src.data_types import PrerequisiteTopic, PrerequisiteEntry
from src.ref_resolver import resolve_refs

# 케이스 1: 정상 치환
node = ConceptNode(
    concept='test',
    source_excerpt='x',
    explanation='벡터 내적을 사용한다. 자세한 설명: [[REF:vector_dot_product]]',
)
topic = PrerequisiteTopic(
    topic_id='vector_dot_product',
    title='벡터와 내적',
    first_mention_in='2.4.1',
    all_mentions=['2.4.1'],
)
entry = PrerequisiteEntry(
    topic=topic,
    section_number='3.2',
    subsections=[],
    backlinks=['2.4.1'],
)

result = resolve_refs([node], [entry])
print('치환 결과:')
print(result[0].explanation)
assert '[[REF:vector_dot_product]]' not in result[0].explanation
assert '[Part 3.2 벡터와 내적]' in result[0].explanation
print()

# 케이스 2: 미해결
node2 = ConceptNode(
    concept='test2',
    source_excerpt='x',
    explanation='softmax 함수: [[REF:unknown_topic]]',
)
resolve_refs([node2], [entry])
print('미해결 케이스:')
print(node2.explanation)
assert '[[UNRESOLVED:unknown_topic]]' in node2.explanation
print()

# 케이스 3: 여러 플레이스홀더
node3 = ConceptNode(
    concept='test3',
    source_excerpt='x',
    explanation='벡터 [[REF:vector_dot_product]] 와 softmax [[REF:softmax]] 사용',
)
entry2 = PrerequisiteEntry(
    topic=PrerequisiteTopic(
        topic_id='softmax', title='softmax 함수',
        first_mention_in='2.5.1', all_mentions=['2.5.1']
    ),
    section_number='3.4',
    subsections=[],
    backlinks=['2.5.1'],
)
resolve_refs([node3], [entry, entry2])
print('다중 플레이스홀더:')
print(node3.explanation)
assert '[Part 3.2 벡터와 내적]' in node3.explanation
assert '[Part 3.4 softmax 함수]' in node3.explanation
print()

# 케이스 4: 중첩 트리
root = ConceptNode(concept='root', source_excerpt='x')
child = ConceptNode(concept='child', source_excerpt='x',
                     explanation='[[REF:vector_dot_product]]')
root.children = [child]
resolve_refs([root], [entry])
print('중첩 트리:')
print(root.children[0].explanation)
assert '[Part 3.2' in root.children[0].explanation

print('ref_resolver OK')
"
```

### 4.4. 커밋 4

```bash
git add src/ref_resolver.py docs/phase3/ref_resolver_design.md
git commit -m "feat(ref_resolver): add placeholder to anchor link resolution

- [[REF:topic_id]] -> **[Part 3.X title](#anchor)** substitution
- unresolved topics marked [[UNRESOLVED:topic_id]] for warnings
- 0 Claude calls, pure regex-based local logic
- handles nested tree traversal, multiple placeholders per node"
git log --oneline -5
```

---

## 단계 5. prerequisite_collector 신규 모듈 (할당량 0)

### 5.1. 설계 문서

`docs/phase3/prerequisite_collector_design.md`:

```markdown
# prerequisite_collector.py 설계

## 단일 책임
Part 2 트리 전체를 순회하며 각 노드의 prerequisites 필드에 등록된 topic_id를
수집하고, config의 predefined_pool과 병합한 뒤, 실제로 등장한 topic만 중복 제거해서
반환한다.

## 공개 API

```python
def collect_prerequisites(
    part2_nodes: list[ConceptNode],
    predefined_pool: list[PrerequisitePoolItem],
    allow_new: bool = True,
) -> list[PrerequisiteTopic]:
    """Part 2 트리에서 모든 기초 지식 주제를 수집하고 중복 제거한다.

    Args:
        part2_nodes: Part 2 루트 노드 리스트.
        predefined_pool: config.part3.predefined_pool.
        allow_new: 풀에 없는 topic_id도 허용할지.

    Returns:
        PrerequisiteTopic 리스트. 실제로 Part 2에서 등장한 주제만.
    """
```

## 동작
1. predefined_pool 을 topic_id → title 맵으로 변환.
2. Part 2 트리 DFS 순회하며 각 노드의 prerequisites 필드 수집.
3. 각 topic_id 마다:
   - 풀에 있으면: title을 풀에서 가져옴
   - 풀에 없고 allow_new=True: topic_id를 title로 변환 (언더스코어 → 공백, title case)
   - 풀에 없고 allow_new=False: 경고 후 스킵
4. 각 topic의 first_mention_in, all_mentions 계산 (노드 id 사용).
5. 실제로 등장한 topic 만 반환 (풀에 있어도 쓰이지 않으면 제외).
6. 정렬: 풀 순서 우선, 나머지는 topic_id 알파벳 순.

## 의존성
- warnings (표준)
- src.tree.ConceptNode
- src.data_types.PrerequisiteTopic
- src.config.PrerequisitePoolItem (또는 유사 이름)
```

### 5.2. `src/prerequisite_collector.py` 구현

```python
# 단일 책임: Part 2 트리를 순회하며 기초 지식 주제를 수집하고 중복 제거
from __future__ import annotations

import warnings

from src.data_types import PrerequisiteTopic
from src.tree import ConceptNode


def _walk(node: ConceptNode):
    """트리 DFS 순회 헬퍼."""
    yield node
    for child in node.children:
        yield from _walk(child)


def collect_prerequisites(
    part2_nodes: list[ConceptNode],
    predefined_pool: list,  # list[PrerequisitePoolItem] but avoid circular import
    allow_new: bool = True,
) -> list[PrerequisiteTopic]:
    """Part 2 트리에서 모든 기초 지식 주제를 수집하고 중복 제거한다.

    Args:
        part2_nodes: Part 2 루트 노드 리스트.
        predefined_pool: config.part3.predefined_pool (PrerequisitePoolItem 리스트).
        allow_new: 풀에 없는 topic_id도 허용할지.

    Returns:
        PrerequisiteTopic 리스트. 풀 순서 우선, 나머지는 알파벳 순.
    """
    # 풀을 topic_id → title 맵으로 변환 + 순서 기억
    pool_map: dict[str, str] = {}
    pool_order: dict[str, int] = {}
    for idx, item in enumerate(predefined_pool):
        pool_map[item.id] = item.title
        pool_order[item.id] = idx

    # 수집용 딕셔너리: topic_id → {title, first_mention, all_mentions}
    collected: dict[str, dict] = {}

    for root in part2_nodes:
        for node in _walk(root):
            for topic_id in node.prerequisites:
                if topic_id not in collected:
                    # 제목 결정
                    if topic_id in pool_map:
                        title = pool_map[topic_id]
                    elif allow_new:
                        # 언더스코어 → 공백 + title case
                        title = topic_id.replace("_", " ").title()
                    else:
                        warnings.warn(
                            f"Unknown prerequisite topic (skipped): {topic_id}"
                        )
                        continue

                    collected[topic_id] = {
                        "title": title,
                        "first_mention": node.id,
                        "all_mentions": [node.id],
                    }
                else:
                    collected[topic_id]["all_mentions"].append(node.id)

    # PrerequisiteTopic 리스트로 변환
    topics: list[PrerequisiteTopic] = []
    for topic_id, info in collected.items():
        topics.append(PrerequisiteTopic(
            topic_id=topic_id,
            title=info["title"],
            first_mention_in=info["first_mention"],
            all_mentions=info["all_mentions"],
        ))

    # 정렬: 풀 순서 우선, 나머지는 topic_id 알파벳 순
    def _sort_key(t: PrerequisiteTopic):
        if t.topic_id in pool_order:
            return (0, pool_order[t.topic_id])
        else:
            return (1, t.topic_id)

    topics.sort(key=_sort_key)
    return topics
```

### 5.3. 단위 테스트

```bash
.venv/bin/python -c "
from src.tree import ConceptNode
from src.data_types import PrerequisiteTopic
from src.config import PrerequisitePoolItem
from src.prerequisite_collector import collect_prerequisites

# 가짜 Part 2 트리
root1 = ConceptNode(concept='Abstract', source_excerpt='x', depth=0)
root1.prerequisites = ['vector_dot_product', 'softmax']

child1 = ConceptNode(concept='Sub', source_excerpt='x', depth=1, parent_id=root1.id)
child1.prerequisites = ['vector_dot_product', 'new_unknown_topic']
root1.children = [child1]

# 풀
pool = [
    PrerequisitePoolItem(id='vector_dot_product', title='벡터와 내적'),
    PrerequisitePoolItem(id='softmax', title='softmax'),
    PrerequisitePoolItem(id='rnn_lstm_gru', title='RNN'),  # 사용 안 됨
]

topics = collect_prerequisites([root1], pool, allow_new=True)

print(f'수집된 topic 수: {len(topics)}')
for t in topics:
    print(f'  {t.topic_id}: {t.title} (mentions: {len(t.all_mentions)})')

assert len(topics) == 3
topic_ids = [t.topic_id for t in topics]

# 풀 순서가 먼저 (vector_dot_product, softmax), 그 다음 알파벳 순 (new_unknown_topic)
assert topic_ids[0] == 'vector_dot_product'
assert topic_ids[1] == 'softmax'
assert topic_ids[2] == 'new_unknown_topic'

# rnn_lstm_gru 는 사용 안 되었으므로 제외
assert 'rnn_lstm_gru' not in topic_ids

# vector_dot_product 는 2번 등장
vdp = next(t for t in topics if t.topic_id == 'vector_dot_product')
assert len(vdp.all_mentions) == 2

# new_unknown_topic 은 자동 제목 생성 (언더스코어 → 공백, title case)
new_topic = next(t for t in topics if t.topic_id == 'new_unknown_topic')
assert new_topic.title == 'New Unknown Topic'

# allow_new=False 테스트
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    topics2 = collect_prerequisites([root1], pool, allow_new=False)
    # new_unknown_topic 은 제외되어야 함
    topic_ids2 = [t.topic_id for t in topics2]
    assert 'new_unknown_topic' not in topic_ids2
    assert len(topic_ids2) == 2
    # 경고 발생 확인
    assert any('new_unknown_topic' in str(msg.message) for msg in w)

print('prerequisite_collector OK')
"
```

### 5.4. 커밋 5

```bash
git add src/prerequisite_collector.py docs/phase3/prerequisite_collector_design.md
git commit -m "feat(prerequisite_collector): aggregate Part 3 topics from Part 2 tree

- collects topic_ids from all Part 2 nodes prerequisites fields
- merges with config.part3.predefined_pool
- dedups, handles unknown topics via allow_new flag
- returns only topics actually mentioned in Part 2
- sorted: pool order first, then alphabetical for new topics"
git log --oneline -5
```

---

## 단계 6. paper_analyzer 신규 모듈 (Claude 호출 1~3회)

### 6.1. 설계 문서

`docs/phase3/paper_analyzer_design.md`:

```markdown
# paper_analyzer.py 설계

## 단일 책임
논문 전체 Markdown을 받아 Part 1 생성용 PaperAnalysis 객체를 생성한다.

## 공개 API

```python
def analyze_paper(markdown: str, client: ClaudeClient) -> PaperAnalysis:
    """논문 Markdown 전체를 분석해 PaperAnalysis를 반환한다.

    Args:
        markdown: 논문 전체 Markdown 문자열.
        client: ClaudeClient 인스턴스.

    Returns:
        PaperAnalysis 객체.
    """
```

## Claude 호출
1회 (긴 논문은 cache/truncation은 claude_client 가 처리)

## 시스템 프롬프트 원칙 (HANDOFF §1.2 반영)
- 저자 관점 (top-down)
- 일반 교과서 설명 지양
- 학부 1학년 수준, 한국어
- 구체성 강조

## JSON 스키마
PaperAnalysis 의 모든 필드 + required 리스트.

## 에러 처리
- Claude 응답이 필수 필드 누락: ValueError raise
- title 이 빈 문자열: ValueError
```

### 6.2. `src/paper_analyzer.py` 구현

```python
# 단일 책임: 논문 전체를 분석하여 Part 1 생성 재료인 PaperAnalysis를 생성
from __future__ import annotations

from src.claude_client import ClaudeClient
from src.data_types import PaperAnalysis


_SYSTEM_PROMPT = """\
당신은 AI 분야 학술 논문 분석 전문가입니다.
주어진 논문 전체를 읽고 "큰 그림" 을 추출하십시오.

## 분석 목표
- 논문이 주장하는 핵심 명제
- 논문이 해결하는 문제와 기존 접근법의 한계
- 논문의 기여 (contribution)
- 실험 결과의 의미
- 이 논문의 의의 (왜 중요한가, 이후 영향)
- 이 논문의 구조 (섹션 이름 리스트)

## 분석 원칙

### 원칙 1 — 저자 관점
저자가 무엇을 주장하고 싶어 하는지를 파악하십시오.
일반적인 교과서 설명이 아닙니다. "저자가 ~한다", "저자는 ~를 주장한다" 와 같이
저자의 시각에서 서술하십시오.

### 원칙 2 — 구체적으로
"새로운 방법을 제안합니다" 같은 모호한 표현 금지.
"RNN 대신 self-attention을 사용한 Transformer를 제안합니다" 같이 구체적으로.
논문의 핵심 용어, 수치, 이름을 그대로 사용하십시오.

### 원칙 3 — 독자 수준
고등학교 수학 2, 물리 1, 기초 프로그래밍을 이수한 대학교 1학년이 이해할 수
있도록 설명하십시오. 전문 용어가 처음 등장하면 괄호 풀이를 병기하십시오.
예: "Transformer (순환 없이 attention만으로 작동하는 신경망 구조)"

### 원칙 4 — 한국어로
모든 설명은 한국어로 작성하십시오. 단, 논문 제목, 저자 이름, 전문 용어의
영어 원문은 병기합니다.

## 절대 금지
- 원문에 없는 사실 날조
- 저자와 무관한 일반 교과서 설명
- 모호한 표현 ("중요한 개선", "혁신적" 같은 수사만 나열)
- 한국어 이외의 언어로 작성 (영어 원문 병기는 허용)

반드시 지정된 JSON 스키마로만 응답하십시오.
자유 텍스트, 주석, 설명 없이 오직 JSON 만."""


_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "논문 제목 (영어 원문 그대로)",
        },
        "authors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "저자 이름 리스트",
        },
        "year": {
            "type": ["integer", "null"],
            "description": "발표 연도",
        },
        "core_thesis": {
            "type": "string",
            "description": "4~5 문장으로 논문의 핵심 주장 요약 (한국어)",
        },
        "problem_statement": {
            "type": "string",
            "description": "이 논문이 해결하려는 문제와 기존 접근법의 한계 (한국어)",
        },
        "key_contributions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2~5개의 핵심 기여, 각각 한 문장 (한국어)",
        },
        "main_results": {
            "type": "array",
            "items": {"type": "string"},
            "description": "주요 실험 결과를 리스트로 (한국어)",
        },
        "significance": {
            "type": "string",
            "description": "이 논문의 의의와 이후 영향 (한국어)",
        },
        "reading_guide": {
            "type": "string",
            "description": "독자에게 이 가이드북을 어떻게 읽으면 좋은지 안내 (한국어)",
        },
        "paper_structure": {
            "type": "array",
            "items": {"type": "string"},
            "description": "논문 섹션 이름을 순서대로 (예: ['Abstract', 'Introduction', 'Background', ...])",
        },
    },
    "required": [
        "title",
        "core_thesis",
        "problem_statement",
        "key_contributions",
        "main_results",
        "significance",
        "reading_guide",
        "paper_structure",
    ],
}


def analyze_paper(markdown: str, client: ClaudeClient) -> PaperAnalysis:
    """논문 Markdown 전체를 분석해 PaperAnalysis를 반환한다.

    Args:
        markdown: 논문 전체 Markdown 문자열.
        client: ClaudeClient 인스턴스.

    Returns:
        PaperAnalysis 객체.

    Raises:
        ValueError: Claude 응답이 잘못되었을 때.
    """
    user_prompt = f"다음 논문을 분석해주세요:\n\n{markdown}"

    result = client.call(
        user_prompt=user_prompt,
        system_prompt=_SYSTEM_PROMPT,
        json_schema=_SCHEMA,
    )

    title = result.get("title", "").strip()
    if not title:
        raise ValueError("paper_analyzer: title is empty in Claude response")

    core_thesis = result.get("core_thesis", "").strip()
    if not core_thesis:
        raise ValueError("paper_analyzer: core_thesis is empty in Claude response")

    return PaperAnalysis(
        title=title,
        authors=result.get("authors", []),
        year=result.get("year"),
        core_thesis=core_thesis,
        problem_statement=result.get("problem_statement", ""),
        key_contributions=result.get("key_contributions", []),
        main_results=result.get("main_results", []),
        significance=result.get("significance", ""),
        reading_guide=result.get("reading_guide", ""),
        paper_structure=result.get("paper_structure", []),
    )
```

### 6.3. dry_run 테스트

```bash
.venv/bin/python -c "
from pathlib import Path
from src.claude_client import ClaudeClient
from src.arxiv_parser import parse_arxiv
from src.paper_analyzer import analyze_paper

client = ClaudeClient(mode='dry_run')
result = parse_arxiv(Path('data/papers/attention_mini'))
print(f'markdown length: {len(result.markdown)}')

# dry_run 에서는 스키마 기본값 반환. title 이 빈 문자열이라 ValueError 예상.
try:
    analysis = analyze_paper(result.markdown, client)
    print('Unexpected success in dry_run')
except ValueError as e:
    print(f'dry_run ValueError (expected): {e}')
    print('dry_run OK')
"
```

dry_run 은 빈 값을 반환하므로 ValueError 가 터지는 것이 정상이다. 이것으로
**함수 구조와 import 는 정상** 임을 확인한다.

### 6.4. cache 모드 live 테스트 (실제 Claude 호출)

```bash
mkdir -p samples/_tmp_phase3/cache
.venv/bin/python << 'PYEOF'
import json
from pathlib import Path
from dataclasses import asdict
from src.claude_client import ClaudeClient
from src.arxiv_parser import parse_arxiv
from src.paper_analyzer import analyze_paper

# cache mode 로 호출. 첫 실행이면 실제 Claude 호출, 이후는 캐시 재사용.
client = ClaudeClient(
    mode='cache',
    cache_dir=Path('samples/_tmp_phase3/cache'),
    max_total_calls=10,
    sleep_between_calls=2,
)
result = parse_arxiv(Path('data/papers/attention_mini'))
print(f'논문 로드: {len(result.markdown)} chars')

print('paper_analyzer 호출 중...')
try:
    analysis = analyze_paper(result.markdown, client)
    
    print()
    print('=' * 60)
    print(f'제목: {analysis.title}')
    print(f'저자: {analysis.authors}')
    print(f'연도: {analysis.year}')
    print()
    print(f'핵심 주장:')
    print(analysis.core_thesis)
    print()
    print(f'해결 문제:')
    print(analysis.problem_statement)
    print()
    print(f'핵심 기여 {len(analysis.key_contributions)}개:')
    for i, c in enumerate(analysis.key_contributions, 1):
        print(f'  {i}. {c}')
    print()
    print(f'주요 결과 {len(analysis.main_results)}개:')
    for i, r in enumerate(analysis.main_results, 1):
        print(f'  {i}. {r}')
    print()
    print(f'의의:')
    print(analysis.significance)
    print()
    print(f'논문 구조: {analysis.paper_structure}')
    print('=' * 60)
    
    stats = client.get_stats()
    print(f'\nstats: {stats}')
    
    # JSON 파일로 저장 (사용자 검토용)
    output_path = Path('samples/_tmp_phase3/paper_analysis_test.json')
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(asdict(analysis), f, ensure_ascii=False, indent=2)
    print(f'\n결과 저장: {output_path}')
    
    # Sanity checks
    assert analysis.title, 'title is empty'
    assert analysis.core_thesis, 'core_thesis is empty'
    assert len(analysis.key_contributions) >= 1, 'no contributions'
    
    # attention_mini 이므로 제목에 Attention 이 있을 것
    title_lower = analysis.title.lower()
    assert 'attention' in title_lower or '어텐션' in title_lower, \
        f'title 에 attention 이 없음: {analysis.title}'
    
    print('\npaper_analyzer live 테스트 OK')
    
except Exception as e:
    print(f'\n에러 발생: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    print('\npaper_analyzer live 테스트 실패')
PYEOF
```

결과가 이상하거나 에러가 나면 보고서에 기록하고 다음 단계로 진행.

### 6.5. 커밋 6

```bash
git add src/paper_analyzer.py docs/phase3/paper_analyzer_design.md
# 생성된 JSON 도 포함 (사용자가 돌아와서 검토)
if [ -f samples/_tmp_phase3/paper_analysis_test.json ]; then
    git add samples/_tmp_phase3/paper_analysis_test.json
fi

git commit -m "feat(paper_analyzer): add Part 1 big-picture extractor

- single Claude call analyzes entire paper markdown
- outputs PaperAnalysis with title, thesis, contributions, results, significance
- Korean output, undergraduate level, author-centric perspective
- system prompt enforces HANDOFF philosophy: top-down, specific, no jargon
- verified live with attention_mini (cache mode)
- result saved to samples/_tmp_phase3/paper_analysis_test.json for user review"
git log --oneline -8
```

---

## 단계 7. 최종 상태 확인 및 보고서 작성

### 7.1. 전체 상태 확인

```bash
# 최종 git log
git log --oneline -15

# 새로 생긴 파일들
echo "=== 새 Python 파일 ==="
ls -la src/data_types.py src/ref_resolver.py src/prerequisite_collector.py src/paper_analyzer.py 2>&1

echo ""
echo "=== Phase 3 설계 문서 ==="
ls -la docs/phase3/ 2>&1

echo ""
echo "=== 임시 테스트 결과 ==="
ls -la samples/_tmp_phase3/ 2>&1

echo ""
echo "=== HANDOFF 상태 ==="
wc -l HANDOFF.md HANDOFF_phase2_backup.md 2>&1
```

### 7.2. `PHASE3_WORK_REPORT.md` 작성

프로젝트 루트에 보고서 파일 작성. 아래 템플릿을 채워라:

```markdown
# Phase 3 뼈대 준비 작업 보고서

**작업 일시**: [date 명령으로 현재 시각]
**작업자**: Claude Code (자율 실행 모드)
**시작 커밋**: [/tmp/phase3_start_commit.txt 내용]

---

## 작업 결과 요약

| 단계 | 내용 | 결과 | 커밋 |
|---|---|---|---|
| 0 | 준비 (HANDOFF 교체, git 백업) | [성공/실패] | [해시 또는 N/A] |
| 1 | 데이터 구조 (tree.py, data_types.py) | [성공/실패] | [해시] |
| 2 | chunker 축소 | [성공/실패] | [해시] |
| 3 | config 확장 | [성공/실패] | [해시] |
| 4 | ref_resolver 신규 | [성공/실패] | [해시] |
| 5 | prerequisite_collector 신규 | [성공/실패] | [해시] |
| 6 | paper_analyzer 신규 + live 테스트 | [성공/실패] | [해시] |

총 커밋 수: [N]
총 Claude 호출 수: [N] (paper_analyzer 테스트)

---

## 각 단계 상세

### 단계 0. 준비
- HANDOFF.md 교체: [성공 / 실패 — 이유]
- Phase 2 최종 커밋: [해시]
- 시작 커밋: [해시]

### 단계 1. 데이터 구조
- tree.py: ConceptNode 에 3개 필드 추가 (part, ref_id, prerequisites)
- data_types.py: 4개 dataclass 신규 (RawSection, PaperAnalysis, PrerequisiteTopic, PrerequisiteEntry)
- 검증: [pass / fail]
- 커밋: [해시]

### 단계 2. chunker 축소
- split_into_raw_sections() 신규 함수
- 기존 split_into_sections() 은 DEPRECATED 마크로 유지
- attention_mini 테스트: [N개 섹션 반환]
- 커밋: [해시]

### 단계 3. config 확장
- max_total_calls: 500 → 1500
- part1, part2, part3 섹션 추가
- predefined_pool: 10개 topic
- 커밋: [해시]

### 단계 4. ref_resolver
- 플레이스홀더 → 앵커 링크 치환
- 단위 테스트: [4개 케이스 pass/fail]
- 커밋: [해시]

### 단계 5. prerequisite_collector
- Part 2 트리 순회 + 중복 제거
- allow_new=True/False 양쪽 테스트 pass/fail
- 커밋: [해시]

### 단계 6. paper_analyzer (★ Claude 호출 포함)
- 시스템 프롬프트: HANDOFF §1.2 원칙 반영
- JSON 스키마: PaperAnalysis 필드 대응
- dry_run: ValueError (expected) [pass/fail]
- **live 테스트 (cache mode, attention_mini)**:
  - Claude 호출 수: [N]
  - 생성된 JSON 파일: samples/_tmp_phase3/paper_analysis_test.json
  - 제목 추출: [yes/no]
  - 핵심 주장 추출: [yes/no]
  - 기여 리스트 추출: [N개]
  - 전체 성공: [yes/no]
- 커밋: [해시]

---

## 현재 git 상태

### 최근 커밋 (10개)
[git log --oneline -10 출력]

### 새로 생긴 파일
[find src/ -name "*.py" -newer /tmp/phase3_start_commit.txt 또는 git diff --name-status]

---

## 실패한 작업 / 결정 필요

[실패한 단계가 있으면 상세 내용]
[또는 "없음"]

---

## 사용자에게 확인 요청

**필수 확인 사항**:

1. **paper_analyzer 결과 품질**:
   `samples/_tmp_phase3/paper_analysis_test.json` 을 직접 읽어보시고 품질 판단.
   특히 다음을 확인:
   - 제목이 정확한가? ("Attention Is All You Need (Mini)")
   - 핵심 주장(core_thesis)이 논문을 정확히 요약하는가?
   - 기여(key_contributions)가 구체적인가? 모호한 표현은 없는가?
   - 한국어 품질은 자연스러운가?
   - 전문 용어 괄호 풀이가 적절한가?

2. **Phase 2 의도적 미수정 파일**:
   다음 파일들은 Phase 3에서 **사용자와 함께** 재작성/확장 예정이므로 이 작업에서
   건드리지 않음:
   - src/expander.py (top-down 재작성)
   - src/verifier.py (5축 확장)
   - src/assembler.py (3-Part 출력)
   - src/main.py (파이프라인 재배선)

3. **다음 작업 방향**:
   위 파일들을 사용자 확인/합의 하에 순차적으로 재작성해야 함.
   권장 순서: expander (핵심) → verifier → assembler → main.

---

## 전체 Claude 호출 내역

- 단계 0~5: 0 calls (로컬 로직만)
- 단계 6 paper_analyzer dry_run: 0 calls
- 단계 6 paper_analyzer live: [N] calls

**총계**: [N] calls

---

**보고서 끝. 사용자 검토 대기.**
```

이 템플릿의 `[...]` 부분을 실제 값으로 채워서 저장하라.

```bash
# 현재 시각
date > /tmp/phase3_end_time.txt
cat /tmp/phase3_end_time.txt

# 보고서 작성 (위 템플릿을 실제 값으로 채운 뒤)
# cat > PHASE3_WORK_REPORT.md << 'EOF'
# [채워진 보고서 내용]
# EOF

# 확인
wc -l PHASE3_WORK_REPORT.md
head -30 PHASE3_WORK_REPORT.md
```

### 7.3. 보고서 커밋

```bash
git add PHASE3_WORK_REPORT.md
git commit -m "docs: add Phase 3 skeleton preparation report

- documents all 6 steps of Phase 3 bootstrap work
- lists new files, modules, and Claude calls made
- identifies files intentionally not modified (expander, verifier, assembler, main)
- provides user review checklist for paper_analyzer live test output"
git log --oneline -10
```

---

## 최종 출력

모든 작업이 끝나면 마지막으로 요약 출력:

```bash
echo ""
echo "════════════════════════════════════════════════════════════"
echo "    Phase 3 뼈대 준비 작업 완료"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "보고서: PHASE3_WORK_REPORT.md"
echo ""
echo "주요 결과물:"
echo "  - HANDOFF.md (Phase 3 재설계 문서)"
echo "  - src/data_types.py (신규)"
echo "  - src/chunker.py (split_into_raw_sections 추가)"
echo "  - src/ref_resolver.py (신규)"
echo "  - src/prerequisite_collector.py (신규)"
echo "  - src/paper_analyzer.py (신규 + live 테스트 완료)"
echo ""
echo "사용자 검토 필요:"
echo "  - cat PHASE3_WORK_REPORT.md"
echo "  - cat samples/_tmp_phase3/paper_analysis_test.json"
echo ""
echo "다음 단계 (사용자 돌아온 후):"
echo "  - expander.py top-down 재작성"
echo "  - verifier.py 5축 확장"
echo "  - assembler.py 3-Part 출력"
echo "  - main.py 파이프라인 재배선"
echo ""
echo "════════════════════════════════════════════════════════════"
```

---

**지시 끝. 끝까지 자율 진행. 중간 보고 없음. 완료 후 PHASE3_WORK_REPORT.md 확인.**
