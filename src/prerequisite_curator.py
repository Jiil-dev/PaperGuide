# 단일 책임: Claude 를 이용해 수집된 prerequisite 후보 중 진짜 핵심만 선별
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.claude_client import ClaudeClient
    from src.data_types import PrerequisiteTopic, PaperAnalysis


_SYSTEM_PROMPT = """\
당신은 학부 1학년이 AI 논문을 이해할 수 있도록 돕는 큐레이터입니다.

주어진 prerequisite 후보 리스트에서 "이 논문 이해에 진짜 필요한 주제만" 골라주세요.

## 선별 원칙

1. **충분성**: 학부 1학년이 이 논문의 본문을 이해하는 데 필요한 모든 기초 지식
2. **간결성**: 부수적이거나 너무 좁은 주제는 제외
3. **통합**: 비슷한 여러 주제는 하나로 (예: BERT Architecture + BERT Tokenizer → "BERT 개요")
4. **가변 N**: 논문에 따라 5~30 개 사이에서 자유롭게 결정
   - 단순한 한 분야 논문 → 5~10 개
   - 여러 분야 종합 논문 → 15~25 개

## 제외할 것

- 너무 좁은 알고리즘 이름 (예: "BERT CLS Token", "Beta VAE")
- 논문 고유 명칭 (예: "ALOHA", "ACT Policy")
- 단순 변형 (단/복수, 형용사 차이)
- 본문에서 한 번만 언급된 주변 개념

반드시 지정된 JSON 스키마로만 응답하십시오.\
"""


_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string"},
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["topic_id", "title", "rationale"],
            },
            "description": "선별된 prerequisite 주제들 (5~30 개, 논문에 따라 가변)",
        },
    },
    "required": ["selected_topics"],
}


@dataclass
class CuratedTopic:
    topic_id: str
    title: str
    rationale: str


def curate_prerequisites(
    candidates: list,
    paper_analysis,
    client,
) -> list:
    """수집된 prerequisite 후보들을 Claude 로 큐레이션.

    Args:
        candidates: prerequisite_collector 가 수집한 PrerequisiteTopic 리스트.
        paper_analysis: PaperAnalysis 객체.
        client: ClaudeClient 인스턴스.

    Returns:
        큐레이션된 PrerequisiteTopic 리스트 (가변 길이).
    """
    from src.data_types import PrerequisiteTopic

    if not candidates:
        return []

    candidates_text = "\n".join(
        f"- {t.topic_id}: {t.title}" for t in candidates
    )

    user_prompt = f"""## 논문 정보

제목: {paper_analysis.title}

핵심 주장: {paper_analysis.core_thesis}

## 후보 prerequisite 리스트 ({len(candidates)} 개)

{candidates_text}

위 후보들 중 학부 1학년이 이 논문 본문을 이해하는 데 진짜 필요한 주제만 골라
JSON 으로 응답하세요. 5~30 개 사이에서 논문에 맞게 자유롭게 결정하세요."""

    response = client.call(
        user_prompt=user_prompt,
        system_prompt=_SYSTEM_PROMPT,
        json_schema=_SCHEMA,
    )

    selected = response.get("selected_topics", [])
    candidate_map = {t.topic_id: t for t in candidates}

    result = []
    for sel in selected:
        topic_id = sel.get("topic_id", "")
        title = sel.get("title", "")
        if not topic_id or not title:
            continue
        if topic_id in candidate_map:
            original = candidate_map[topic_id]
            result.append(PrerequisiteTopic(
                topic_id=topic_id,
                title=title,
                first_mention_in=original.first_mention_in,
                all_mentions=original.all_mentions,
            ))
        else:
            result.append(PrerequisiteTopic(
                topic_id=topic_id,
                title=title,
                first_mention_in="",
                all_mentions=[],
            ))

    return result
