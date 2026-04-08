# paper_analyzer.py 설계

## 단일 책임
논문 전체 Markdown을 받아 Part 1 생성용 PaperAnalysis 객체를 생성한다.

## 공개 API

```python
def analyze_paper(markdown: str, client: ClaudeClient) -> PaperAnalysis:
    """논문 Markdown 전체를 분석해 PaperAnalysis를 반환한다."""
```

## Claude 호출
1회 (긴 논문은 cache/truncation은 claude_client가 처리)

## 시스템 프롬프트 원칙 (HANDOFF §1.2 반영)
- 저자 관점 (top-down)
- 일반 교과서 설명 지양
- 학부 1학년 수준, 한국어
- 구체성 강조

## JSON 스키마
PaperAnalysis 의 모든 필드 + required 리스트.

## 에러 처리
- Claude 응답이 필수 필드 누락: ValueError raise
- title 이 빈 문자열: ValueError
