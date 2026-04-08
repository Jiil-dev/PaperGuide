# prerequisite_collector.py 설계

## 단일 책임
Part 2 트리 전체를 순회하며 각 노드의 prerequisites 필드에 등록된 topic_id를
수집하고, config의 predefined_pool과 병합한 뒤, 실제로 등장한 topic만 중복 제거해서
반환한다.

## 공개 API

```python
def collect_prerequisites(
    part2_nodes: list[ConceptNode],
    predefined_pool: list[PrerequisitePoolItem],
    allow_new: bool = True,
) -> list[PrerequisiteTopic]:
```

## 동작
1. predefined_pool 을 topic_id → title 맵으로 변환.
2. Part 2 트리 DFS 순회하며 각 노드의 prerequisites 필드 수집.
3. 각 topic_id 마다 title 결정 (풀 우선, 없으면 자동 생성).
4. first_mention_in, all_mentions 계산.
5. 실제로 등장한 topic 만 반환.
6. 정렬: 풀 순서 우선, 나머지는 topic_id 알파벳 순.

## 의존성
- warnings (표준)
- src.tree.ConceptNode
- src.data_types.PrerequisiteTopic
