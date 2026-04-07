# 단일 책임: CLI 진입점. 전체 파이프라인 오케스트레이션 (config → 파싱 → chunking → expanding → assembling).
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rich.console import Console

from src.arxiv_parser import parse_arxiv
from src.assembler import assemble
from src import checkpoint
from src.chunker import split_into_sections
from src.claude_client import ClaudeClient, RateLimitExceeded
from src.concept_cache import ConceptCache
from src.config import load_config
from src.expander import Expander
from src.pdf_parser import parse_pdf
from src.verifier import Verifier


def validate_no_anthropic_usage() -> None:
    """src/ 내 .py 파일에서 금지된 import를 검사한다.

    주석(#로 시작하는 줄)은 검사에서 제외.
    main.py 자신은 제외 (검증 코드가 금지 문자열을 참조하므로).
    """
    forbidden_imports = [
        re.compile(r"^\s*import\s+anthropic(\s|$|\.)"),
        re.compile(r"^\s*from\s+anthropic(\s|\.)"),
        re.compile(r"^\s*import\s+httpx(\s|$|\.)"),
        re.compile(r"^\s*from\s+httpx(\s|\.)"),
        re.compile(r"^\s*import\s+requests(\s|$|\.)"),
        re.compile(r"^\s*from\s+requests(\s|\.)"),
    ]

    src_dir = Path(__file__).parent
    for py_file in src_dir.glob("*.py"):
        if py_file.name == "main.py":
            continue

        lines = py_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            code_part = line.split("#", 1)[0]

            for pattern in forbidden_imports:
                if pattern.match(code_part):
                    raise RuntimeError(
                        f"금지된 import 발견: {py_file.name}:{lineno}: "
                        f"{stripped}. CLAUDE.md 절대 규칙 위반."
                    )


def _parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(
        description="AI 논문 PDF/TeX를 학부 1학년용 가이드북으로 변환"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="설정 파일 경로 (기본: config.yaml)"
    )
    parser.add_argument(
        "--mode",
        choices=["live", "cache", "dry_run"],
        help="Claude 모드 오버라이드 (config.yaml 값 대신 사용)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="체크포인트에서 재개",
    )
    parser.add_argument(
        "--input",
        help="입력 경로 (PDF 파일 또는 TeX 디렉터리)",
    )
    return parser.parse_args()


def main() -> None:
    """전체 파이프라인을 실행한다."""
    # 0. 금지 import 검사
    validate_no_anthropic_usage()

    # 1. CLI 인자 파싱
    args = _parse_args()

    # 2. config 로드 + CLI 오버라이드
    config = load_config(args.config)
    mode = args.mode or config.claude.mode
    input_path = Path(args.input).resolve() if args.input else config.paths.pdf_input

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
    console.print(
        f"제목: {parse_result.title}, 길이: {len(parse_result.markdown)}자"
    )

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
        """매 노드 완료 시 체크포인트 저장 + 진행 출력."""
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
    assemble(
        roots,
        title=f"{parse_result.title} 해설",
        output_path=output_path,
    )
    console.print(f"[green]가이드북 생성 완료: {output_path}[/green]")

    # 11. 통계 출력
    stats = client.get_stats()
    console.print(f"통계: {stats}")


if __name__ == "__main__":
    main()
