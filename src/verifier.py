# 단일 책임: ConceptNode의 explanation이 source_excerpt에 충실하고 학부 1학년에게 적절한지 Claude 호출로 검증한다.
from __future__ import annotations

import random

from src.claude_client import ClaudeClient
from src.tree import ConceptNode

_TARGET_LEVEL = "고등학교 수학2, 물리1, 기초 프로그래밍 수준을 이수한 대학교 1학년 학생"

_SYSTEM_PROMPT = """\
당신은 AI 논문 해설서의 품질 검증자입니다.
주어진 '설명(explanation)'이 '원문(source_excerpt)'을 기반으로 정확하고,
목표 독자 수준에 적합한지 엄격하게 판정하십시오.

검증 항목 6가지를 모두 적용합니다:

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

판정 기준:
- 6가지 항목 모두 통과해야 passed=true.
- 하나라도 문제가 있으면 passed=false이고 errors에 해당 항목을 기록.
- confidence는 0.0~1.0. 설명의 전반적 품질에 대한 확신도.
- paper_centric과 flow는 각각 1~5 점 스케일로 별도 보고.

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

위 6가지 검증 항목(원문 충실성, 수준 적절성, 자기충족성, 수식 정확성,
논문 중심성, 흐름 유지)을 적용하여 판정 결과를 JSON으로 반환하세요.\
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
        "notes": {
            "type": "string",
            "description": "추가 코멘트 (자유 형식)",
        },
    },
    "required": ["passed", "confidence", "errors", "paper_centric", "flow", "notes"],
}


class Verifier:
    """검증기.

    ConceptNode의 explanation을 6가지 항목으로 검증:
    원문 충실성, 수준 적절성, 자기충족성, 수식 정확성, 논문 중심성, 흐름 유지.
    """

    def __init__(
        self,
        client: ClaudeClient,
        min_confidence: float = 0.7,
        sample_rate: float = 1.0,
    ):
        """검증기를 초기화한다.

        Args:
            client: ClaudeClient 인스턴스 (모드 무관).
            min_confidence: 이 이상의 confidence여야 최종 통과.
            sample_rate: 검증 수행 확률 (0.0~1.0). 1.0이면 전수, 0.1이면 10%만 검증.
        """
        self._client = client
        self._min_confidence = min_confidence
        self._sample_rate = sample_rate
        self._verify_count = 0
        self._skip_count = 0

    def verify(self, node: ConceptNode) -> dict:
        """노드의 explanation을 검증한다.

        Args:
            node: explanation이 채워진 ConceptNode.

        Returns:
            dict: passed, confidence, errors, notes, passed_final 포함.
        """
        # 샘플링: sample_rate 확률로만 실제 검증
        if random.random() > self._sample_rate:
            self._skip_count += 1
            return {
                "passed": True,
                "confidence": 1.0,
                "errors": [],
                "paper_centric": {"score": 5, "reason": "sampled out"},
                "flow": {"score": 5, "reason": "sampled out"},
                "notes": "sampled out",
                "passed_final": True,
            }
        self._verify_count += 1

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
        paper_centric = result.get("paper_centric", {"score": 0, "reason": ""})
        flow = result.get("flow", {"score": 0, "reason": ""})
        notes = result.get("notes", "")

        passed_final = passed and (confidence >= self._min_confidence)

        return {
            "passed": passed,
            "confidence": confidence,
            "errors": errors,
            "paper_centric": paper_centric,
            "flow": flow,
            "notes": notes,
            "passed_final": passed_final,
        }
