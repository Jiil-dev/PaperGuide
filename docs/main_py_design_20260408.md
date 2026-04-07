# src/main.py 설계

## 1. 모듈 책임 (한 줄)

**CLI 진입점. config → 입력 파싱 → chunking → expanding → assembling 전체 파이프라인 오케스트레이션. 체크포인트 자동 저장/재개. validate_no_anthropic_usage() 정적 검사.**

---

## 2. CLI 인터페이스 (argparse)

```bash
python -m src.main [--config CONFIG] [--mode MODE] [--resume] [--input INPUT]
```

| 인자 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--config` | str | `"config.yaml"` | config 파일 경로 |
| `--mode` | str | None (config에서) | `live` / `cache` / `dry_run`. config.yaml의 `claude.mode`를 오버라이드 |
| `--resume` | flag | False | 체크포인트에서 재개 |
| `--input` | str | None (config에서) | 입력 경로 (PDF 파일 또는 TeX 디렉터리). config.yaml의 `paths.pdf_input`을 오버라이드 |

```python
def _parse_args():
    parser = argparse.ArgumentParser(
        description="AI 논문 PDF/TeX를 학부 1학년용 가이드북으로 변환"
    )
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    parser.add_argument("--mode", choices=["live", "cache", "dry_run"], help="Claude 모드 오버라이드")
    parser.add_argument("--resume", action="store_true", help="체크포인트에서 재개")
    parser.add_argument("--input", help="입력 경로 (PDF 또는 TeX 디렉터리)")
    return parser.parse_args()
```

---

## 3. main() 전체 흐름

```python
def main():
    # 0. 금지 import 검사
    validate_no_anthropic_usage()

    # 1. CLI 인자 파싱
    args = _parse_args()

    # 2. config 로드 + CLI 오버라이드
    config = load_config(args.config)
    mode = args.mode or config.claude.mode
    input_path = Path(args.input) if args.input else config.paths.pdf_input

    # 3. rich 콘솔 초기화
    console = Console()
    console.print(f"[bold]Paper Analyzer[/bold] — mode={mode}")

    # 4. 입력 파싱
    console.print(f"입력: {input_path}")
    if input_path.is_dir():
        parse_result = parse_arxiv(input_path)
    elif input_path.suffix.lower() == ".pdf":
        parse_result = parse_pdf(input_path)
    else:
        console.print(f"[red]지원하지 않는 입력 형식: {input_path}[/red]")
        sys.exit(1)
    console.print(f"제목: {parse_result.title}, 길이: {len(parse_result.markdown)}자")

    # 5. chunking
    roots = split_into_sections(parse_result.markdown)
    console.print(f"루트 섹션: {len(roots)}개")

    # 6. 체크포인트 확인
    cp_path = config.paths.checkpoints_dir / "latest.json"
    if args.resume and checkpoint.exists(cp_path):
        roots = checkpoint.load(cp_path)
        console.print(f"[yellow]체크포인트에서 재개: {cp_path}[/yellow]")

    # 7. 의존성 조립
    client = ClaudeClient(
        mode=mode,
        cli_path=config.claude.cli_path,
        max_total_calls=config.claude.max_total_calls,
        timeout_seconds=config.claude.timeout_seconds,
        sleep_between_calls=config.claude.sleep_between_calls,
        cache_dir=config.paths.cache_dir,
    )
    concept_cache = ConceptCache(
        cache_dir=config.paths.cache_dir / "concept_cache",
        model_name=config.dedup.embedding_model,
        threshold=config.dedup.similarity_threshold,
    )
    verifier = Verifier(
        client=client,
        min_confidence=config.verification.min_confidence,
    )

    def save_callback(node):
        checkpoint.save(roots, cp_path)
        console.print(f"  [{node.status}] {node.concept}")

    expander = Expander(
        client=client,
        verifier=verifier,
        cache=concept_cache,
        max_depth=config.expansion.max_depth,
        max_children_per_node=config.expansion.max_children_per_node,
        max_retries=config.verification.max_retries,
        on_node_done=save_callback,
    )

    # 8. 확장
    try:
        for root in roots:
            expander.expand(root)
    except RateLimitExceeded as e:
        checkpoint.save(roots, cp_path)
        console.print(f"[red]할당량 초과: {e}[/red]")
        console.print(f"체크포인트 저장 완료: {cp_path}")
        console.print("--resume 옵션으로 재개 가능")
        sys.exit(1)

    # 9. 최종 체크포인트 저장
    checkpoint.save(roots, cp_path)

    # 10. 가이드북 생성
    output_path = config.paths.output_dir / f"{parse_result.title}_해설.md"
    assemble(roots, title=f"{parse_result.title} 해설", output_path=output_path)
    console.print(f"[green]가이드북 생성 완료: {output_path}[/green]")

    # 11. 통계 출력
    stats = client.get_stats()
    console.print(f"통계: {stats}")


if __name__ == "__main__":
    main()
```

---

## 4. 입력 경로 판정 로직

```python
input_path = Path(args.input) if args.input else config.paths.pdf_input

if input_path.is_dir():
    parse_result = parse_arxiv(input_path)
elif input_path.suffix.lower() == ".pdf":
    parse_result = parse_pdf(input_path)
else:
    # 에러
```

HANDOFF.md §3-5 그대로. pdf_parser와 arxiv_parser 중 하나 호출.

---

## 5. 의존성 조립 순서와 주입

```
config → ClaudeClient → Verifier
config → ConceptCache
(client, verifier, cache) → Expander
```

모든 의존성은 main()에서 생성하고 생성자 주입. 각 모듈은 서로를 직접 생성하지 않음.

---

## 6. save_callback 정의와 on_node_done 주입

```python
def save_callback(node: ConceptNode) -> None:
    checkpoint.save(roots, cp_path)
    console.print(f"  [{node.status}] {node.concept}")
```

- `roots`는 main()의 로컬 변수 — 클로저로 캡처
- 매 노드 완료 시 전체 트리를 체크포인트에 저장
- 진행 상황도 콘솔에 출력

---

## 7. RateLimitExceeded 처리 + exit code

```python
try:
    for root in roots:
        expander.expand(root)
except RateLimitExceeded as e:
    checkpoint.save(roots, cp_path)  # 현재까지의 진행 저장
    console.print(f"[red]할당량 초과[/red]")
    sys.exit(1)
```

- 할당량 초과 시 체크포인트 저장 후 exit(1)
- 사용자는 `--resume`으로 재개 가능
- 정상 완료 시 exit(0) (기본값)

---

## 8. validate_no_anthropic_usage()

```python
def validate_no_anthropic_usage() -> None:
    """src/ 내 .py 파일에서 금지된 import/호출을 검사한다."""
    forbidden = [
        "import anthropic",
        "from anthropic",
        "import httpx",
        "import requests",
        "api.anthropic.com",
        "ANTHROPIC_API_KEY",
    ]
    src_dir = Path(__file__).parent
    for py_file in src_dir.glob("*.py"):
        if py_file.name == "main.py":
            continue  # 자기 자신은 제외 (검증 코드가 금지 문자열 참조)
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in content:
                raise RuntimeError(
                    f"금지된 패턴 발견: '{pattern}' in {py_file.name}. "
                    f"CLAUDE.md 절대 규칙 위반."
                )
```

HANDOFF.md §3-1 항목 7. main.py 시작 시 호출.

---

## 9. rich 진행 표시

간단한 `Console.print()` 방식 채택:

```
Paper Analyzer — mode=cache
입력: data/papers/attention
제목: Attention Is All You Need, 길이: 41402자
루트 섹션: 9개
  [done] Abstract
  [done] Introduction
  [verification_failed] Background
  [duplicate] Softmax 함수
  ...
가이드북 생성 완료: data/output/Attention Is All You Need_해설.md
통계: {'total_calls': 42, 'cache_hits': 10, 'cache_misses': 32, 'dry_run_calls': 0}
```

rich.progress.Progress 진행 바는 사용하지 않음 — 새 자식이 동적으로 추가되어 전체 노드 수가 변하므로 진행 바가 부정확해짐. 한 줄 출력이 더 실용적.

---

## 10. 외부 의존성

### import 목록

| 모듈 | 용도 |
|------|------|
| `argparse` | CLI 인자 파싱 |
| `sys` | exit code |
| `pathlib.Path` | 경로 |
| `rich.console.Console` | 진행 표시 |
| `src.config.load_config` | 설정 로드 |
| `src.pdf_parser.parse_pdf` | PDF 파싱 |
| `src.arxiv_parser.parse_arxiv` | TeX 파싱 |
| `src.chunker.split_into_sections` | 섹션 분할 |
| `src.tree.ConceptNode` | 노드 타입 |
| `src.concept_cache.ConceptCache` | 중복 캐시 |
| `src.claude_client.ClaudeClient, RateLimitExceeded` | Claude 래퍼 |
| `src.verifier.Verifier` | 검증기 |
| `src.expander.Expander` | 확장기 |
| `src.checkpoint` | 체크포인트 저장/로드 |
| `src.assembler.assemble` | 가이드북 생성 |

### 절대 금지

anthropic, httpx, requests — `validate_no_anthropic_usage()`가 강제.

---

## 11. 에러 처리

| 단계 | 실패 시나리오 | 처리 |
|------|-------------|------|
| config 로드 | YAML 파싱 실패, Pydantic 검증 실패 | 예외 전파 → 프로그램 종료 |
| 입력 파싱 | 파일 없음, 비PDF, 암호 PDF | 예외 전파 → 프로그램 종료 |
| chunking | 헤더 0개 | "Document" 노드 1개 반환 (정상) |
| 체크포인트 로드 | JSON 손상 | ValueError → 프로그램 종료 (수동 복구 필요) |
| 확장 중 할당량 초과 | RateLimitExceeded | 체크포인트 저장 → exit(1) |
| 확장 중 개별 노드 실패 | RuntimeError 등 | expander가 해당 노드만 failed 처리, 계속 진행 |
| 가이드북 생성 | 디스크 쓰기 실패 | 예외 전파 → 종료 (체크포인트는 이미 저장됨) |

---

## 12. 테스트 전략

### dry_run 전체 파이프라인

```bash
python -m src.main --mode dry_run --input data/papers/attention
```

- Claude 호출 0 (dry_run)
- 모든 노드 verification_failed (정상)
- 가이드북 생성됨 (모든 섹션에 "[검증 실패]" 또는 "[미완료]")
- 체크포인트 저장됨
- 통계 출력됨

### 작은 입력으로 cache 모드 (사용자 허락)

- Attention 논문의 한 섹션만 잘라서 입력
- 또는 매우 짧은 논문 (.tex 1개)

---

## 13. 까다로운 부분

### ① 체크포인트 재개 시 chunker 결과와의 불일치

`--resume`으로 재개할 때, 체크포인트의 트리 구조가 현재 chunker 결과와 다를 수 있음 (예: 코드 변경으로 chunker 동작이 바뀐 경우). 현재 설계는 `--resume` 시 chunker를 건너뛰고 체크포인트만 사용하므로 불일치 문제 없음. 단, 새로 chunking한 결과와 체크포인트를 "병합"하는 기능은 없음.

### ② save_callback의 성능

매 노드 완료 시 전체 트리를 JSON으로 직렬화하고 디스크에 쓴다. 노드가 수백 개이고 트리가 깊으면 직렬화 비용이 쌓일 수 있음. 하지만 `_node_to_dict` 재귀가 O(N)이고, JSON 직렬화도 O(N)이며, N이 수백~수천 범위이므로 현실적으로 문제없음. Claude 호출 대기 시간(3초+)에 비하면 무시할 수 있는 비용.

### ③ --input 오버라이드와 config.paths.pdf_input의 관계

config.yaml의 `paths.pdf_input`은 기본 입력 경로이지만, `--input` CLI 인자로 오버라이드 가능. 단, config의 `pdf_input`은 `Path` 타입(Pydantic이 변환)이고, `--input`은 문자열이므로 `Path(args.input)`으로 변환 필요. 또한 config의 경로는 `load_config()`에서 절대경로로 정규화되지만, `--input`은 정규화되지 않음 — `Path(args.input).resolve()`를 사용하는 것을 고려.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
