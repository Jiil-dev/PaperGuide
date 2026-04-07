# 단일 책임: ConceptNode 트리를 DFS로 재귀 확장한다. Claude로 explanation + children을 생성하고, verifier로 검증하며, concept_cache로 중복을 차단한다.
from __future__ import annotations

from typing import Callable

from src.claude_client import ClaudeClient, RateLimitExceeded
from src.concept_cache import ConceptCache
from src.tree import ConceptNode
from src.verifier import Verifier

_SYSTEM_PROMPT = """\
당신은 AI 논문 해설서의 저자입니다.
주어진 개념을 목표 독자가 완벽히 이해할 수 있도록 설명하십시오.

## 목표 독자
고등학교 수학2(미적분 기초), 물리1, 기초 프로그래밍을 이수한 대학교 1학년.
선형대수, 확률론, 머신러닝, 딥러닝 지식은 전혀 없습니다.

## 작성 규칙
1. **전문 용어 풀어쓰기**: 전문 용어가 처음 등장하면 반드시 괄호 안에
   학부 1학년이 이해할 수 있는 풀이를 병기하십시오.
   예: "softmax(각 값을 0~1 사이 확률로 변환하는 함수)"

2. **원문 충실**: source_excerpt에 없는 정보를 지어내지 마십시오.
   배경 지식이 필요하면 children에 별도 개념으로 분리하십시오.

3. **자기충족 설명**: 설명은 다른 섹션을 참조하지 않고 독립적으로
   이해할 수 있어야 합니다.

4. **수식 보존**: 원문의 수식은 LaTeX 형식 그대로 유지하십시오.

5. **leaf 판정**: 이 개념이 목표 독자가 추가 설명 없이 바로 이해할 수
   있는 수준이면 is_leaf=true로 판정하십시오.

6. **children 생성**: is_leaf=false인 경우, 이 개념을 이해하기 위해
   필요한 선행 개념을 children에 나열하십시오.
   각 child는 name(개념명)과 brief(한 줄 설명)를 포함합니다.

반드시 지정된 JSON 형식으로만 응답하십시오.\
"""

_USER_PROMPT_TEMPLATE = """\
다음 개념에 대한 설명을 생성해 주세요.

## 개념 이름
{concept}

## 원문 (source_excerpt)
{source_excerpt}

## 현재 트리 깊이
{depth} (최대 {max_depth})

{children_instruction}

위 규칙에 따라 JSON으로 응답하세요.\
"""

_CHILDREN_INSTRUCTION_NEW = """\
## 하위 개념 생성
이 개념을 이해하기 위해 필요한 선행 개념이 있다면 children에 나열하세요.
목표 독자가 이미 알 것으로 기대되는 기초 개념은 제외하세요.
더 이상 분해가 필요 없으면 is_leaf=true, children=[]로 응답하세요.\
"""

_CHILDREN_INSTRUCTION_EXISTING = """\
## 하위 개념
이 개념의 하위 구조는 이미 정해져 있습니다. children=[]로 응답하세요.
explanation만 생성하면 됩니다.\
"""

_RETRY_SECTION = """\

## 이전 시도의 문제점
{error_list}

위 문제를 수정하여 다시 생성해 주세요.\
"""

_EXPAND_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "목표 독자 수준의 한국어 설명",
        },
        "is_leaf": {
            "type": "boolean",
            "description": "더 이상 분해 불필요 시 true",
        },
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "하위 개념 이름"},
                    "brief": {"type": "string", "description": "한 줄 설명"},
                },
                "required": ["name", "brief"],
            },
            "description": "이해에 필요한 선행 개념 리스트",
        },
    },
    "required": ["explanation", "is_leaf", "children"],
}

_EXPAND_SCHEMA_NO_CHILDREN = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "목표 독자 수준의 한국어 설명",
        },
        "is_leaf": {
            "type": "boolean",
            "description": "더 이상 분해 불필요 시 true",
        },
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "brief": {"type": "string"},
                },
                "required": ["name", "brief"],
            },
            "description": "이미 하위 구조가 있으므로 빈 배열로 응답",
        },
    },
    "required": ["explanation", "is_leaf", "children"],
}


class Expander:
    """트리 확장기.

    ConceptNode 트리를 DFS로 재귀 확장한다.
    각 pending 노드에 대해 Claude로 explanation + children을 생성하고,
    verifier로 검증하며, concept_cache로 중복을 차단한다.
    checkpoint 모듈은 import하지 않으며, on_node_done 콜백으로만 소통.
    """

    def __init__(
        self,
        client: ClaudeClient,
        verifier: Verifier,
        cache: ConceptCache,
        max_depth: int = 4,
        max_children_per_node: int = 5,
        max_retries: int = 1,
        on_node_done: Callable[[ConceptNode], None] | None = None,
    ):
        """트리 확장기를 초기화한다.

        Args:
            client: ClaudeClient 인스턴스.
            verifier: Verifier 인스턴스.
            cache: ConceptCache 인스턴스.
            max_depth: 최대 트리 깊이. 이 이상은 leaf로 강제.
            max_children_per_node: 새 자식 생성 시 최대 개수.
            max_retries: 검증 실패 시 재시도 횟수 (0이면 재시도 없음).
            on_node_done: 노드 확장 완료 시 호출되는 콜백.
        """
        self._client = client
        self._verifier = verifier
        self._cache = cache
        self._max_depth = max_depth
        self._max_children = max_children_per_node
        self._max_retries = max_retries
        self._on_node_done = on_node_done

    def expand(
        self, root: ConceptNode, ancestor_path: list[str] | None = None
    ) -> None:
        """root와 그 하위를 DFS로 재귀 확장한다. 트리를 in-place 수정.

        Args:
            root: 확장할 루트 노드.
            ancestor_path: 조상 concept 이름 리스트. 순환 감지용.
        """
        if ancestor_path is None:
            ancestor_path = []

        # 이미 처리된 노드 건너뜀 (체크포인트 재개)
        if root.status != "pending":
            # 기존 자식은 여전히 재귀 확장 필요
            child_path = ancestor_path + [root.concept]
            for child in root.children:
                self.expand(child, child_path)
            return

        # === 가드 체크 ===

        # 1. 깊이 초과 → leaf로 강제
        if root.depth >= self._max_depth:
            root.is_leaf = True
            root.status = "done"
            self._notify(root)
            return

        # 2. 조상 경로 순환 체크
        if self._cache.check_ancestor_cycle(root.concept, ancestor_path):
            root.status = "duplicate"
            root.duplicate_of = "ancestor-cycle"
            self._notify(root)
            return

        # 3. 캐시 중복 체크 (해시 + 임베딩)
        dup_id = self._cache.lookup(
            root.concept, brief=root.source_excerpt[:200]
        )
        if dup_id is not None:
            root.status = "duplicate"
            root.duplicate_of = dup_id
            self._notify(root)
            return

        # === Claude 호출 + 검증 루프 ===
        has_existing_children = len(root.children) > 0
        allow_new_children = not has_existing_children
        existing_children = list(root.children) if has_existing_children else []

        previous_errors: list[dict] | None = None

        try:
            for attempt in range(self._max_retries + 1):
                # 재시도 시 상태 초기화
                root.explanation = ""
                root.verification = {}
                if allow_new_children:
                    root.children = []
                else:
                    root.children = list(existing_children)

                # Claude 호출
                result = self._call_expand(root, allow_new_children, previous_errors)
                root.explanation = result.get("explanation", "")

                if result.get("is_leaf", False):
                    root.is_leaf = True

                # 새 자식 생성 (chunker 기존 자식이 없을 때만)
                if allow_new_children and not root.is_leaf:
                    new_children = result.get("children", [])[
                        : self._max_children
                    ]
                    for child_data in new_children:
                        child = ConceptNode(
                            concept=child_data.get("name", ""),
                            source_excerpt=child_data.get("brief", ""),
                            depth=root.depth + 1,
                            parent_id=root.id,
                        )
                        root.children.append(child)

                # 검증
                verify_result = self._verifier.verify(root)
                root.verification = verify_result

                if verify_result.get("passed_final", False):
                    root.status = "done"
                    break
                else:
                    previous_errors = verify_result.get("errors", [])
            else:
                # max_retries 소진
                root.status = "verification_failed"
                root.failed_errors = previous_errors

        except RateLimitExceeded:
            raise  # 상위로 전파

        except Exception as e:
            root.status = "failed"
            root.failed_errors = [
                {"category": "runtime", "description": str(e)}
            ]
            self._notify(root)
            return  # 자식 확장 중단

        # === 캐시 등록 ===
        self._cache.add(root.id, root.concept, brief=root.source_excerpt[:200])

        # === 콜백 ===
        self._notify(root)

        # === 자식 재귀 확장 ===
        # verification_failed도 자식 확장 진행 (duplicate/failed만 중단)
        child_path = ancestor_path + [root.concept]
        for child in root.children:
            self.expand(child, child_path)

    def _call_expand(
        self,
        node: ConceptNode,
        allow_new_children: bool,
        previous_errors: list[dict] | None = None,
    ) -> dict:
        """Claude를 호출하여 explanation과 children을 생성한다."""
        children_instruction = (
            _CHILDREN_INSTRUCTION_NEW
            if allow_new_children
            else _CHILDREN_INSTRUCTION_EXISTING
        )

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            concept=node.concept,
            source_excerpt=node.source_excerpt,
            depth=node.depth,
            max_depth=self._max_depth,
            children_instruction=children_instruction,
        )

        # 재시도 시 이전 에러 추가
        if previous_errors:
            error_lines = []
            for err in previous_errors:
                cat = err.get("category", "unknown")
                desc = err.get("description", "")
                error_lines.append(f"- [{cat}] {desc}")
            error_list = "\n".join(error_lines)
            user_prompt += _RETRY_SECTION.format(error_list=error_list)

        schema = (
            _EXPAND_SCHEMA if allow_new_children else _EXPAND_SCHEMA_NO_CHILDREN
        )

        return self._client.call(
            user_prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            json_schema=schema,
        )

    def _notify(self, node: ConceptNode) -> None:
        """콜백을 호출한다."""
        if self._on_node_done is not None:
            self._on_node_done(node)
