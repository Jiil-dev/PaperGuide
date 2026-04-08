# expander.py Phase 3 재작성 설계

## Phase 2 와의 차이

### Phase 2 (bottom-up)
섹션을 받으면 "이해에 필요한 선행 개념" 을 자식으로 생성.
예: Abstract → 자식 [신경망 기초, RNN 이해, Attention 개념]

### Phase 3 (top-down)
섹션을 받으면 "논문 저자가 이 섹션에서 다루는 하위 논점" 을 자식으로 생성.
예: Abstract → 자식 [제안하는 구조 요약, 기존 한계, 실험 결과 요약]

## 공개 API
기존 API 유지. 내부 프롬프트 전면 재작성.

## 시스템 프롬프트 원칙 (HANDOFF §1.2 반영)

### 원칙 1 — top-down: 저자 관점
"저자는 여기서 ~를 말한다" 형식. 일반 교과서 설명 금지.
paper_analyzer.py 의 시스템 프롬프트와 같은 스타일.

### 원칙 2 — 흐름 우선: 기초 지식 위임
기초 개념은 본문에 한 줄 괄호 병기 또는 [[REF:topic_id]] 플레이스홀더로만 등장.
여러 문단에 걸친 기초 지식 설명 금지.

### 원칙 3 — 하위 논점 분해
각 섹션을 "저자가 이 섹션에서 주장하는 하위 논점들" 로 분해.
논점마다 자식 노드 생성.

### 원칙 4 — 실험 섹션은 자세히
Training, Results 같은 실험 섹션은 하이퍼파라미터 선택 이유, 실험 결과 해석까지 자세히.

## JSON 스키마

각 노드는 다음 필드를 생성:
- concept: 이 노드의 주제 (짧은 명사구)
- explanation: 한국어 해설 (top-down, 저자 관점)
- children: 하위 논점 리스트 (재귀)
- prerequisites: 이 해설에 등장하는 기초 개념 topic_id 리스트

## 하위 논점 생성 기준
- 섹션 내용을 2~5개의 하위 논점으로 분해
- 각 논점은 저자의 한 주장에 대응
- depth 가 깊어질수록 더 구체적으로
- max_depth (config.part2.max_depth=4) 도달하면 자식 생성 중단

## 플레이스홀더 규칙
기초 개념이 등장하면 [[REF:topic_id]] 를 explanation 에 삽입 + prerequisites 필드에 topic_id 추가.
topic_id 는 소문자 언더스코어 (예: vector_dot_product).
