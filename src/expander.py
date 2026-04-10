# 단일 책임: ConceptNode 트리를 DFS로 재귀 확장한다. Claude로 explanation + children을 생성하고, verifier로 검증하며, concept_cache로 중복을 차단한다.
from __future__ import annotations

from typing import Callable

from src.claude_client import ClaudeClient, RateLimitExceeded
from src.concept_cache import ConceptCache
from src.tree import ConceptNode
from src.verifier import Verifier

_SYSTEM_PROMPT = """\
당신은 AI 논문을 학부 1학년에게 해설하는 전문가입니다.
독자: 고등학교 수학 2, 물리 1, 기초 프로그래밍 이수자.

## 해설 원칙

1. **저자 관점**: "저자는 ~를 주장한다", "저자는 ~를 선택했다" 형식. 일반 교과서 설명 금지.

2. **흐름 우선**: 기초 개념은 본문에 한 줄 괄호 + [[REF:topic_id]] 플레이스홀더만. 깊은 설명 금지 (Part 3 가 처리). topic_id 는 소문자+언더스코어.

3. **트리 구조**:
   - depth=0 (섹션 루트): 2~5 개 자식 필수 (Abstract, Intro, Method 등)
   - depth=1: 자식 0~3 개 (단순하면 leaf)
   - depth=2 이상: leaf 강제, children=[]
   - 각 노드 본문은 굵은글씨 단락으로 세부 논점 전개 가능
   - 과도 교정 금지: "얕게 유지" ≠ "자식 없음"

4. **실험 섹션**: Training/Results/Experiments 는 자세히. 하이퍼파라미터 이유, 실험 설계 의도, Table/Figure 수치 해석.

5. **모든 섹션 해설 필수**: Abstract 도 Part 1 과 별개로 Part 2 에 해설. 저자가 그 섹션을 어떻게 썼는지 분석. 최소 3 문단.

6. **한국어**: 모든 설명 한국어, 영어 원문 병기 허용.

7. **구체성**: 모호한 수사 금지. 구체적 용어와 수치 사용.

## 절대 금지

- 원문에 없는 사실 날조
- depth=0 섹션이 children=[] 로 끝남 (1~2 문장 극히 짧은 섹션 제외)
- 본문에 기초 개념 깊게 설명
- prerequisites 는 최대 3 개, 논문 고유 명칭 제외

JSON schema 로만 응답.\
"""

_USER_PROMPT_TEMPLATE = """\
다음 논문 섹션에 대한 해설을 생성해 주세요.

## 섹션 이름
{concept}

## 원문 (source_excerpt)
{source_excerpt}

## 현재 트리 깊이
{depth} (최대 {max_depth})

{children_instruction}

위 규칙에 따라 JSON으로 응답하세요.\
"""

_CHILDREN_INSTRUCTION_NEW = """\
## 하위 논점 생성
이 섹션에서 저자가 다루는 하위 논점들을 2~5개 나열하세요.
각 논점은 저자의 한 주장이나 설명 단위에 대응합니다.
더 이상 분해가 필요 없는 단순한 서술이면 is_leaf=true, children=[]로 응답하세요.\
"""

_CHILDREN_INSTRUCTION_EXISTING = """\
## 하위 논점
이 섹션의 하위 구조는 이미 정해져 있습니다. children=[]로 응답하세요.
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
            "description": "top-down 저자 관점 해설 (한국어). 기초 개념은 [[REF:topic_id]] 로.",
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
                    "concept": {"type": "string", "description": "하위 논점 이름 (짧은 한국어 명사구)"},
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
    "required": ["explanation", "is_leaf", "children", "prerequisites"],
}

_EXPAND_SCHEMA_NO_CHILDREN = {
    "type": "object",
    "properties": {
        "explanation": {
            "type": "string",
            "description": "top-down 저자 관점 해설 (한국어). 기초 개념은 [[REF:topic_id]] 로.",
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
                    "concept": {"type": "string"},
                    "brief": {"type": "string"},
                },
                "required": ["concept", "brief"],
            },
            "description": "이미 하위 구조가 있으므로 빈 배열로 응답",
        },
        "prerequisites": {
            "type": "array",
            "items": {"type": "string"},
            "description": "explanation 에 등장한 기초 개념 topic_id 리스트 (소문자+언더스코어)",
        },
    },
    "required": ["explanation", "is_leaf", "children", "prerequisites"],
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
        use_cache: bool = True,
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
            use_cache: 캐시 중복 체크 사용 여부. Phase 3 Part 2에서는 False.
        """
        self._client = client
        self._verifier = verifier
        self._cache = cache
        self._max_depth = max_depth
        self._max_children = max_children_per_node
        self._max_retries = max_retries
        self._on_node_done = on_node_done
        self._use_cache = use_cache

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

        # 1. 깊이 초과 → leaf로 강제하되 explanation은 생성
        force_leaf = root.depth >= self._max_depth

        # 2. 조상 경로 순환 체크
        if self._use_cache and self._cache.check_ancestor_cycle(root.concept, ancestor_path):
            root.status = "duplicate"
            root.duplicate_of = "ancestor-cycle"
            self._notify(root)
            return

        # 3. 캐시 중복 체크 (해시 + 임베딩)
        if self._use_cache:
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
        if force_leaf:
            allow_new_children = False
            root.is_leaf = True
        else:
            allow_new_children = not has_existing_children
        existing_children = (
            list(root.children) if has_existing_children and not force_leaf else []
        )

        previous_errors: list[dict] | None = None

        try:
            for attempt in range(self._max_retries + 1):
                # 재시도 시 상태 초기화
                root.explanation = ""
                root.verification = {}
                root.prerequisites = []
                if allow_new_children:
                    root.children = []
                else:
                    root.children = list(existing_children)

                # Claude 호출
                result = self._call_expand(root, allow_new_children, previous_errors)
                explanation = result.get("explanation", "").strip()

                # 빈 explanation 방어
                if not explanation:
                    raise ValueError(
                        f"expander: empty explanation for '{root.concept}' "
                        f"(depth={root.depth})"
                    )

                root.explanation = explanation
                root.prerequisites = result.get("prerequisites", [])

                if result.get("is_leaf", False):
                    root.is_leaf = True

                # 새 자식 생성 (chunker 기존 자식이 없을 때만)
                if allow_new_children and not root.is_leaf:
                    new_children = result.get("children", [])[
                        : self._max_children
                    ]
                    for child_data in new_children:
                        child = ConceptNode(
                            concept=child_data.get("concept", ""),
                            source_excerpt=child_data.get("brief", ""),
                            depth=root.depth + 1,
                            parent_id=root.id,
                            part=2,
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
        if self._use_cache:
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
