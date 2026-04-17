# PaperGuide


PaperGuide 는 학술 AI 논문을 종합적인 한국어 해설서로 변환하는 Python 파이프라인입니다. 일반적인 논문 요약기와 달리, **저자의 관점**에서 설명하고, **읽기의 흐름**을 보존하며, 기초 지식을 얕은 인라인 정의가 아닌 **독립적인 깊이 있는 설명**으로 다룹니다.

**Claude Code 로 만들어졌고, Claude Code 로 작동합니다.** Anthropic API 키가 필요 없습니다 — 기존의 Claude Max/Pro 구독을 `claude` CLI 로 활용합니다.

---

## PaperGuide 의 차별점

대부분의 논문 요약 도구는 글머리 기호나 짧은 초록을 줍니다. PaperGuide 는 **책**을 씁니다. 구체적으로:

- **Top-down, 저자 중심**: 모든 섹션이 "저자가 여기서 무엇을 주장하는가" 의 관점에서 설명됩니다. 저자의 단어 선택, 수사적 구조, 논증 전략까지 분석합니다.
- **읽기 흐름 보존**: 기초 개념(RNN, softmax, 행렬 곱셈 등)은 본문에 직접 풀어쓰지 않고 별도의 Part 3 로 링크됩니다. 본문이 3 문단짜리 선행 지식 정의로 끊어지지 않습니다.
- **탄탄한 기초 지식**: Part 3 는 학부 1학년이 실제로 이해할 수 있을 만큼 각 주제를 충분히 깊게 다룹니다 — 한 줄 용어집이 아닙니다.
- **3-Part 구조**:
  - **Part 1 (10–15%)**: 큰 그림 — 논문이 무엇을 주장하는지, 왜 중요한지, 어떻게 읽을지.
  - **Part 2 (70–80%)**: 논문 섹션을 저자의 시각에서 따라 읽기.
  - **Part 3 (15–20%)**: Part 2 를 이해하는 데 필요한 모든 기초 개념의 독립적 설명.

## 예시 출력

"Attention Is All You Need" 논문(mini 버전, Abstract + Introduction)의 완전한 가이드북이 [`examples/`](examples/) 에 있습니다. 약 2,000 줄의 한국어 해설이며, 저자의 설계 결정과 수사 전략까지 상세히 분석되어 있습니다.

## 요구사항

- **Python 3.12+**
- **Claude Code CLI** (`claude` 명령어) 설치 및 인증 완료
  - Claude Max 또는 Claude Pro 구독 필요
  - 설치: [Claude Code 문서](https://docs.anthropic.com/en/docs/claude-code) 참고
  - 인증: `claude login`
- **Linux / macOS / WSL** (WSL Ubuntu 에서 테스트됨)

## 설치

```bash
# 1. 클론
git clone https://github.com/Jiil-dev/PaperGuide.git
cd PaperGuide

# 2. 가상환경 생성
python3.12 -m venv .venv
source .venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. Claude Code CLI 동작 확인
claude --version
```

## 빠른 시작

논문을 다음 형식 중 하나로 준비하세요:

- **디렉터리**: arXiv 소스 폴더 (`.tex` 파일들 포함, 예: `data/papers/your_paper/`)
- **PDF**: 단일 `.pdf` 파일
- **압축 파일**: `.tar.gz`, `.tgz`, `.tar`, `.zip` 파일 (예: arXiv 에서 받은 소스 압축) — 자동 해제됩니다

### 가장 간단한 사용법

`config.yaml` 의 기본값 (`cache` 모드, `data/cache` 디렉터리) 이 자동으로
사용됩니다. input, output, phase 만 지정하면 됩니다:

```bash
.venv/bin/python -m src.main \
    --input data/papers/your_paper.tar.gz \
    --output samples/your_paper_guidebook.md \
    --phase 3
```

### 기본값 덮어쓰기

논문마다 별도의 cache 디렉터리를 쓰고 싶으면 (권장) 명시적으로
`--cache-dir` 를 주세요:

```bash
.venv/bin/python -m src.main \
    --input data/papers/your_paper.tar.gz \
    --output samples/your_paper_guidebook.md \
    --cache-dir data/cache_your_paper \
    --phase 3
```

결과는 한국어로 작성된 완전한 3-Part 가이드북이 담긴 단일 Markdown 파일입니다.

### 모드

| 모드 | 설명 | 사용 시점 |
|------|------|-----------|
| `--mode live` | 실제 Claude Code 호출 | 운영 실행 |
| `--mode cache` | 디스크 캐시 우선 사용, 없으면 live 호출 | 재실행 시 (권장) |
| `--mode dry_run` | Claude 호출 없이 스키마 기본값 반환 | 개발용 |

### 논문마다 별도 `--cache-dir` 를 쓰는 이유

서로 다른 논문은 concept cache 를 공유하면 안 됩니다. 논문마다 고유한 cache 디렉터리를 사용해서 교차 오염을 막으세요.

## 출력 구조

생성되는 Markdown 의 구조는 다음과 같습니다:

```
# <논문 제목> — 완전판 가이드북

## Part 1. 논문이 무엇을 주장하는가 — 큰 그림
### 1.1 핵심 주장
### 1.2 해결하려는 문제
### 1.3 핵심 기여
### 1.4 주요 결과
### 1.5 이 논문의 의의
### 1.6 이 가이드북 읽는 법

## Part 2. 논문 따라 읽기 — 완전 해설
### 2.1 Abstract
    #### 2.1.1 ...
### 2.2 Introduction
    ...
(각 논문 섹션을 depth 2 까지 재귀적으로 확장)

## Part 3. 기초 지식 탄탄히
### 3.1 <기초 주제 1>
### 3.2 <기초 주제 2>
...
```

헤더는 Markdown Level 5 (`#####`) 까지로 제한되어, 사양서가 아닌 "책 읽는 경험" 을 보존합니다.

## 설정

`config.yaml` 을 편집하여 생성 파라미터를 조정할 수 있습니다:

```yaml
claude:
  default_mode: cache              # CLI --mode 미지정 시 사용
  default_cache_dir: data/cache    # CLI --cache-dir 미지정 시 사용
  max_total_calls: 1500            # 한 실행당 Claude 호출 상한
  sleep_between_calls: 3

part2:
  max_depth: 2          # Part 2 의 최대 중첩 깊이 (헤더 Level 3~5)
  max_children_per_node: 3

part3:
  max_topics: 15
  predefined_pool: [...]   # Claude 가 선택할 수 있는 일반 기초 주제 풀
  allow_claude_to_add: true

verification:
  min_confidence: 0.7    # 노드를 수락하는 최소 검증 신뢰도
  max_retries: 0
```

## 작동 방식

PaperGuide 는 7 단계 파이프라인입니다:

1. **파싱** — arXiv tex 소스 또는 PDF 에서 markdown 추출
2. **분석 (Part 1)** — 큰 그림 요약 생성
3. **분할** — 논문을 raw 섹션으로 분할
4. **확장 (Part 2)** — 각 섹션에 대해 top-down 해설을 재귀적으로 생성
5. **기초 지식 수집** — Part 2 에서 등장한 모든 `[[REF:topic_id]]` 플레이스홀더 수집
6. **Part 3 작성** — 각 기초 주제의 독립 해설 생성
7. **조립** — 최종 3-Part Markdown 렌더링, 모든 플레이스홀더 치환

모든 Claude 호출은 `claude_client.py` 를 통과하며, 로컬의 `claude -p` CLI 를 JSON 스키마 강제와 함께 호출합니다.

## 프로젝트 상태

- ✅ Phase 3 완성 (top-down, 흐름 보존, 3-Part 가이드북 생성)
- 🧪 "Attention Is All You Need" mini 논문 (Abstract + Introduction) 으로 테스트 완료
- 📋 향후 작업: 전체 논문 테스트, 다중 논문 배치 모드, 사용자 정의 기초 주제 풀

## 문서

- English README: [README.md](README.md)
- 개발 문서 (설계 결정, 반복 이력): [docs/development/](docs/development/)

## 라이선스

MIT — [LICENSE](LICENSE) 참고

## 감사의 말

[Claude Code](https://claude.ai/code) 로 제작되었습니다. 아키텍처 설계부터 디버깅까지 전 개발 과정이 Claude 와의 협업으로 이루어졌습니다.
