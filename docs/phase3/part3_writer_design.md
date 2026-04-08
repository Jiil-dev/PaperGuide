# part3_writer.py 설계

## 단일 책임
`PrerequisiteTopic` 하나를 받아 해당 주제의 탄탄한 Part 3 항목
(`PrerequisiteEntry`) 을 생성한다.

## 공개 API

```python
def write_part3_topic(
    topic: PrerequisiteTopic,
    section_number: str,
    client: ClaudeClient,
) -> PrerequisiteEntry:
```

## Claude 호출
주제당 1회. 주제 설명 + 하위 섹션 구조 생성.

## 프롬프트 원칙
- 독립적으로 읽을 수 있는 단위
- 얕지 않게: 학부 1학년이 이 논문 이해에 필요한 만큼
- 한 학기 교재 분량은 과함
- 정의 → 직관 → 원리 → 예시 → 논문과의 연결 순

## JSON 스키마
- title
- intro (짧은 도입)
- subsections: [{concept, explanation}]  — 4~8 개
- connection_to_paper: 논문과 어떻게 연결되는지
