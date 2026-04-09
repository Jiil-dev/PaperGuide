# 예시 가이드북

이 디렉터리에는 PaperGuide 가 생성한 예시 가이드북이 있습니다.

## attention_is_all_you_need_mini.md

**"Attention Is All You Need"** 논문 (Vaswani et al., 2017) 의 완전한 3-Part 가이드북입니다. Abstract 와 Introduction 섹션만 포함된 mini 버전에서 생성되었습니다.

**통계**:
- 약 2,000 줄의 한국어 해설
- 240 KB Markdown 파일
- 86 회 Claude Code 호출로 생성 (~96 분 소요)
- 최대 헤더 깊이: Level 5 (사양서가 아닌 책 스타일)

**주목할 점**:
- **Part 1** (1~36 줄): 논문의 큰 그림 요약
- **Part 2** (37~288 줄): 섹션별 저자 관점 해설
  - 저자의 단어 선택 (`complex`, `simple`, `solely`, `entirely`) 이 의도적인 수사적 장치로 분석되는 것에 주목
  - 순환 구조 제거의 트레이드오프 (예: 위치 인코딩이 필요해짐) 가 명시적으로 논의되는 것에 주목
- **Part 3** (289~1983 줄): 17 개 기초 주제의 독립적 깊이 있는 해설
  - RNN/LSTM/GRU, CNN 기초, 어텐션 역사, 인코더-디코더, 최적화 기법 등
  - 각 주제는 정의 → 직관 → 수학 → 숫자 예시 → 논문과의 연결 순으로 구성

이 샘플은 `--phase 3 --mode cache --cache-dir samples/_tmp_phase3/cache` 로 생성되었습니다.

## 직접 가이드북 생성하기

```bash
.venv/bin/python -m src.main \
    --input data/papers/your_paper \
    --output examples/your_paper_guidebook.md \
    --mode live \
    --cache-dir data/cache_your_paper \
    --phase 3
```

전체 사용법은 [메인 README](../README_KR.md) 를 참고하세요.
