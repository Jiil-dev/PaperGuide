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


def _normalize_topic_id(topic_id: str) -> str:
    """topic_id 정규화: 명백한 중복 (단/복수, basics 접미사) 통일."""
    tid = topic_id.lower().strip()
    # 복수형 → 단수형 (단, ss 로 끝나는 건 제외: classes, basis 등)
    if tid.endswith("s") and not tid.endswith("ss") and len(tid) > 3:
        tid = tid[:-1]
    # _basics, _basic 접미사 제거
    for suffix in ["_basics", "_basic"]:
        if tid.endswith(suffix):
            tid = tid[: -len(suffix)]
            break
    return tid


def collect_prerequisites(
    part2_nodes: list[ConceptNode],
    predefined_pool: list,  # list[PrerequisitePoolItem] but avoid circular import
    allow_new: bool = True,
    max_topics: int = 15,
) -> list[PrerequisiteTopic]:
    """Part 2 트리에서 모든 기초 지식 주제를 수집하고 중복 제거한다.

    Args:
        part2_nodes: Part 2 루트 노드 리스트.
        predefined_pool: config.part3.predefined_pool (PrerequisitePoolItem 리스트).
        allow_new: 풀에 없는 topic_id도 허용할지.
        max_topics: 반환할 최대 주제 수. config.part3.max_topics.

    Returns:
        PrerequisiteTopic 리스트. 풀 순서 우선, 나머지는 알파벳 순. max_topics 이하.
    """
    # 풀을 정규화된 topic_id → title 맵으로 변환 + 순서 기억
    pool_map: dict[str, str] = {}
    pool_order: dict[str, int] = {}
    for idx, item in enumerate(predefined_pool):
        normalized_id = _normalize_topic_id(item.id)
        pool_map[normalized_id] = item.title
        pool_order[normalized_id] = idx

    # 수집용 딕셔너리: 정규화된 topic_id → {title, first_mention, all_mentions}
    collected: dict[str, dict] = {}

    for root in part2_nodes:
        for node in _walk(root):
            for raw_topic_id in node.prerequisites:
                topic_id = _normalize_topic_id(raw_topic_id)
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

    # 정렬: 풀 순서 우선, 나머지는 알파벳 순
    def _sort_key(t: PrerequisiteTopic):
        if t.topic_id in pool_order:
            return (0, pool_order[t.topic_id])
        else:
            return (1, t.topic_id)

    topics.sort(key=_sort_key)

    # max_topics 강제 적용 (predefined_pool 항목이 우선 보존됨)
    return topics[:max_topics]
