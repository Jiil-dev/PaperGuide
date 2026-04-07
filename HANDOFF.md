# Paper Analyzer — 작업 인계 문서

## 1. 프로젝트 현재 상태

- **Phase**: Phase 2 진입 직후 (설정 파일 단계)
- **완료**: 
  - `CLAUDE.md` 작성 (출력 포맷 섹션 포함)
  - `requirements.txt` 생성 (7개 패키지)
  - Python/venv/pip 환경 준비 (WSL Ubuntu)
- **미완료**:
  - `.venv` 재생성 여부 확인 필요
  - `pip install -r requirements.txt` 실행 및 검증
  - `.gitignore` 생성
  - `config.yaml` 생성
  - `src/` 하위 코드 파일 전체 (아직 한 개도 없음)

## 2. 환경 정보

- WSL Ubuntu
- 프로젝트 경로: `~/j0061/paper-analyzer` (공백 없음)
- Python 3.10+ (`python-is-python3` 설치 완료)
- Claude Code CLI: WSL 측에 설치되어 `claude --version` 동작 확인

## 3. 확정된 핵심 설계 결정 (절대 뒤집지 말 것)

### 3-1. 8가지 설계 보정 (전부 합의 완료)

1. **claude_client.py 시그니처 확장**: `call(user_prompt, system_prompt, json_schema, ...)` 형태. `system_prompt` 필수 인자. `max_total_calls` 상한, `get_stats()` 메서드 포함.

2. **3가지 모드 지원**: `ClaudeClient(mode="live"|"cache"|"dry_run")`. 
   - `live`: 실제 `claude -p` 호출
   - `cache`: 해시 기반 디스크 캐시 (`data/cache/claude_responses/<hash>.json`)
   - `dry_run`: 스키마 기본값으로 가짜 응답
   - 기본값은 `cache` (개발용), config.yaml의 `claude.mode`로 제어

3. **verifier → expander 피드백 경로**: `expand_node(..., previous_errors: list[dict] | None = None)`. previous_errors가 있으면 "이전 답변의 오류: ... 수정해서 다시 작성하라"를 프롬프트 앞에 주입. 재생성 루프는 expander 내부에서 `verification.max_retries`회. 실패 시 노드에 `status="verification_failed"` 마킹 후 탐색 계속.

4. **concept_cache.py 인터페이스**: 외부 메서드는 `lookup(concept_name, brief)`, `add(node_id, concept_name, brief)`, `check_ancestor_cycle(concept_name, ancestor_path)` 세 개만. 임베딩 계산은 내부에서만. 외부가 embedding_vec을 넘기는 설계 금지.

5. **chunker.py가 ConceptNode 직접 반환**: `split_into_sections(markdown) -> list[ConceptNode]`. Section dict 중간 타입 만들지 말 것.

6. **expander의 checkpoint 의존 제거**: 
   - expander.py는 checkpoint 모듈을 절대 import하지 않는다.
   - `expand_tree(..., on_node_done: Callable[[ConceptNode], None] | None = None)` 콜백만 받는다.
   - 매 노드 확장(중복/실패 포함)이 끝날 때마다 `on_node_done(node)` 호출.
   - 체크포인트 저장은 전적으로 main.py의 책임. main.py가 `lambda n: checkpoint.save(root, ...)` 형태로 콜백 주입.

7. **validate_no_anthropic_usage()**: main.py 시작 시 src/ 전체를 검사. `import anthropic`, `ANTHROPIC_API_KEY`, `api.anthropic.com` 등의 패턴이 있으면 즉시 중단. CLAUDE.md 절대 규칙의 코드 안전핀.

8. **assembler의 중복/실패 노드 렌더링**:
   - `status == "duplicate"` 또는 `duplicate_of`가 설정된 노드: 본문 다시 쓰지 않고 `→ §<duplicate_of_id> "<원본 개념명>" 참조` 한 줄만.
   - `status == "verification_failed"`: 설명 앞에 `> ⚠ 검증 실패 — 원문 대조 필요` 인용 블록 삽입.

### 3-2. 캐시 해시 정책 (claude_client.py)

- 해시 알고리즘: **SHA-256** (MD5 금지)
- 해시 입력 = 아래 4개의 연결:
  1. `system_prompt` 전문
  2. `user_prompt` 전문
  3. `json.dumps(json_schema, sort_keys=True)`
  4. `CLAUDE_CLIENT_VERSION = "1"` (클라이언트 상수, 프롬프트 템플릿/스키마 수정 시 +1로 캐시 일괄 무효화)
- 캐시 경로: `data/cache/claude_responses/<sha256>.json`
- 손상된 캐시 파일(json.loads 실패)은 조용히 무시하고 live 폴백

### 3-3. 출력 포맷 결정

- **최종 산출물은 Markdown(.md)만 생성**
- PDF/HTML/EPUB 변환은 본 프로젝트 범위 밖
- assembler.py에 pandoc, weasyprint, reportlab 등 PDF 관련 코드 금지
- 향후 PDF 필요하면 별도 스크립트(`scripts/md_to_pdf.sh`)로 분리

### 3-4. 목표 독자 수준

- 학부 1학년
- 배경지식: 고등학교 수학2(미적분 기초), 고등학교 물리1, 기초 프로그래밍
- 선형대수/확률/머신러닝/딥러닝 전혀 모름
- 이 기준을 expander의 시스템 프롬프트와 leaf 판정 규칙에 반영

### 3-5. 입력 파서 전략

입력 파서는 두 가지 모듈로 분리된다:

**(1) pdf_parser.py** — 일반 PDF 입력 처리
- 사용 라이브러리: `pymupdf4llm`
- 용도: 수식이 적은 텍스트 중심 논문, 블로그, 리포트
- 한계: 수식이 PDF 내부에서 이미지/벡터 그래픽으로 렌더링된 경우,
  `**==> picture [W x H] intentionally omitted <==**` placeholder로 누락됨
- 2026-04-08 distillation.pdf (9페이지, 수식 거의 없음)에서 정상 동작 확인
- 2026-04-08 attention.pdf (15페이지, 수식 밀집)에서 핵심 수식 누락 확인

**(2) arxiv_parser.py** — arXiv TeX 소스 입력 처리 (미구현)
- 사용: 표준 라이브러리 (정규식 기반)
- 용도: arXiv에 올라온 AI 논문 (주 입력 경로)
- 입력: 디렉터리 경로 (압축 해제된 .tex 파일 모음)
- 수식 보존: LaTeX 원본 그대로 유지 (완벽)
- 2026-04-08 Attention Is All You Need (arXiv 1706.03762) 소스로 검증:
  `\mathrm{Attention}(Q,K,V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V` 확인

**입력 형식 판정 (main.py가 수행):**
- 경로가 `.pdf`로 끝나면 → pdf_parser 호출
- 경로가 디렉터리이면 → arxiv_parser 호출

**테스트 데이터 위치 (git 추적 안 됨):**
- `data/papers/distillation.pdf` — pdf_parser 테스트용
- `data/papers/attention/` — arxiv_parser 테스트용 (arXiv 1706.03762 TeX 소스)
- 다른 머신에서 재현 시 이 두 파일을 수동으로 받아서 같은 위치에 배치.

## 4. 모듈 설계 요약 (각 파일의 책임)

- `config.py`: YAML 로드, Pydantic v2 검증, 경로 자동 생성
- `pdf_parser.py`: PDF → 수식 포함 Markdown (pymupdf4llm)
- `chunker.py`: Markdown → ConceptNode 리스트 (헤더 기반)
- `tree.py`: ConceptNode 데이터클래스 (concept, source_excerpt, explanation, is_leaf, depth, parent_id, children, status, duplicate_of, failed_errors, verification)
- `concept_cache.py`: 3단계 중복 차단 (해시 → 임베딩 유사도 ≥0.88 → 조상 경로 순환)
- `claude_client.py`: subprocess로 `claude -p` 호출, 3모드 지원, JSON schema 강제, tenacity 재시도, 호출 상한
- `expander.py`: DFS 재귀 확장, on_node_done 콜백, previous_errors 피드백 루프
- `verifier.py`: 별도 Claude 호출로 hallucination/omission/contradiction/math_error 검출
- `checkpoint.py`: 트리 JSON 직렬화/역직렬화 (main에서만 호출)
- `assembler.py`: DFS 순회로 Markdown 책 생성, 중복/실패 노드 특별 렌더링
- `main.py`: argparse, 체크포인트 재개 분기, validate_no_anthropic_usage, expander에 콜백 주입

## 5. 다음 세션이 가장 먼저 해야 할 일

1. 현재 `.venv` 상태 확인 (`ls -la .venv`)
2. 필요하면 `.venv` 재생성: `rm -rf .venv && python -m venv .venv && source .venv/bin/activate`
3. `pip install --upgrade pip setuptools wheel`
4. `pip install -r requirements.txt`
5. 설치 검증: `pip list | grep -iE "pymupdf|sentence-transformers|numpy|pyyaml|tenacity|rich|pydantic|torch"`
6. 설치 성공하면 `.gitignore` 생성 단계로 진입

## 6. 절대 하지 말 것 (Claude가 자의적으로 저지르기 쉬운 실수)

- `anthropic` Python SDK import, API 키 사용, `api.anthropic.com` 호출 → **전부 금지**, CLAUDE.md 참조
- 설계 합의 없이 파일 여러 개 동시 생성
- 테스트 프레임워크(pytest 등) 추가
- Docker/CI/README 생성 (README는 맨 마지막)
- PDF 변환 코드(pandoc, weasyprint 등) 추가
- 한 파일을 작성한 뒤 "다음 파일도 바로 만들겠다"며 허락 없이 이어가기

## 7. 작업 규칙 (CLAUDE.md에서 재확인)

- 새 파일 만들기 전에 책임과 인터페이스를 한국어로 요약해서 사용자에게 OK 받기
- 코드 작성 직후 `python -c "import src.<모듈>"` import 테스트
- 외부 호출(claude -p, 모델 다운로드) 필요하면 사용자에게 먼저 묻기
- 의미 있는 단위 끝날 때마다 git commit 제안
- 모르는 건 추측하지 말고 물어보기