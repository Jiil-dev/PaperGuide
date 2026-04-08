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
자유 텍스트, 주석, 설명 없이 오직 JSON 만.\
"""


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
            "description": "논문 섹션 이름을 순서대로",
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
