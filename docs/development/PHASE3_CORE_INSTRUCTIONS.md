# Phase 3 Core 작업 — 자율 실행 지시 (옵션 C 풀 버전)

**작성자**: 웹 Claude (설계 담당)
**작성일**: 2026-04-08
**실행자**: Claude Code (자율 실행 모드)
**전제**: 단계 1~7 (뼈대 준비) 이미 완료됨. HEAD = `58889d9 docs: add Phase 3 skeleton preparation report`
**예상 소요**: 3~4시간
**사용자 개입**: 없음

---

## 이 문서의 역할

단계 8 부터 단계 14 까지 Phase 3 의 핵심 모듈들을 자율 구현한다. 단계 1~7 에서
준비된 뼈대(data_types, chunker, config, ref_resolver, prerequisite_collector,
paper_analyzer) 위에 expander, verifier, part3_writer, assembler, main 을 올린다.

**paper_analyzer 의 검증된 스타일을 재사용한다**. `samples/_tmp_phase3/paper_analysis_test.json`
의 core_thesis, key_contributions 가 top-down + 저자 관점 + 구체적 + 한국어로 나온 것이
확인됐다. 같은 시스템 프롬프트 원칙을 expander, part3_writer 에 적용한다.

---

## 절대 규칙 (위반 시 즉시 중단)

### 규칙 1. HANDOFF.md §1.3 준수
- Anthropic API 사용 금지 (`import anthropic`, `httpx`, `requests`)
- Claude 호출은 JSON 모드 + 스키마 강제
- 출력은 Markdown 단일 파일
- dry_run / cache 모드 기본
- 프롬프트는 HANDOFF §1.2 원칙 반영: top-down, 흐름 우선, 기초는 얕지 않게

### 규칙 2. 작업 범위 엄격 제한

**맡긴 작업**:
- verifier.py 5축 확장 (2개 축 추가)
- expander.py 내부 재작성 (top-down)
- part3_writer.py 신규
- assembler.py 3-Part 출력 확장
- main.py 파이프라인 재배선
- attention_mini end-to-end 테스트

**절대 금지**:
- ❌ **Attention 전체 논문 (`data/papers/attention/`) 실행 금지**
- ❌ 기타 큰 논문 실행 금지
- ❌ end-to-end 테스트 외 추가 실험 금지
- ❌ 프롬프트 튜닝 반복 금지 (한 번 돌리고 결과만 저장)
- ❌ config.yaml 의 max_total_calls 를 코드에서 임의 변경 금지

### 규칙 3. 커밋 메시지 단어 제한
다음 단어를 커밋 메시지에 **사용하지 말 것**:
- "verified" → "tested" 사용
- "success" → "completed" 사용
- "perfect" → (사용 금지)
- "excellent" → (사용 금지)

이유: "성공 선언" 은 사용자 판단 영역이다. Claude Code 는 "구현/테스트 완료" 만 선언.

### 규칙 4. 에러 처리 정책
- 첫 시도 실패: 명백한 수정 → 재시도
- 두 번째 실패: 해당 단계 스킵, 보고서 기록, 다음 진행
- **세 단계 연속 실패 시 전체 작업 중단**

### 규칙 5. 중간 산출물 의무 저장

각 live 테스트 결과를 다음 경로에 파일로 저장:

- `samples/_tmp_phase3/verifier_5axis_test.json` — verifier 5축 출력
- `samples/_tmp_phase3/expander_abstract_output.json` — expander top-down 트리 결과
- `samples/_tmp_phase3/part3_topic_output.json` — part3_writer 개별 주제 출력
- `samples/_tmp_phase3/assembler_3part_output.md` — assembler 3-Part 렌더링
- `samples/_tmp_phase3/end_to_end_attention_mini.md` — 최종 end-to-end 결과
- `samples/_tmp_phase3/end_to_end_stats.json` — 통계 (call 수, 시간 등)

이 파일들은 사용자가 돌아와서 **직접 읽고 품질 판단**할 재료다.

### 규칙 6. 건드리지 않을 파일
- HANDOFF.md (읽기만)
- src/tree.py (Phase 3 필드 이미 추가됨)
- src/data_types.py, src/chunker.py, src/config.py, src/paper_analyzer.py,
  src/ref_resolver.py, src/prerequisite_collector.py (이미 구현)
- src/claude_client.py, src/pdf_parser.py, src/arxiv_parser.py,
  src/checkpoint.py, src/concept_cache.py (Phase 2 그대로 재사용)
- config.yaml (이미 확장 완료)

---

## 단계 8. verifier 5축 확장

### 8.1. 현재 verifier 분석

```bash
cat src/verifier.py
```

기존 구조 파악. 특히:
- 기존 4축이 무엇인지 (보통: faithfulness, level_appropriate, completeness, clarity 같은 것)
- 시스템 프롬프트 형식
- JSON 스키마
- 공개 API (함수 이름, 인자, 반환형)

### 8.2. 설계 문서

`docs/phase3/verifier_design.md`:

```markdown
# verifier.py Phase 3 확장 설계

## 기존 (Phase 2)
4개 축으로 검증:
- faithfulness (원문 충실)
- level_appropriate (학부 1학년 수준)
- completeness (빠진 내용 없음)
- clarity (명확함)

## Phase 3 추가 (2개 축)

### 5. paper_centric (논문 중심성)
해설이 논문의 저자 관점에서 쓰였는가? 일반 교과서 설명으로 빠지지 않았는가?

판단 기준:
- "저자는 ~를 주장한다", "저자는 ~를 선택했다" 같은 저자 관점 서술
- 논문의 실제 용어, 수치, 예시를 그대로 사용
- "일반적으로 ~는 ..." 같은 교과서 설명이 주가 되지 않음

### 6. flow (흐름 유지)
기초 지식 때문에 본문 흐름이 끊기지 않는가?

판단 기준:
- 기초 개념이 본문에 짧은 괄호 병기 또는 [[REF:topic_id]] 플레이스홀더로만 등장
- 본문에 기초 개념 설명이 여러 문단에 걸쳐 박혀있지 않음
- Part 3로 위임된 것이 많음

## 공개 API
기존 API 유지. 내부 프롬프트와 스키마만 확장.
```

### 8.3. verifier.py 수정

`cat src/verifier.py` 로 현재 구조 파악 후, 기존 시스템 프롬프트에 5, 6번 축 추가.
기존 JSON 스키마에도 5, 6번 필드 추가. 공개 API 는 변경하지 말 것.

핵심 추가 프롬프트 조각 (기존 프롬프트의 축 설명 부분에 추가):

```
### 5. paper_centric (논문 중심성)
해설이 논문 저자의 관점에서 쓰였는가를 평가한다.

판단 기준:
- 좋음: "저자는 RNN의 순차 계산 문제를 지적한다", "저자는 Multi-Head Attention을 선택했다"
- 나쁨: "RNN은 일반적으로 이런 구조다", "Attention mechanism은 보통 이렇게 동작한다"

해설이 "이 논문" 이 아니라 "이 분야 일반" 을 설명하고 있다면 이 축에서 낮은 점수.

### 6. flow (흐름 유지)
본문 흐름이 기초 지식으로 끊기지 않았는가를 평가한다.

판단 기준:
- 좋음: 기초 개념이 한 줄 괄호 병기나 [[REF:...]] 플레이스홀더로만 등장
- 나쁨: "벡터 내적이란 ~이고, 이것의 기하학적 의미는 ~이며..." 식으로 여러 문단이 본문에 박힘

본문에 기초 지식이 여러 문단에 걸쳐 설명되어 있다면 이 축에서 낮은 점수.
```

기존 JSON 스키마의 축 필드에 추가:

```python
"paper_centric": {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
},
"flow": {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
},
```

### 8.4. dry_run 테스트

```bash
.venv/bin/python -c "
from src.claude_client import ClaudeClient
from src.verifier import verify_explanation  # 또는 실제 함수 이름
from src.tree import ConceptNode

client = ClaudeClient(mode='dry_run')

# 가짜 노드
node = ConceptNode(
    concept='Self-Attention',
    source_excerpt='The Transformer uses self-attention...',
    explanation='저자는 RNN 대신 self-attention 을 사용한다.',
)

# dry_run은 스키마 기본값 반환하거나 ValueError
try:
    result = verify_explanation(node, client)  # 실제 함수 이름 사용
    print(f'dry_run result: {result}')
except Exception as e:
    print(f'dry_run exception (OK): {type(e).__name__}: {e}')

print('verifier dry_run OK')
"
```

### 8.5. live 테스트 (작게)

```bash
.venv/bin/python << 'PYEOF'
import json
from pathlib import Path
from dataclasses import asdict
from src.claude_client import ClaudeClient
from src.verifier import verify_explanation  # 실제 함수 이름
from src.tree import ConceptNode

client = ClaudeClient(
    mode='cache',
    cache_dir=Path('samples/_tmp_phase3/cache'),
    max_total_calls=3,
    sleep_between_calls=2,
)

# 테스트 케이스 1: 좋은 해설 (저자 관점)
good_node = ConceptNode(
    concept='Self-Attention',
    source_excerpt='The Transformer is the first transduction model relying entirely on self-attention.',
    explanation='저자들은 Transformer가 self-attention 만으로 구성된 최초의 시퀀스 변환 모델이라고 주장한다. RNN을 완전히 배제한 이 설계 선택은 병렬 처리를 가능케 하려는 저자들의 의도에서 나온 것이다.',
)

result_good = verify_explanation(good_node, client)
print('=== 좋은 해설 검증 ===')
print(json.dumps(result_good if isinstance(result_good, dict) else asdict(result_good),
                 ensure_ascii=False, indent=2))

# 결과 저장
output = {
    'good_case': result_good if isinstance(result_good, dict) else asdict(result_good),
}

output_path = Path('samples/_tmp_phase3/verifier_5axis_test.json')
with output_path.open('w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)
print(f'결과 저장: {output_path}')

stats = client.get_stats()
print(f'stats: {stats}')
print('verifier 5축 테스트 완료')
PYEOF
```

### 8.6. 커밋

```bash
git add src/verifier.py docs/phase3/verifier_design.md samples/_tmp_phase3/verifier_5axis_test.json
git commit -m "feat(verifier): extend to 5-axis verification for Phase 3

- added paper_centric axis: author perspective vs textbook explanation
- added flow axis: prerequisite placement vs inline textbook content
- existing 4 axes unchanged
- public API unchanged
- tested with good-case sample on attention_mini context"
git log --oneline -3
```

---

## 단계 9. expander 내부 재작성 (★ 핵심)

이게 Phase 3 의 가장 중요한 단계다. Phase 2 의 bottom-up 로직을 top-down 으로
완전히 뒤집는다. 파일명은 유지.

### 9.1. 현재 expander 분석

```bash
cat src/expander.py
```

특히 다음을 파악:
- 공개 API (함수 이름, 인자, 반환형)
- 기존 시스템 프롬프트 위치
- 기존 JSON 스키마
- DFS 재귀 구조
- depth 관련 가드

### 9.2. 설계 문서

`docs/phase3/expander_design.md`:

```markdown
# expander.py Phase 3 재작성 설계

## Phase 2 와의 차이

### Phase 2 (bottom-up)
섹션을 받으면 "이해에 필요한 선행 개념" 을 자식으로 생성.
예: Abstract → 자식 [신경망 기초, RNN 이해, Attention 개념]

### Phase 3 (top-down)
섹션을 받으면 "논문 저자가 이 섹션에서 다루는 하위 논점" 을 자식으로 생성.
예: Abstract → 자식 [제안하는 구조 요약, 기존 한계, 실험 결과 요약]

## 공개 API
기존 API 유지. 내부 프롬프트 전면 재작성.

## 시스템 프롬프트 원칙 (HANDOFF §1.2 반영)

### 원칙 1 — top-down: 저자 관점
"저자는 여기서 ~를 말한다" 형식. 일반 교과서 설명 금지.
paper_analyzer.py 의 시스템 프롬프트와 같은 스타일.

### 원칙 2 — 흐름 우선: 기초 지식 위임
기초 개념은 본문에 한 줄 괄호 병기 또는 [[REF:topic_id]] 플레이스홀더로만 등장.
여러 문단에 걸친 기초 지식 설명 금지.

### 원칙 3 — 하위 논점 분해
각 섹션을 "저자가 이 섹션에서 주장하는 하위 논점들" 로 분해.
논점마다 자식 노드 생성.

### 원칙 4 — 실험 섹션은 자세히
Training, Results 같은 실험 섹션은 하이퍼파라미터 선택 이유, 실험 결과 해석까지 자세히.

## JSON 스키마

각 노드는 다음 필드를 생성:
- concept: 이 노드의 주제 (짧은 명사구)
- explanation: 한국어 해설 (top-down, 저자 관점)
- children: 하위 논점 리스트 (재귀)
- prerequisites: 이 해설에 등장하는 기초 개념 topic_id 리스트

## 하위 논점 생성 기준
- 섹션 내용을 2~5개의 하위 논점으로 분해
- 각 논점은 저자의 한 주장에 대응
- depth 가 깊어질수록 더 구체적으로
- max_depth (config.part2.max_depth=4) 도달하면 자식 생성 중단

## 플레이스홀더 규칙
기초 개념이 등장하면 [[REF:topic_id]] 를 explanation 에 삽입 + prerequisites 필드에 topic_id 추가.
topic_id 는 소문자 언더스코어 (예: vector_dot_product).
```

### 9.3. expander.py 재작성

**중요**: 기존 DFS 재귀 구조, 공개 API, depth 가드는 유지. 시스템 프롬프트와
JSON 스키마만 재작성.

새 시스템 프롬프트 (paper_analyzer 스타일 참고):

```python
_SYSTEM_PROMPT = """\
당신은 AI 분야 학술 논문을 학부 1학년에게 해설하는 전문가입니다.

주어진 논문 섹션을 "저자의 관점에서" 해설하십시오.
독자는 고등학교 수학 2, 물리 1, 기초 프로그래밍을 이수한 대학교 1학년입니다.

## 해설 원칙

### 원칙 1 — top-down: 저자 중심
"저자는 ~라고 주장한다", "저자는 ~를 선택했다", "저자가 이 섹션에서 하는 말은 ~이다"
와 같이 저자의 시각에서 서술하십시오.

일반적인 교과서 설명 금지. 예시:
- 나쁨: "RNN은 일반적으로 순차적으로 입력을 처리한다."
- 좋음: "저자는 RNN이 순차적이라는 점이 병렬 처리를 막는다고 지적한다."

### 원칙 2 — 흐름 우선: 기초 지식 위임
기초 개념 (선형대수, 확률론, 머신러닝 기초 등) 이 등장하면:

1. 본문에는 한 줄 괄호 병기만: "내적(두 벡터의 성분별 곱의 합)"
2. 플레이스홀더 삽입: [[REF:topic_id]]
3. 깊은 설명은 절대 금지 — Part 3 에서 따로 다룬다

여러 문단에 걸쳐 기초 개념을 설명하지 마십시오. 한 줄이면 충분합니다.

topic_id 규칙:
- 소문자 + 언더스코어
- 예: vector_dot_product, softmax, rnn_lstm_gru, matrix_multiplication
- 사전 정의된 풀: neural_network_basics, vector_dot_product, matrix_multiplication,
  softmax, rnn_lstm_gru, cnn_basics, encoder_decoder, attention_history,
  optimization_basics, regularization
- 풀에 없는 주제도 자유롭게 만들 수 있음 (예: batch_normalization)

### 원칙 3 — 하위 논점 분해
각 섹션을 2~5 개의 "저자가 하는 하위 논점" 으로 분해하십시오.
각 논점이 자식 노드가 됩니다. 각 자식은 다시 재귀적으로 분해됩니다.

### 원칙 4 — 실험 섹션은 자세히
Training, Results, Experiments 같은 섹션은 특히 자세히 해설:
- 하이퍼파라미터 선택 이유
- 실험 설계의 의도
- Table/Figure 의 수치 해석
- 비교 대상 선택 이유

### 원칙 5 — 한국어로
모든 설명은 한국어. 영어 원문 병기는 허용.

### 원칙 6 — 구체성
"중요한 개선", "혁신적" 같은 모호한 수사 금지. 구체적 용어와 수치 사용.

## 절대 금지
- 원문에 없는 사실 날조
- 저자와 무관한 교과서 설명
- 본문에 기초 개념 깊게 설명
- 모호한 표현
- 영어로만 작성

반드시 지정된 JSON 스키마로만 응답하십시오.\
"""
```

새 JSON 스키마:

```python
_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {
            "type": "string",
            "description": "이 노드의 주제를 짧은 한국어 명사구로",
        },
        "explanation": {
            "type": "string",
            "description": "top-down 저자 관점 해설 (한국어). 기초 개념은 [[REF:topic_id]] 로.",
        },
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "brief": {
                        "type": "string",
                        "description": "이 자식 노드가 다룰 하위 논점 한 줄 요약 (한국어)",
                    },
                },
                "required": ["concept", "brief"],
            },
            "description": "2~5 개의 하위 논점. max_depth 도달 시 빈 리스트.",
        },
        "prerequisites": {
            "type": "array",
            "items": {"type": "string"},
            "description": "explanation 에 등장한 기초 개념 topic_id 리스트 (소문자+언더스코어)",
        },
    },
    "required": ["concept", "explanation", "children", "prerequisites"],
}
```

기존 expander 의 재귀 로직에서:
1. Claude 호출 부분의 시스템 프롬프트와 스키마를 위 새 것으로 교체
2. Claude 응답 파싱 시 `children` 은 각각의 `concept` 와 `brief` 를 가진 딕셔너리 리스트
3. 각 자식에 대해 재귀 호출. 재귀 호출 시 `brief` 를 추가 컨텍스트로 전달
4. `prerequisites` 필드를 노드에 저장

**중요한 주의**:
- 기존 `verify_explanation` 호출 로직 유지 (이제 5축 검증)
- 기존 depth 가드 (`force_leaf`) 유지
- 기존 concept_cache 호출 유지 (중복 방지)
- `part` 필드는 2 (Part 2) 로 설정

### 9.4. dry_run 테스트

```bash
.venv/bin/python -c "
from pathlib import Path
from src.claude_client import ClaudeClient
from src.config import load_config
from src.data_types import RawSection
# expand_section 또는 실제 함수 이름
# from src.expander import expand_section

client = ClaudeClient(mode='dry_run')
config = load_config('config.yaml')

section = RawSection(
    title='Abstract',
    content='The Transformer is the first transduction model relying entirely on self-attention.',
    order=1,
)

# dry_run 에서는 빈 결과 또는 에러 예상
try:
    # result = expand_section(section, client, config)  # 실제 함수
    print('expander dry_run 구조 OK (실제 호출은 live 테스트에서)')
except Exception as e:
    print(f'dry_run 에러: {e}')
"
```

### 9.5. live 테스트 — attention_mini Abstract 1개만

**절대 Introduction 섹션은 건드리지 말 것. Abstract 만 테스트.**

```bash
.venv/bin/python << 'PYEOF'
import json
from pathlib import Path
from dataclasses import asdict
from src.claude_client import ClaudeClient
from src.config import load_config
from src.arxiv_parser import parse_arxiv
from src.chunker import split_into_raw_sections
from src.tree import ConceptNode
# from src.expander import expand_section  # 실제 함수 이름 사용

client = ClaudeClient(
    mode='cache',
    cache_dir=Path('samples/_tmp_phase3/cache'),
    max_total_calls=30,  # Abstract 1개 재귀 확장 여유
    sleep_between_calls=2,
)
config = load_config('config.yaml')

result = parse_arxiv(Path('data/papers/attention_mini'))
sections = split_into_raw_sections(result.markdown)
abstract = sections[0]
print(f'테스트 입력: {abstract.title} ({len(abstract.content)} chars)')

# expander 호출 (실제 함수 이름과 인자로 수정 필요)
print('expander 재귀 확장 시작...')
# root_node = expand_section(abstract, client, config)  # 실제 호출

# 결과를 트리 JSON 으로 저장
def tree_to_dict(node):
    return {
        'id': node.id,
        'concept': node.concept,
        'explanation': node.explanation,
        'prerequisites': node.prerequisites,
        'part': node.part,
        'depth': node.depth,
        'status': node.status,
        'children': [tree_to_dict(c) for c in node.children],
    }

# tree_json = tree_to_dict(root_node)
# output_path = Path('samples/_tmp_phase3/expander_abstract_output.json')
# with output_path.open('w', encoding='utf-8') as f:
#     json.dump(tree_json, f, ensure_ascii=False, indent=2)
# print(f'결과 저장: {output_path}')

stats = client.get_stats()
print(f'stats: {stats}')
print('expander live 테스트 완료 (사용자 검토 대기)')
PYEOF
```

**주의**: 위 스크립트는 실제 함수 이름 (`expand_section` 등) 으로 수정해야 한다.
`cat src/expander.py` 로 공개 함수 이름 확인 후 사용.

### 9.6. 커밋

```bash
git add src/expander.py docs/phase3/expander_design.md samples/_tmp_phase3/expander_abstract_output.json
git commit -m "feat(expander): rewrite internal logic for top-down Phase 3

- system prompt: author-centric, paper-centric explanation
- children represent sub-arguments not prerequisite concepts
- prerequisites field stores topic_id for Part 3 deferral
- [[REF:topic_id]] placeholders for basic concepts
- flow preserved: no textbook explanations inline
- public API unchanged
- tested with attention_mini Abstract section
- result saved to samples/_tmp_phase3/expander_abstract_output.json for review"
git log --oneline -3
```

---

## 단계 10. part3_writer 신규 모듈

### 10.1. 설계 문서

`docs/phase3/part3_writer_design.md`:

```markdown
# part3_writer.py 설계

## 단일 책임
`PrerequisiteTopic` 하나를 받아 해당 주제의 탄탄한 Part 3 항목
(`PrerequisiteEntry`) 을 생성한다.

## 공개 API

```python
def write_part3_topic(
    topic: PrerequisiteTopic,
    section_number: str,
    client: ClaudeClient,
    config: Part3Config,
) -> PrerequisiteEntry:
```

## Claude 호출
주제당 1~3 회. 주제 설명 + 하위 섹션 구조 생성.

## 프롬프트 원칙
- 독립적으로 읽을 수 있는 단위
- 얕지 않게: 학부 1학년이 이 논문 이해에 필요한 만큼
- 한 학기 교재 분량은 과함
- 정의 → 직관 → 원리 → 예시 → 논문과의 연결 순

## JSON 스키마
- title
- intro (짧은 도입)
- subsections: [{concept, explanation}]  — 4~8 개
- connection_to_paper: 논문과 어떻게 연결되는지
```

### 10.2. src/part3_writer.py 구현

```python
# 단일 책임: PrerequisiteTopic 하나를 받아 Part 3 항목을 생성
from __future__ import annotations

from src.claude_client import ClaudeClient
from src.data_types import PrerequisiteTopic, PrerequisiteEntry
from src.tree import ConceptNode


_SYSTEM_PROMPT = """\
당신은 AI 논문 이해에 필요한 기초 지식을 학부 1학년에게 가르치는 전문가입니다.

주어진 주제 하나에 대해 독립적으로 읽을 수 있는 "탄탄한" 설명을 작성하십시오.

## 대상 독자
고등학교 수학 2, 물리 1, 기초 프로그래밍을 이수한 대학교 1학년.
선형대수, 확률론, 머신러닝, 딥러닝 지식 없음.

## 깊이 기준
- 이 주제를 알아야 논문을 이해할 수 있을 만큼 **충분히 깊게**
- 한 학기 교재 분량은 과함 (5~15 분 분량)
- 한 줄 용어집은 부족 (얕지 않게)

## 작성 원칙

### 원칙 1 — 독립적 단위
이 Part 3 항목만 읽어도 주제를 이해할 수 있어야 함.
다른 Part 를 반드시 읽어야 이해되는 설명은 금지.

### 원칙 2 — 정의 → 직관 → 원리 → 예시 → 논문 연결
이 순서로 설명을 구성:
1. 정의 (이 개념이 무엇인가)
2. 직관적 비유 (쉬운 예시로 감을 잡기)
3. 원리 (수학적/논리적 설명)
4. 구체 예시 (숫자로 계산해보기)
5. 논문과의 연결 (이 논문에서 이 개념이 어떻게 쓰이는가)

### 원칙 3 — 한국어
모든 설명 한국어. 영어 원문 병기 허용.

### 원칙 4 — 구체성
수식은 LaTeX 로. 필요하면 숫자 예시. 모호한 수사 금지.

## 하위 섹션 구조
주제를 4~8 개의 하위 섹션으로 분해:
- 각 하위 섹션은 `concept` (짧은 제목) 과 `explanation` (본문) 을 가짐
- explanation 은 수식, 예시, 비유를 포함
- 길이는 하위 섹션당 약 200~500 자

## 절대 금지
- 다른 Part 에 의존하는 설명
- 모호한 표현
- 영어로만 작성
- 본문에 다시 [[REF:...]] 플레이스홀더 삽입 (Part 3 는 최종 단계)

반드시 지정된 JSON 스키마로만 응답하십시오.\
"""


_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "이 주제의 한국어 제목 (예: '벡터와 내적')",
        },
        "intro": {
            "type": "string",
            "description": "짧은 도입 (왜 이 주제가 필요한지 2~3 문장)",
        },
        "subsections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["concept", "explanation"],
            },
            "description": "4~8 개의 하위 섹션",
        },
        "connection_to_paper": {
            "type": "string",
            "description": "이 주제가 논문에서 어떻게 쓰이는지 설명",
        },
    },
    "required": ["title", "intro", "subsections", "connection_to_paper"],
}


def write_part3_topic(
    topic: PrerequisiteTopic,
    section_number: str,
    client: ClaudeClient,
) -> PrerequisiteEntry:
    """PrerequisiteTopic 을 받아 Part 3 항목을 생성한다.

    Args:
        topic: 생성할 주제 정보.
        section_number: Part 3 내 섹션 번호 (예: "3.1").
        client: ClaudeClient 인스턴스.

    Returns:
        PrerequisiteEntry 객체.

    Raises:
        ValueError: Claude 응답이 잘못되었을 때.
    """
    user_prompt = f"""다음 주제에 대해 Part 3 항목을 작성해주세요:

주제 ID: {topic.topic_id}
주제 제목: {topic.title}
이 주제가 등장하는 Part 2 노드 수: {len(topic.all_mentions)}

위 정보를 바탕으로 학부 1학년이 논문 이해에 필요한 만큼 충분히 깊게 설명해주세요."""

    result = client.call(
        user_prompt=user_prompt,
        system_prompt=_SYSTEM_PROMPT,
        json_schema=_SCHEMA,
    )

    title = result.get("title", "").strip() or topic.title
    if not title:
        raise ValueError(f"part3_writer: title is empty for {topic.topic_id}")

    subsections_data = result.get("subsections", [])
    if not subsections_data:
        raise ValueError(f"part3_writer: no subsections for {topic.topic_id}")

    # ConceptNode 리스트로 변환
    subsection_nodes: list[ConceptNode] = []
    for idx, sub in enumerate(subsections_data):
        concept = sub.get("concept", "").strip()
        explanation = sub.get("explanation", "").strip()
        if not concept or not explanation:
            continue
        node = ConceptNode(
            concept=concept,
            source_excerpt=topic.topic_id,  # Part 3 는 source_excerpt 가 topic_id
            explanation=explanation,
            part=3,
            ref_id=topic.topic_id,
            status='complete',
        )
        subsection_nodes.append(node)

    # intro 와 connection_to_paper 는 첫 subsection 앞뒤로 합치거나
    # 별도 필드에 저장. 여기서는 첫 번째 subsection 앞에 intro 를 붙인다.
    intro = result.get("intro", "").strip()
    connection = result.get("connection_to_paper", "").strip()

    if intro and subsection_nodes:
        subsection_nodes[0].explanation = f"{intro}\n\n{subsection_nodes[0].explanation}"

    if connection and subsection_nodes:
        last = subsection_nodes[-1]
        last.explanation = f"{last.explanation}\n\n**논문과의 연결**: {connection}"

    return PrerequisiteEntry(
        topic=topic,
        section_number=section_number,
        subsections=subsection_nodes,
        backlinks=topic.all_mentions,
    )
```

### 10.3. dry_run + live 테스트

```bash
.venv/bin/python << 'PYEOF'
import json
from pathlib import Path
from dataclasses import asdict
from src.claude_client import ClaudeClient
from src.data_types import PrerequisiteTopic
from src.part3_writer import write_part3_topic

client = ClaudeClient(
    mode='cache',
    cache_dir=Path('samples/_tmp_phase3/cache'),
    max_total_calls=5,
    sleep_between_calls=2,
)

topic = PrerequisiteTopic(
    topic_id='vector_dot_product',
    title='벡터와 내적',
    first_mention_in='fake_node_id',
    all_mentions=['fake_node_id_1', 'fake_node_id_2'],
)

print('part3_writer 호출 중...')
entry = write_part3_topic(topic, '3.1', client)

print(f'제목: {entry.topic.title}')
print(f'섹션 번호: {entry.section_number}')
print(f'하위 섹션 수: {len(entry.subsections)}')
for i, sub in enumerate(entry.subsections, 1):
    print(f'  {i}. {sub.concept} ({len(sub.explanation)} chars)')

# 결과 저장
def node_to_dict(n):
    return {
        'concept': n.concept,
        'explanation': n.explanation,
        'part': n.part,
        'ref_id': n.ref_id,
    }

output = {
    'topic': asdict(entry.topic),
    'section_number': entry.section_number,
    'subsections': [node_to_dict(s) for s in entry.subsections],
    'backlinks': entry.backlinks,
}

output_path = Path('samples/_tmp_phase3/part3_topic_output.json')
with output_path.open('w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'결과 저장: {output_path}')

stats = client.get_stats()
print(f'stats: {stats}')
print('part3_writer 테스트 완료')
PYEOF
```

### 10.4. 커밋

```bash
git add src/part3_writer.py docs/phase3/part3_writer_design.md samples/_tmp_phase3/part3_topic_output.json
git commit -m "feat(part3_writer): add Part 3 topic writer

- single Claude call generates a full Part 3 entry for one topic
- output: PrerequisiteEntry with 4~8 subsection ConceptNodes
- system prompt: independent readable unit, 'not shallow' depth standard
- structure: definition -> intuition -> principle -> example -> paper link
- tested with vector_dot_product topic"
git log --oneline -3
```

---

## 단계 11. assembler 3-Part 확장

### 11.1. 현재 assembler 분석

```bash
cat src/assembler.py
```

기존 렌더링 로직 파악. 특히:
- 공개 API (assemble_guidebook 또는 유사)
- Markdown 생성 방식
- 앵커 생성 (`_make_anchor`)
- 중복 링크 렌더링 로직

### 11.2. 설계 문서

`docs/phase3/assembler_design.md`:

```markdown
# assembler.py Phase 3 확장 설계

## 추가되는 것
3-Part 구조 출력 지원.

## 공개 API
기존 함수 유지 + 새 함수 추가 또는 기존 함수 확장:

```python
def assemble_3part_guidebook(
    analysis: PaperAnalysis,
    part2_trees: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> str:
    """3-Part 가이드북 Markdown 생성."""
```

## 출력 구조

```
# [논문 제목] — 완전판 가이드북

## Part 1. 논문이 무엇을 주장하는가 — 큰 그림

### 1.1 핵심 주장
[PaperAnalysis.core_thesis]

### 1.2 해결하려는 문제
[PaperAnalysis.problem_statement]

### 1.3 핵심 기여
- [key_contributions[0]]
- ...

### 1.4 주요 결과
- ...

### 1.5 이 논문의 의의
[significance]

### 1.6 읽는 법
[reading_guide]

## Part 2. 논문 따라 읽기 — 완전 해설

### 2.1 [첫 섹션 이름]
[expander 트리 렌더링]

### 2.2 [다음 섹션]
...

## Part 3. 기초 지식 탄탄히

### 3.1 [첫 주제 제목]
[part3_writer 출력 렌더링]

### 3.2 ...
```

## ref 치환
Part 2 렌더링 **전에** ref_resolver.resolve_refs() 를 호출해서
[[REF:...]] 을 앵커 링크로 치환.
```

### 11.3. assembler.py 수정

기존 `assemble_guidebook` 은 유지. 새 함수 `assemble_3part_guidebook` 추가.

```python
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
```

기존 `_make_anchor` 등 헬퍼는 재사용.

### 11.4. 단위 테스트 (Claude 호출 0)

```bash
.venv/bin/python << 'PYEOF'
from pathlib import Path
from src.tree import ConceptNode
from src.data_types import PaperAnalysis, PrerequisiteTopic, PrerequisiteEntry
from src.assembler import assemble_3part_guidebook

# 가짜 데이터
analysis = PaperAnalysis(
    title='Test Paper',
    authors=['A'],
    year=2024,
    core_thesis='저자는 X 를 주장한다.',
    problem_statement='기존 Y 의 한계.',
    key_contributions=['기여 1', '기여 2'],
    main_results=['결과 1'],
    significance='중요한 논문이다.',
    reading_guide='순서대로 읽으세요.',
    paper_structure=['Abstract', 'Introduction'],
)

# 가짜 Part 2 트리
abstract_root = ConceptNode(
    concept='Abstract',
    source_excerpt='x',
    explanation='저자는 Transformer 를 제안한다. [[REF:vector_dot_product]] 를 사용한다.',
    part=2,
)
child1 = ConceptNode(
    concept='하위 논점 1',
    source_excerpt='x',
    explanation='세부 설명 1',
    part=2,
)
abstract_root.children = [child1]

# 가짜 Part 3 엔트리
topic = PrerequisiteTopic(
    topic_id='vector_dot_product',
    title='벡터와 내적',
    first_mention_in='abs_id',
    all_mentions=['abs_id'],
)
sub = ConceptNode(
    concept='정의',
    source_excerpt='vector_dot_product',
    explanation='벡터의 내적은 ~이다.',
    part=3,
    ref_id='vector_dot_product',
)
entry = PrerequisiteEntry(
    topic=topic,
    section_number='3.1',
    subsections=[sub],
    backlinks=['abs_id'],
)

# 조립
markdown = assemble_3part_guidebook(analysis, [abstract_root], [entry])

print(markdown[:2000])
print('...' if len(markdown) > 2000 else '')

# 검증
assert 'Part 1' in markdown
assert 'Part 2' in markdown
assert 'Part 3' in markdown
assert '저자는 Transformer' in markdown
assert '벡터와 내적' in markdown
assert '[[REF:vector_dot_product]]' not in markdown  # 치환됨
assert '[Part 3.1 벡터와 내적]' in markdown  # 링크 생성

# 파일 저장
output_path = Path('samples/_tmp_phase3/assembler_3part_output.md')
with output_path.open('w', encoding='utf-8') as f:
    f.write(markdown)
print(f'결과 저장: {output_path}')
print('assembler 3-Part 테스트 완료')
PYEOF
```

### 11.5. 커밋

```bash
git add src/assembler.py docs/phase3/assembler_design.md samples/_tmp_phase3/assembler_3part_output.md
git commit -m "feat(assembler): add 3-Part guidebook assembly for Phase 3

- new function assemble_3part_guidebook
- renders Part 1 (big picture) from PaperAnalysis
- renders Part 2 (paper walkthrough) from expander tree recursively
- renders Part 3 (prerequisites) from part3_writer entries
- calls ref_resolver before rendering to substitute [[REF:...]] placeholders
- legacy assemble_guidebook kept for Phase 2 backward compat
- unit tested with fake data"
git log --oneline -3
```

---

## 단계 12. main.py 파이프라인 재배선

### 12.1. 현재 main.py 분석

```bash
cat src/main.py
```

기존 Phase 2 파이프라인 파악. CLI 인자, 순서, checkpoint 저장 위치 등.

### 12.2. Phase 3 파이프라인 추가

기존 Phase 2 경로는 유지하고, 새 Phase 3 경로 추가. 구분 방식:
- CLI 플래그 `--phase 3` (기본값: 3)
- 또는 별도 함수 `run_phase3_pipeline()` 추가

권장: **기존 `main()` 에 `--phase` 플래그 추가**. 기본값은 3.

```python
# main.py 상단 import 추가
from src.paper_analyzer import analyze_paper
from src.prerequisite_collector import collect_prerequisites
from src.part3_writer import write_part3_topic
from src.assembler import assemble_3part_guidebook
```

새 함수:

```python
def run_phase3_pipeline(args, config):
    """Phase 3 3-Part 가이드북 생성 파이프라인."""
    from pathlib import Path
    from src.claude_client import ClaudeClient
    from src.arxiv_parser import parse_arxiv
    from src.pdf_parser import parse_pdf
    from src.chunker import split_into_raw_sections
    # from src.expander import expand_section  # 실제 함수 이름

    client = ClaudeClient(
        mode=args.mode,
        cache_dir=Path(args.cache_dir),
        max_total_calls=config.claude.max_total_calls,
        sleep_between_calls=config.claude.sleep_between_calls,
    )

    # 1. Parse
    paper_path = Path(args.paper)
    if paper_path.is_dir():
        parse_result = parse_arxiv(paper_path)
    else:
        parse_result = parse_pdf(paper_path)
    markdown = parse_result.markdown
    print(f"[1/7] Parsed: {len(markdown)} chars")

    # 2. Analyze (Part 1 재료)
    print("[2/7] Analyzing paper (Part 1)...")
    analysis = analyze_paper(markdown, client)
    print(f"      Title: {analysis.title}")

    # 3. Chunk
    print("[3/7] Chunking into sections...")
    sections = split_into_raw_sections(markdown)
    print(f"      {len(sections)} sections")

    # 4. Expand (Part 2)
    print("[4/7] Expanding sections (Part 2, top-down)...")
    part2_trees = []
    for section in sections:
        # root = expand_section(section, client, config)  # 실제 호출
        # part2_trees.append(root)
        pass
    print(f"      {len(part2_trees)} root nodes")

    # 5. Collect prerequisites
    print("[5/7] Collecting prerequisites...")
    topics = collect_prerequisites(
        part2_trees,
        config.part3.predefined_pool,
        allow_new=config.part3.allow_claude_to_add,
    )
    print(f"      {len(topics)} unique topics")

    # 6. Write Part 3
    print("[6/7] Writing Part 3 entries...")
    part3_entries = []
    for idx, topic in enumerate(topics, start=1):
        section_num = f"3.{idx}"
        entry = write_part3_topic(topic, section_num, client)
        part3_entries.append(entry)
    print(f"      {len(part3_entries)} entries")

    # 7. Assemble
    print("[7/7] Assembling 3-Part guidebook...")
    guidebook_md = assemble_3part_guidebook(analysis, part2_trees, part3_entries)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(guidebook_md, encoding='utf-8')
    print(f"Done: {output_path} ({len(guidebook_md)} chars)")

    stats = client.get_stats()
    print(f"Stats: {stats}")
    return output_path, stats
```

기존 `main()` 에서 Phase 3 를 호출하도록 수정:

```python
# argparse 에 추가
parser.add_argument('--phase', type=int, default=3, choices=[2, 3],
                    help='Pipeline version')

# main 분기
if args.phase == 3:
    run_phase3_pipeline(args, config)
else:
    # 기존 Phase 2 로직
    run_phase2_pipeline(args, config)  # 기존 함수로 리팩터
```

**중요**: 기존 로직을 `run_phase2_pipeline` 같은 이름으로 묶어서 보존하고,
새 `run_phase3_pipeline` 을 추가하는 방식. 기존 코드를 지우지 말 것.

### 12.3. dry_run 검증

```bash
.venv/bin/python src/main.py \
    --paper data/papers/attention_mini \
    --output /tmp/test_guidebook.md \
    --mode dry_run \
    --cache-dir samples/_tmp_phase3/cache \
    --phase 3 2>&1 | head -30
```

dry_run 은 Claude 호출 없이 구조 확인용. 에러 없이 스크립트가 끝까지 돌아가면 OK.

### 12.4. 커밋

```bash
git add src/main.py
git commit -m "feat(main): add Phase 3 pipeline with 3-Part guidebook flow

- new run_phase3_pipeline: parse -> analyze -> chunk -> expand -> collect
  -> part3 -> assemble
- --phase CLI flag (default 3) for Phase 2/3 selection
- Phase 2 logic preserved as run_phase2_pipeline
- dry_run mode works end-to-end without Claude calls"
git log --oneline -3
```

---

## 단계 13. End-to-end 테스트 (attention_mini)

### 13.1. 작은 end-to-end 실행

**절대 Attention 전체 논문 금지**. `data/papers/attention_mini` 만 사용.

```bash
mkdir -p samples/_tmp_phase3
time .venv/bin/python src/main.py \
    --paper data/papers/attention_mini \
    --output samples/_tmp_phase3/end_to_end_attention_mini.md \
    --mode cache \
    --cache-dir samples/_tmp_phase3/cache \
    --phase 3 2>&1 | tee samples/_tmp_phase3/end_to_end_log.txt
```

예상 소요: 10~20분, Claude 호출 약 30~60 회.

### 13.2. 결과 확인

```bash
# 파일 크기
wc -l samples/_tmp_phase3/end_to_end_attention_mini.md
wc -c samples/_tmp_phase3/end_to_end_attention_mini.md

# 구조 확인
grep -n "^## Part" samples/_tmp_phase3/end_to_end_attention_mini.md

# 미해결 플레이스홀더 있는지
grep -n "\[\[UNRESOLVED:" samples/_tmp_phase3/end_to_end_attention_mini.md || echo "미해결 없음"
grep -n "\[\[REF:" samples/_tmp_phase3/end_to_end_attention_mini.md || echo "REF 모두 치환됨"
```

### 13.3. 통계 저장

```bash
cat > samples/_tmp_phase3/end_to_end_stats.json << EOF
{
  "timestamp": "$(date -Iseconds)",
  "paper": "attention_mini",
  "output_file": "samples/_tmp_phase3/end_to_end_attention_mini.md",
  "output_lines": $(wc -l < samples/_tmp_phase3/end_to_end_attention_mini.md),
  "output_bytes": $(wc -c < samples/_tmp_phase3/end_to_end_attention_mini.md),
  "log_file": "samples/_tmp_phase3/end_to_end_log.txt"
}
EOF
cat samples/_tmp_phase3/end_to_end_stats.json
```

### 13.4. 커밋

```bash
git add samples/_tmp_phase3/end_to_end_attention_mini.md samples/_tmp_phase3/end_to_end_stats.json samples/_tmp_phase3/end_to_end_log.txt
git commit -m "test(phase3): end-to-end run on attention_mini

- runs full Phase 3 pipeline: parse -> analyze -> expand -> part3 -> assemble
- attention_mini only (Abstract + Introduction, not full paper)
- cache mode for reproducibility
- output saved for user review (NO quality judgment by Claude Code)
- stats: see end_to_end_stats.json"
git log --oneline -3
```

---

## 단계 14. 작업 보고서 작성

### 14.1. 최종 상태 수집

```bash
git log --oneline -15 > /tmp/phase3_core_log.txt
cat /tmp/phase3_core_log.txt

ls -la samples/_tmp_phase3/
find src/ -name "*.py" -newer /tmp/phase3_core_start_commit.txt 2>/dev/null || ls -la src/*.py
```

### 14.2. PHASE3_CORE_WORK_REPORT.md 작성

프로젝트 루트에 보고서 생성:

```markdown
# Phase 3 Core 작업 보고서

**작업 일시**: [date]
**작업자**: Claude Code (자율 실행 모드, 옵션 C 풀 버전)
**시작 커밋**: 58889d9 docs: add Phase 3 skeleton preparation report

---

## 작업 결과 요약

| 단계 | 내용 | 결과 | 커밋 |
|---|---|---|---|
| 8 | verifier 5축 확장 | [완료/실패] | [해시] |
| 9 | expander top-down 재작성 | [완료/실패] | [해시] |
| 10 | part3_writer 신규 | [완료/실패] | [해시] |
| 11 | assembler 3-Part 확장 | [완료/실패] | [해시] |
| 12 | main.py 파이프라인 재배선 | [완료/실패] | [해시] |
| 13 | attention_mini end-to-end 테스트 | [완료/실패] | [해시] |

총 커밋 수: [N]
총 Claude 호출 수: [N]

---

## 각 단계 상세

### 단계 8. verifier 5축 확장
- 추가된 축: paper_centric, flow
- 기존 4축 유지
- 공개 API 유지
- dry_run: [결과]
- live 테스트: [결과 파일 경로]
- 커밋: [해시]

### 단계 9. expander top-down 재작성 (★)
- 시스템 프롬프트 재작성 완료 (paper_analyzer 스타일 적용)
- JSON 스키마 변경 (children 의 concept/brief, prerequisites 필드)
- dry_run: [결과]
- live 테스트 (attention_mini Abstract): [Claude 호출 N회, 결과 파일]
- 커밋: [해시]

### 단계 10. part3_writer 신규
- 구현 완료
- 단위 테스트: [결과]
- live 테스트 (vector_dot_product): [결과 파일]
- 커밋: [해시]

### 단계 11. assembler 3-Part 확장
- assemble_3part_guidebook 함수 추가
- 기존 assemble_guidebook 유지 (Phase 2 호환)
- ref_resolver 호출 포함
- 단위 테스트 (가짜 데이터): [결과]
- 결과 파일: samples/_tmp_phase3/assembler_3part_output.md
- 커밋: [해시]

### 단계 12. main.py 파이프라인 재배선
- run_phase3_pipeline 함수 추가
- --phase CLI 플래그 추가 (기본값 3)
- 기존 Phase 2 로직 보존
- dry_run 검증: [결과]
- 커밋: [해시]

### 단계 13. End-to-end 테스트
- 입력: data/papers/attention_mini
- 모드: cache
- 결과 파일: samples/_tmp_phase3/end_to_end_attention_mini.md
- 파일 크기: [N 줄, N bytes]
- Claude 호출 수: [N]
- 소요 시간: [N 분]
- 미해결 플레이스홀더: [있음/없음]
- 커밋: [해시]

---

## 현재 git 상태

### 최근 커밋 (단계 8~13)
[git log --oneline 출력]

### 생성된 파일
[find 출력]

---

## 실패한 작업 / 결정 필요

[있으면 여기]

---

## 사용자에게 확인 요청

**필수 검토 사항** (사용자 판단 영역):

1. **전체 가이드북 품질**:
   `cat samples/_tmp_phase3/end_to_end_attention_mini.md` 로 읽고 판단.
   - Part 1 (큰 그림) 이 논문을 잘 요약하는가?
   - Part 2 가 top-down 으로 작성됐는가? (bottom-up 회귀 여부)
   - Part 2 에 기초 지식이 깊게 박혀있지 않은가?
   - Part 3 가 탄탄한가?
   - 전체 흐름이 자연스러운가?

2. **개별 모듈 결과물**:
   - verifier: samples/_tmp_phase3/verifier_5axis_test.json
   - expander: samples/_tmp_phase3/expander_abstract_output.json
   - part3_writer: samples/_tmp_phase3/part3_topic_output.json
   - assembler: samples/_tmp_phase3/assembler_3part_output.md

3. **다음 단계**:
   - 사용자 검토 후 만족스러우면: Attention 전체 논문으로 실행
   - 개선 필요하면: 해당 모듈 프롬프트 조정

---

## 전체 Claude 호출 내역

- 단계 8 verifier: [N]
- 단계 9 expander: [N]
- 단계 10 part3_writer: [N]
- 단계 11 assembler: 0
- 단계 12 main: 0
- 단계 13 end-to-end: [N]

**총계**: [N] calls

---

**보고서 끝. 사용자 검토 대기.**
```

### 14.3. 보고서 커밋

```bash
git add PHASE3_CORE_WORK_REPORT.md
git commit -m "docs: add Phase 3 Core work report

- documents steps 8-13 (verifier, expander, part3_writer, assembler, main, e2e)
- lists Claude calls per step
- provides user review checklist (no quality judgment by Claude Code)
- identifies review files in samples/_tmp_phase3/"
git log --oneline -15
```

### 14.4. 최종 출력

```bash
echo ""
echo "════════════════════════════════════════════════════════════"
echo "    Phase 3 Core 작업 완료 (옵션 C 풀 버전)"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "보고서: PHASE3_CORE_WORK_REPORT.md"
echo ""
echo "사용자 검토 필수 파일:"
echo "  ★ samples/_tmp_phase3/end_to_end_attention_mini.md (최종 가이드북)"
echo "  - samples/_tmp_phase3/expander_abstract_output.json"
echo "  - samples/_tmp_phase3/part3_topic_output.json"
echo "  - samples/_tmp_phase3/verifier_5axis_test.json"
echo "  - samples/_tmp_phase3/assembler_3part_output.md"
echo ""
echo "확인 명령:"
echo "  cat PHASE3_CORE_WORK_REPORT.md"
echo "  cat samples/_tmp_phase3/end_to_end_attention_mini.md"
echo ""
echo "다음 단계 (사용자 판단 후):"
echo "  - 품질 OK: Attention 전체 논문 실행"
echo "  - 개선 필요: 해당 모듈 프롬프트 조정 (사용자와 함께)"
echo ""
echo "════════════════════════════════════════════════════════════"
```

---

**지시 끝. 끝까지 자율 진행. 중간 보고 없음. 완료 후 PHASE3_CORE_WORK_REPORT.md 와 samples/_tmp_phase3/end_to_end_attention_mini.md 확인.**
