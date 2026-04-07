# main.py 구현 결과

## 1. 작성된 코드

src/main.py — 165줄. `cat src/main.py`로 원본 확인 가능.

## 2. 문법 검사

```
$ .venv/bin/python -c "import ast; ast.parse(open('src/main.py').read()); print('syntax OK')"
syntax OK
```

## 3. validate_no_anthropic_usage() 단독 테스트

```
$ .venv/bin/python -c "from src.main import validate_no_anthropic_usage; validate_no_anthropic_usage(); print('validate OK')"
validate OK
```

src/ 내 전체 .py 파일 스캔 통과. 금지된 import 없음.

## 4. import 테스트

```
$ .venv/bin/python -c "from src.main import main; print('import OK')"
import OK
```

## 5. CLI help 출력

```
$ .venv/bin/python -m src.main --help
usage: main.py [-h] [--config CONFIG] [--mode {live,cache,dry_run}] [--resume]
               [--input INPUT]

AI 논문 PDF/TeX를 학부 1학년용 가이드북으로 변환

options:
  -h, --help            show this help message and exit
  --config CONFIG       설정 파일 경로 (기본: config.yaml)
  --mode {live,cache,dry_run}
                        Claude 모드 오버라이드 (config.yaml 값 대신 사용)
  --resume              체크포인트에서 재개
  --input INPUT         입력 경로 (PDF 파일 또는 TeX 디렉터리)
```

한국어 description 정상 출력.

## 6. dry_run 전체 파이프라인 테스트

### 실행 명령

```bash
.venv/bin/python -m src.main --mode dry_run --input data/papers/attention
```

### 콘솔 출력

```
Paper Analyzer — mode=dry_run
입력: /home/engineer/j0061/paper-analyzer/data/papers/attention
제목: Attention Is All You Need, 길이: 41402자
루트 섹션: 9개
  [verification_failed] Abstract
  [verification_failed] Introduction
  [verification_failed] Background
  [verification_failed] Model Architecture
  [verification_failed] Encoder and Decoder Stacks
  [verification_failed] Attention
  [verification_failed] Scaled Dot-Product Attention
  [verification_failed] Multi-Head Attention
  [verification_failed] Applications of Attention in our Model
  [verification_failed] Position-wise Feed-Forward Networks
  [verification_failed] Embeddings and Softmax
  [verification_failed] Positional Encoding
  [verification_failed] Why Self-Attention
  [verification_failed] Training
  [verification_failed] Training Data and Batching
  [verification_failed] Hardware and Schedule
  [verification_failed] Optimizer
  [verification_failed] Regularization
  [verification_failed] Results
  [verification_failed] Machine Translation
  [verification_failed] Model Variations
  [verification_failed] English Constituency Parsing
  [verification_failed] Conclusion
  [verification_failed] Attention Visualizations
가이드북 생성 완료: data/output/Attention Is All You Need_해설.md
통계: {'total_calls': 0, 'cache_hits': 0, 'cache_misses': 0, 'dry_run_calls': 96}
```

### 생성된 파일

| 파일 | 크기 | 경로 |
|------|------|------|
| 가이드북 | 3,754자 | `data/output/Attention Is All You Need_해설.md` |
| 체크포인트 | 54,430 bytes | `checkpoints/latest.json` |

### 가이드북 첫 60줄

```markdown
# Attention Is All You Need 해설

생성 일시: 2026-04-08 07:01

---

## 목차

- [1. Abstract](#1-abstract)
- [2. Introduction](#2-introduction)
- [3. Background](#3-background)
- [4. Model Architecture](#4-model-architecture)
  - [4.1. Encoder and Decoder Stacks](#41-encoder-and-decoder-stacks)
  - [4.2. Attention](#42-attention)
    - [4.2.1. Scaled Dot-Product Attention](#421-scaled-dot-product-attention)
    - [4.2.2. Multi-Head Attention](#422-multi-head-attention)
    - [4.2.3. Applications of Attention in our Model](#423-applications-of-attention-in-our-model)
  - [4.3. Position-wise Feed-Forward Networks](#43-position-wise-feed-forward-networks)
  - [4.4. Embeddings and Softmax](#44-embeddings-and-softmax)
  - [4.5. Positional Encoding](#45-positional-encoding)
- [5. Why Self-Attention](#5-why-self-attention)
- [6. Training](#6-training)
  - [6.1. Training Data and Batching](#61-training-data-and-batching)
  - [6.2. Hardware and Schedule](#62-hardware-and-schedule)
  - [6.3. Optimizer](#63-optimizer)
  - [6.4. Regularization](#64-regularization)
- [7. Results](#7-results)
  - [7.1. Machine Translation](#71-machine-translation)
  - [7.2. Model Variations](#72-model-variations)
  - [7.3. English Constituency Parsing](#73-english-constituency-parsing)
- [8. Conclusion](#8-conclusion)
- [9. Attention Visualizations](#9-attention-visualizations)

---

## 1. Abstract

> [검증 실패] 다음 항목이 확인되지 않았습니다:

...
```

### 검증 항목

| 항목 | 결과 | 판정 |
|------|------|------|
| arxiv_parser 파싱 성공 | 제목 "Attention Is All You Need", 41402자 | OK |
| chunker 루트 9개 | Abstract~Attention Visualizations | OK |
| 모든 노드 verification_failed | 24/24 (dry_run) | OK (의도된 동작) |
| 체크포인트 저장 | checkpoints/latest.json 54KB | OK |
| 가이드북 생성 | data/output/...해설.md 3.7KB | OK |
| 목차 구조 | 9개 루트 + 하위 섹션 계층적 | OK |
| dry_run_calls | 96 (24노드 × expand 2회 + verify 2회) | OK |
| total_calls (live) | 0 | OK (dry_run이므로) |
| exit code | 0 (정상) | OK |

## 7. 구현 중 주의했던 점

1. **validate_no_anthropic_usage 정규식 기반**: `re.compile(r"^\s*import\s+anthropic(\s|$|\.)") ` 등으로 실제 import 문만 검사. 주석, docstring, 문자열 리터럴은 무시.

2. **--input 경로 resolve()**: `Path(args.input).resolve()`로 절대경로 변환. config의 경로와 일관성 유지.

3. **save_callback 클로저**: `roots`와 `cp_path`를 클로저로 캡처. expander의 on_node_done에 주입.

4. **RateLimitExceeded 처리**: 체크포인트 저장 → 에러 메시지 → sys.exit(1). --resume으로 재개 가능.

5. **config 필드명 100% 일치**: config.py의 실제 필드명(pdf_input, cache_dir, output_dir, checkpoints_dir, cli_path, mode, max_total_calls 등)과 main.py의 참조가 정확히 일치함을 확인.

## 8. cache/live 테스트 (사용자 허락 후 추가 예정)

사용자 허락 후 실행 예정.
