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
            source_excerpt=topic.topic_id,
            explanation=explanation,
            part=3,
            ref_id=topic.topic_id,
            status='done',
        )
        subsection_nodes.append(node)

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
