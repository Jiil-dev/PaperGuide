# ref_resolver.py 설계

## 단일 책임
Part 2 ConceptNode 트리의 explanation에 삽입된 `[[REF:topic_id]]` 플레이스홀더를
실제 Markdown 앵커 링크로 치환한다.

## 공개 API

```python
def resolve_refs(
    part2_nodes: list[ConceptNode],
    part3_entries: list[PrerequisiteEntry],
) -> list[ConceptNode]:
    """플레이스홀더를 앵커 링크로 치환한다. in-place 수정 + 반환."""
```

## 동작
1. part3_entries 에서 topic_id → (section_number, title) 맵 생성.
2. 모든 Part 2 노드를 DFS로 순회.
3. 각 노드 explanation 에서 정규식 `[[REF:([a-z_][a-z0-9_]*)]]` 매칭.
4. 매칭된 topic_id 가 맵에 있으면 `**[Part {section} {title}](#{anchor})**` 로 치환.
5. 맵에 없으면 `[[UNRESOLVED:topic_id]]` 로 남김.

## 의존성
- re (표준)
- src.tree.ConceptNode, iter_dfs
- src.data_types.PrerequisiteEntry

## 테스트
- 정상 치환, 미해결, 다중 플레이스홀더, 중첩 트리 4개 케이스
