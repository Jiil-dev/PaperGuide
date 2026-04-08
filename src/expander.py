# 단일 책임: ConceptNode 트리를 DFS로 재귀 확장한다. Claude로 explanation + children을 생성하고, verifier로 검증하며, concept_cache로 중복을 차단한다.
from __future__ import annotations

from typing import Callable

from src.claude_client import ClaudeClient, RateLimitExceeded
from src.concept_cache import ConceptCache
from src.tree import ConceptNode
from src.verifier import Verifier

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

        # 1. 깊이 초과 → leaf로 강제하되 explanation은 생성
        force_leaf = root.depth >= self._max_depth

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
                root.explanation = result.get("explanation", "")
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
