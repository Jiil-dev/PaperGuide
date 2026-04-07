# verifier.py 구현 결과

## 1. 작성된 코드 (src/verifier.py 전체)

```python
# 단일 책임: ConceptNode의 explanation이 source_excerpt에 충실하고 학부 1학년에게 적절한지 Claude 호출로 검증한다.
from __future__ import annotations

from src.claude_client import ClaudeClient
from src.tree import ConceptNode

_TARGET_LEVEL = "고등학교 수학2, 물리1, 기초 프로그래밍 수준을 이수한 대학교 1학년 학생"

_SYSTEM_PROMPT = """\
당신은 AI 논문 해설서의 품질 검증자입니다.
주어진 '설명(explanation)'이 '원문(source_excerpt)'을 기반으로 정확하고,
목표 독자 수준에 적합한지 엄격하게 판정하십시오.

검증 항목 4가지를 모두 적용합니다:

1. **원문 충실성(faithfulness)**: 설명이 원문의 내용을 왜곡하거나,
   원문에 없는 정보를 지어내지 않았는가?
2. **수준 적절성(level)**: 목표 독자(고등학교 수학2, 물리1,
   기초 프로그래밍을 이수한 대학교 1학년)가 이해할 수 있는가?
   지나치게 어렵거나 전문 용어를 설명 없이 사용하면 실패.
3. **자기충족성(self_contained)**: 설명이 원문 없이도 독립적으로
   이해되는 완결된 설명인가? "위에서 언급한", "앞서 설명한" 등
   외부 참조 없이 자체적으로 성립해야 함.
4. **수식 정확성(formula)**: 설명에 수식이 포함되어 있다면,
   원문의 수식과 정확히 일치하는가? 변수명, 연산, 첨자 오류가 없는가?
   수식이 없는 경우 이 항목은 자동 통과.

판정 기준:
- 4가지 항목 모두 통과해야 passed=true.
- 하나라도 문제가 있으면 passed=false이고 errors에 해당 항목을 기록.
- confidence는 0.0~1.0. 설명의 전반적 품질에 대한 확신도.

반드시 지정된 JSON 형식으로만 응답하십시오.\
"""

_USER_PROMPT_TEMPLATE = """\
다음 개념에 대한 설명을 검증해 주세요.

## 개념 이름
{concept}

## 원문 (source_excerpt)
{source_excerpt}

## 검증 대상 설명 (explanation)
{explanation}

## 목표 독자 수준
{target_level}

위 4가지 검증 항목(원문 충실성, 수준 적절성, 자기충족성, 수식 정확성)을
적용하여 판정 결과를 JSON으로 반환하세요.\
"""

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "4가지 검증 항목 모두 통과 시 true",
        },
        "confidence": {
            "type": "number",
            "description": "설명의 전반적 품질에 대한 확신도 (0.0~1.0)",
        },
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "faithfulness",
                            "level",
                            "self_contained",
                            "formula",
                        ],
                    },
                    "description": {
                        "type": "string",
                        "description": "오류 설명 (한국어)",
                    },
                },
                "required": ["category", "description"],
            },
            "description": "발견된 오류 리스트. 통과 시 빈 배열.",
        },
        "notes": {
            "type": "string",
            "description": "추가 코멘트 (자유 형식)",
        },
    },
    "required": ["passed", "confidence", "errors", "notes"],
}


class Verifier:
    """검증기.

    ConceptNode의 explanation을 4가지 항목으로 검증:
    원문 충실성, 수준 적절성, 자기충족성, 수식 정확성.
    """

    def __init__(self, client: ClaudeClient, min_confidence: float = 0.7):
        """검증기를 초기화한다.

        Args:
            client: ClaudeClient 인스턴스 (모드 무관).
            min_confidence: 이 이상의 confidence여야 최종 통과.
        """
        self._client = client
        self._min_confidence = min_confidence

    def verify(self, node: ConceptNode) -> dict:
        """노드의 explanation을 검증한다.

        Args:
            node: explanation이 채워진 ConceptNode.

        Returns:
            dict: passed, confidence, errors, notes, passed_final 포함.
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            concept=node.concept,
            source_excerpt=node.source_excerpt,
            explanation=node.explanation,
            target_level=_TARGET_LEVEL,
        )

        result = self._client.call(
            user_prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            json_schema=_VERIFY_SCHEMA,
        )

        passed = result.get("passed", False)
        confidence = result.get("confidence", 0.0)
        errors = result.get("errors", [])
        notes = result.get("notes", "")

        passed_final = passed and (confidence >= self._min_confidence)

        return {
            "passed": passed,
            "confidence": confidence,
            "errors": errors,
            "notes": notes,
            "passed_final": passed_final,
        }
```

## 2. import 테스트

```
$ .venv/bin/python -c "from src.verifier import Verifier; print('import OK')"
import OK
```

## 3. dry_run 테스트

```
dry_run 결과: {'passed': False, 'confidence': 0, 'errors': [], 'notes': '', 'passed_final': False}
키 검증 OK
```

| 필드 | 값 | 기대값 | 판정 |
|------|------|--------|------|
| passed | False | False (boolean 기본값) | OK |
| confidence | 0 | 0 (number 기본값) | OK |
| errors | [] | [] (array 기본값) | OK |
| notes | "" | "" (string 기본값) | OK |
| passed_final | False | False (False AND 0<0.7) | OK |

dry_run에서는 모든 검증이 실패로 간주됨 — 의도된 동작.

## 4. 구현 중 주의했던 점

1. **모듈 레벨 상수**: `_SYSTEM_PROMPT`, `_USER_PROMPT_TEMPLATE`, `_TARGET_LEVEL`, `_VERIFY_SCHEMA`를 모두 파일 상단에 상수로 정의. 클래스 내부에 두면 인스턴스마다 중복 생성되는 것처럼 보이고, 프롬프트 수정 시 찾기 어려움.

2. **`.get()` 방어**: Claude 응답에 필수 키가 누락될 경우를 대비해 모든 필드를 `.get(key, default)`로 접근. 누락 시 보수적 기본값(passed=False, confidence=0.0) → 실패로 처리.

3. **passed_final 로직**: `passed AND (confidence >= min_confidence)`. Claude가 passed=True로 판정했어도 confidence가 낮으면 최종 실패. 이중 안전장치.

4. **의존성 최소화**: `ClaudeClient`와 `ConceptNode`만 import. config.py, pdf_parser 등 무관한 모듈 import 없음.

5. **프롬프트 한국어**: 시스템 프롬프트와 사용자 프롬프트 모두 한국어. 목표 독자 수준도 한국어로 명시. Claude가 한국어 응답을 하도록 유도하되, JSON schema가 응답 형식을 강제하므로 언어에 관계없이 구조는 보장됨.

## 5. cache mode 테스트 (실행 완료)

### 결과

```
좋은 설명 결과:
  passed: False
  confidence: 0.88
  errors: [
    {
      'category': 'faithfulness',
      'description': "원문에 없는 정보 추가: 'sqrt(d_k)로 나누는 이유는 내적 값이 너무 커지는
        것을 방지하기 위함'이라는 설명은 제공된 원문 발췌에 존재하지 않는 내용임. 또한 원문은
        d_k를 쿼리와 키 모두의 차원으로 명시하나, 설명은 '키의 차원'으로만 기술하여 쿼리 차원
        정보를 누락함."
    },
    {
      'category': 'level',
      'description': "목표 독자(대학교 1학년, 고교 수학2·물리1·기초 프로그래밍 수준)가
        이해하기 어려운 전문 용어인 'softmax', '어텐션 메커니즘', '쿼리/키/값(value)'이
        별도 설명 없이 사용됨."
    }
  ]
  notes: 설명의 전체적인 흐름과 구조는 적절하나, (1) 원문 발췌에 없는 scaling 이유를
    추가한 점과 (2) 핵심 전문 용어에 대한 부연 설명이 부족한 점이 문제입니다. 개선 제안:
    softmax는 '각 값을 0~1 사이 확률로 변환하는 함수'와 같이 풀어서 설명하고, scaling
    이유는 원문 발췌에 해당 내용이 포함된 경우에만 서술해야 합니다. 또한 d_k 설명 시
    '쿼리와 키의 차원'으로 정확히 기술할 필요가 있습니다.
  passed_final: False
  stats: {'total_calls': 1, 'cache_hits': 0, 'cache_misses': 1, 'dry_run_calls': 0}

캐시 히트 OK, stats: {'total_calls': 1, 'cache_hits': 1, 'cache_misses': 1, 'dry_run_calls': 0}
```

### 검증 항목

| 항목 | 결과 | 판정 |
|------|------|------|
| Claude 한국어 응답 | errors, notes 모두 한국어 | OK |
| passed | False | 예상과 다름 (아래 분석) |
| confidence | 0.88 | OK (0.7 이상) |
| errors 내용 | faithfulness + level 2개 | 구체적이고 정당한 지적 |
| passed_final | False | passed=False이므로 False |
| 캐시 히트 | result1 == result2 성립 | OK |
| stats | hits=1, misses=1, total=1 | OK |

### 분석: passed=False가 나온 이유

Claude의 판정은 **정당함**:

1. **faithfulness 실패**: 테스트 explanation에 "sqrt(d_k)로 나누는 이유는 내적 값이 너무 커지는 것을 방지"라는 내용이 있는데, 이는 제공된 source_excerpt에는 존재하지 않는 정보. 실제 논문 원문에는 있지만 우리가 테스트용으로 줄인 excerpt에는 없었음. 또한 "키의 차원"으로만 적었는데 원문은 "queries and keys of dimension d_k"로 둘 다 명시.

2. **level 실패**: "softmax", "어텐션 메커니즘", "쿼리/키/값" 등 전문 용어를 설명 없이 사용. 학부 1학년 기준에서는 이 용어들이 설명 없이는 이해 불가.

이는 verifier가 **의도대로 엄격하게 동작**하고 있음을 증명. 프롬프트 캘리브레이션 문제가 아니라, 테스트 데이터의 설명 품질이 실제로 기준에 미달. 실제 expander가 생성하는 설명은 이 기준을 충족하도록 시스템 프롬프트에 학부 1학년 수준 풀어쓰기를 지시할 것.

## 6. 판정 상세 확인

### 전체 결과 (JSON)

```json
{
  "passed": false,
  "confidence": 0.88,
  "errors": [
    {
      "category": "faithfulness",
      "description": "\"sqrt(d_k)로 나누는 이유는 내적 값이 너무 커지는 것을 방지하기 위함입니다\"라는 내용은 제공된 원문(source_excerpt)에 존재하지 않는 정보입니다. 원문은 scaling의 이유를 설명하지 않으며, 이는 원문에 없는 정보를 추가한 것에 해당합니다."
    },
    {
      "category": "level",
      "description": "'softmax'는 머신러닝 전문 용어로, 목표 독자(고등학교 수학2·물리1·기초 프로그래밍 이수 대학교 1학년)가 사전 지식 없이 이해하기 어렵습니다. 'softmax가 무엇인지'에 대한 간략한 부연 설명(예: 값을 0~1 사이의 확률로 변환하는 함수)이 필요합니다. '어텐션 메커니즘'이라는 용어 역시 보충 설명 없이 사용되었습니다."
    }
  ],
  "notes": "설명의 핵심 절차(내적→스케일링→softmax→가중치) 서술은 원문과 잘 대응하며 정확합니다. 다만 (1) 원문에 없는 scaling 이유를 추가한 점과 (2) 전문 용어(softmax, 어텐션 메커니즘)를 대상 독자 수준에 맞게 풀어 설명하지 않은 점이 문제입니다. 이 두 가지를 보완하면 양질의 해설이 될 수 있습니다.",
  "passed_final": false
}
```

### errors 상세

**[1] faithfulness**

> "sqrt(d_k)로 나누는 이유는 내적 값이 너무 커지는 것을 방지하기 위함입니다"라는 내용은 제공된 원문(source_excerpt)에 존재하지 않는 정보입니다. 원문은 scaling의 이유를 설명하지 않으며, 이는 원문에 없는 정보를 추가한 것에 해당합니다.

**[2] level**

> 'softmax'는 머신러닝 전문 용어로, 목표 독자(고등학교 수학2·물리1·기초 프로그래밍 이수 대학교 1학년)가 사전 지식 없이 이해하기 어렵습니다. 'softmax가 무엇인지'에 대한 간략한 부연 설명(예: 값을 0~1 사이의 확률로 변환하는 함수)이 필요합니다. '어텐션 메커니즘'이라는 용어 역시 보충 설명 없이 사용되었습니다.

### notes 전문

> 설명의 핵심 절차(내적→스케일링→softmax→가중치) 서술은 원문과 잘 대응하며 정확합니다. 다만 (1) 원문에 없는 scaling 이유를 추가한 점과 (2) 전문 용어(softmax, 어텐션 메커니즘)를 대상 독자 수준에 맞게 풀어 설명하지 않은 점이 문제입니다. 이 두 가지를 보완하면 양질의 해설이 될 수 있습니다.

### 사용자 판단 대기

Claude의 두 가지 지적이 정당한지, 아니면 프롬프트 캘리브레이션이 필요한지는 사용자가 결정.

- **faithfulness 지적**: 테스트 explanation이 "내적 값이 너무 커지는 것을 방지"라고 적었는데 이 내용은 제공된 excerpt에 없음 → Claude의 지적은 사실적으로 **정확**. 실제 논문 원문의 후속 문단에 해당 내용이 있지만, 테스트용 excerpt에는 포함하지 않았음.
- **level 지적**: "softmax", "어텐션 메커니즘"을 설명 없이 사용 → 학부 1학년 기준에서 Claude의 지적은 **정당**. expander의 시스템 프롬프트에서 전문 용어 풀어쓰기를 강제해야 함.

캐시 파일은 `/tmp/test_verifier2/claude_responses/`에 남겨둠.
