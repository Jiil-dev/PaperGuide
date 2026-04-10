# 단일 책임: CLI 진입점. 전체 파이프라인 오케스트레이션 (config → 파싱 → chunking → expanding → assembling).
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console

from src.arxiv_parser import parse_arxiv
from src.assembler import assemble, assemble_3part_guidebook
from src import checkpoint
from src.chunker import split_into_sections, split_into_raw_sections
from src.claude_client import ClaudeClient, RateLimitExceeded
from src.concept_cache import ConceptCache
from src.config import load_config
from src.data_types import PaperAnalysis
from src.expander import Expander
from src.paper_analyzer import analyze_paper
from src.part3_writer import write_part3_topic
from src.pdf_parser import parse_pdf
from src.prerequisite_collector import collect_prerequisites
from src.verifier import Verifier


def _is_archive(path: Path) -> bool:
    """압축 파일인지 판정한다."""
    name = path.name.lower()
    return (
        name.endswith(".tar.gz")
        or name.endswith(".tgz")
        or name.endswith(".tar")
        or name.endswith(".zip")
    )


def _extract_archive(archive_path: Path) -> Path:
    """압축 파일을 임시 디렉터리에 풀고 그 경로를 반환한다.

    호출자가 작업 후 shutil.rmtree()로 정리해야 한다.

    Args:
        archive_path: .tar.gz, .tgz, .tar, .zip 파일 경로.

    Returns:
        압축 해제된 디렉터리 경로.

    Raises:
        ValueError: 지원하지 않는 형식.
    """
    extracted = Path(tempfile.mkdtemp(prefix="paperguide_extract_"))
    name = archive_path.name.lower()

    if name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive_path) as tar:
            tar.extractall(extracted, filter="data")
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extracted)
    else:
        shutil.rmtree(extracted, ignore_errors=True)
        raise ValueError(f"지원하지 않는 압축 형식: {archive_path}")

    # 단일 최상위 폴더가 있으면 그 안으로 들어감 (arXiv 관습)
    contents = list(extracted.iterdir())
    if len(contents) == 1 and contents[0].is_dir():
        return contents[0]
    return extracted


def _parse_input(input_path: Path, console: Console):
    """입력 경로를 파싱하여 (ParseResult, temp_dir_or_None)을 반환한다."""
    extracted_temp_dir = None

    if input_path.is_dir():
        parse_result = parse_arxiv(input_path)
    elif input_path.suffix.lower() == ".pdf":
        parse_result = parse_pdf(input_path)
    elif _is_archive(input_path):
        console.print(f"       압축 파일 감지: {input_path.name}")
        console.print("       임시 디렉터리에 압축 해제 중...")
        extracted_dir = _extract_archive(input_path)
        # 정리용 최상위 temp 디렉터리 기록
        if extracted_dir.parent.name.startswith("paperguide_extract_"):
            extracted_temp_dir = extracted_dir.parent
        else:
            extracted_temp_dir = extracted_dir
        console.print(f"       해제 완료: {extracted_dir}")
        parse_result = parse_arxiv(extracted_dir)
    else:
        console.print(f"[red]지원하지 않는 입력 형식: {input_path}[/red]")
        console.print("지원 형식: 디렉터리, .pdf, .tar.gz, .tgz, .tar, .zip")
        sys.exit(1)

    return parse_result, extracted_temp_dir


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
    parser.add_argument(
        "--output",
        help="출력 파일 경로 (기본: data/output/<title>_해설.md)",
    )
    parser.add_argument(
        "--cache-dir",
        help="캐시 디렉터리 오버라이드",
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=3,
        choices=[2, 3],
        help="파이프라인 버전 (기본: 3)",
    )
    return parser.parse_args()


def run_phase2_pipeline(args: argparse.Namespace, config, console: Console) -> None:
    """Phase 2 파이프라인 (기존 bottom-up 로직)."""
    mode = args.mode if args.mode is not None else config.claude.default_mode
    input_path = Path(args.input).resolve() if args.input else config.paths.pdf_input
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(config.claude.default_cache_dir).resolve()

    # 입력 파싱
    console.print(f"입력: {input_path}")
    parse_result, extracted_temp_dir = _parse_input(input_path, console)
    console.print(
        f"제목: {parse_result.title}, 길이: {len(parse_result.markdown)}자"
    )

    # chunking
    roots = split_into_sections(parse_result.markdown)
    console.print(f"루트 섹션: {len(roots)}개")

    # 체크포인트 확인
    cp_path = config.paths.checkpoints_dir / "latest.json"
    if args.resume and checkpoint.exists(cp_path):
        roots = checkpoint.load(cp_path)
        console.print(f"[yellow]체크포인트에서 재개: {cp_path}[/yellow]")

    # 의존성 조립
    client = ClaudeClient(
        mode=mode,
        cli_path=config.claude.cli_path,
        max_total_calls=config.claude.max_total_calls,
        timeout_seconds=config.claude.timeout_seconds,
        sleep_between_calls=config.claude.sleep_between_calls,
        cache_dir=cache_dir,
    )
    concept_cache = ConceptCache(
        cache_dir=cache_dir / "concept_cache",
        model_name=config.dedup.embedding_model,
        threshold=config.dedup.similarity_threshold,
    )
    verifier = Verifier(
        client=client,
        min_confidence=config.verification.min_confidence,
        sample_rate=config.verification.sample_rate,
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

    # 확장
    try:
        for root in roots:
            expander.expand(root)
    except RateLimitExceeded as e:
        checkpoint.save(roots, cp_path)
        console.print(f"[red]할당량 초과: {e}[/red]")
        console.print(f"체크포인트 저장 완료: {cp_path}")
        console.print("--resume 옵션으로 재개 가능")
        sys.exit(1)

    # 최종 체크포인트 저장
    checkpoint.save(roots, cp_path)

    # 가이드북 생성
    output_path = config.paths.output_dir / f"{parse_result.title}_해설.md"
    assemble(
        roots,
        title=f"{parse_result.title} 해설",
        output_path=output_path,
    )
    console.print(f"[green]가이드북 생성 완료: {output_path}[/green]")

    stats = client.get_stats()
    console.print(f"통계: {stats}")

    # 임시 디렉터리 정리
    if extracted_temp_dir is not None and extracted_temp_dir.exists():
        shutil.rmtree(extracted_temp_dir, ignore_errors=True)


def run_phase3_pipeline(args: argparse.Namespace, config, console: Console) -> None:
    """Phase 3 3-Part 가이드북 생성 파이프라인."""
    mode = args.mode if args.mode is not None else config.claude.default_mode
    input_path = Path(args.input).resolve() if args.input else config.paths.pdf_input
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(config.claude.default_cache_dir).resolve()

    client = ClaudeClient(
        mode=mode,
        cli_path=config.claude.cli_path,
        max_total_calls=config.claude.max_total_calls,
        timeout_seconds=config.claude.timeout_seconds,
        sleep_between_calls=config.claude.sleep_between_calls,
        cache_dir=cache_dir,
    )

    # 1. Parse
    console.print(f"[1/7] 입력 파싱: {input_path}")
    parse_result, extracted_temp_dir = _parse_input(input_path, console)
    markdown = parse_result.markdown
    console.print(f"       파싱 완료: {len(markdown)} chars")

    # 2. Analyze (Part 1 재료)
    console.print("[2/7] 논문 분석 (Part 1)...")
    try:
        analysis = analyze_paper(markdown, client)
    except ValueError:
        # dry_run 모드에서 빈 응답 → 기본값으로 대체
        analysis = PaperAnalysis(
            title=parse_result.title or "Untitled",
            core_thesis="(dry_run)",
            problem_statement="(dry_run)",
        )
    console.print(f"       제목: {analysis.title}")

    # 3. Chunk
    console.print("[3/7] 섹션 분할...")
    sections = split_into_raw_sections(markdown)
    console.print(f"       {len(sections)} 섹션")

    # 4. Expand (Part 2)
    console.print("[4/7] 섹션 확장 (Part 2, top-down)...")
    concept_cache = ConceptCache(
        cache_dir=cache_dir / "concept_cache",
        model_name=config.dedup.embedding_model,
        threshold=config.dedup.similarity_threshold,
    )
    verifier = Verifier(
        client=client,
        min_confidence=config.verification.min_confidence,
        sample_rate=config.verification.sample_rate,
    )
    expander = Expander(
        client=client,
        verifier=verifier,
        cache=concept_cache,
        max_depth=config.part2.max_depth,
        max_children_per_node=config.part2.max_children_per_node,
        max_retries=config.verification.max_retries,
        on_node_done=lambda n: console.print(f"  [{n.status}] depth={n.depth} {n.concept}"),
        use_cache=False,  # Phase 3: Part 2 는 논문 섹션이므로 중복 감지 불필요
    )

    from src.tree import ConceptNode
    max_workers = config.claude.max_workers
    console.print(f"       {len(sections)} 섹션, max_workers={max_workers}")

    # 섹션별 root 노드 미리 생성
    section_roots = []
    for section in sections:
        root = ConceptNode(
            concept=section.title,
            source_excerpt=section.content,
            depth=0,
            part=2,
        )
        section_roots.append(root)

    def _expand_one(idx_root):
        idx, root = idx_root
        try:
            expander.expand(root)
            return ("ok", idx, root)
        except RateLimitExceeded:
            return ("rate_limit", idx, root)
        except Exception as e:
            return ("error", idx, root, str(e))

    completed = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_expand_one, (i, r)): i
            for i, r in enumerate(section_roots)
        }
        for future in as_completed(futures):
            result = future.result()
            status, idx = result[0], result[1]
            root = result[2]
            if status == "ok":
                completed[idx] = root
                console.print(f"  [완료 {len(completed)}/{len(sections)}] {root.concept}")
            elif status == "rate_limit":
                console.print(f"  [rate limit] {root.concept}")
            else:
                info = result[3] if len(result) > 3 else ""
                console.print(f"  [error] {root.concept}: {info}")

    # 원래 순서 보존
    part2_trees = [completed[i] for i in sorted(completed.keys())]
    console.print(f"       {len(part2_trees)}/{len(sections)} 루트 노드 완료")

    # 5. Collect prerequisites
    console.print("[5/7] 기초 지식 주제 수집...")
    candidates = collect_prerequisites(
        part2_trees,
        config.part3.predefined_pool,
        allow_new=config.part3.allow_claude_to_add,
        max_topics=1000,  # 큐레이션 전이라 컷 안 함
    )
    console.print(f"       {len(candidates)} 후보 수집")

    if config.part3.use_curator:
        from src.prerequisite_curator import curate_prerequisites
        console.print("       큐레이터로 선별 중...")
        topics = curate_prerequisites(candidates, analysis, client)
        console.print(f"       {len(topics)} 주제 선별됨 (가변)")
    else:
        topics = candidates[:config.part3.max_topics]
        console.print(f"       {len(topics)} 주제 (max_topics 컷)")

    # 6. Write Part 3
    console.print("[6/7] Part 3 작성...")
    console.print(f"       {len(topics)} 주제, max_workers={max_workers}")

    def _write_one(idx_topic):
        idx, topic = idx_topic
        section_num = f"3.{idx + 1}"
        try:
            entry = write_part3_topic(topic, section_num, client)
            return ("ok", idx, entry, section_num, topic.title)
        except RateLimitExceeded:
            return ("rate_limit", idx, None, section_num, "")
        except Exception as e:
            return ("error", idx, None, section_num, str(e))

    p3_completed = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_write_one, (i, t)): i
            for i, t in enumerate(topics)
        }
        for future in as_completed(futures):
            status, idx, entry, section_num, info = future.result()
            if status == "ok":
                p3_completed[idx] = entry
                console.print(f"  [done] {section_num} {info}")
            elif status == "rate_limit":
                console.print(f"  [rate limit] {section_num}")
            else:
                console.print(f"  [failed] {section_num}: {info}")

    part3_entries = [p3_completed[i] for i in sorted(p3_completed.keys())]
    console.print(f"       {len(part3_entries)}/{len(topics)} 항목 완료")

    # 7. Assemble
    console.print("[7/7] 3-Part 가이드북 조립...")
    guidebook_md = assemble_3part_guidebook(analysis, part2_trees, part3_entries)

    # Save
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = config.paths.output_dir / f"{analysis.title}_완전판_가이드북.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(guidebook_md, encoding='utf-8')
    console.print(f"[green]완료: {output_path} ({len(guidebook_md)} chars)[/green]")

    stats = client.get_stats()
    console.print(f"통계: {stats}")

    # 임시 디렉터리 정리
    if extracted_temp_dir is not None and extracted_temp_dir.exists():
        shutil.rmtree(extracted_temp_dir, ignore_errors=True)


def main() -> None:
    """전체 파이프라인을 실행한다."""
    # 0. 금지 import 검사
    validate_no_anthropic_usage()

    # 1. CLI 인자 파싱
    args = _parse_args()

    # 2. config 로드 + CLI 오버라이드
    config = load_config(args.config)

    # 3. rich 콘솔 초기화
    console = Console()
    console.print(f"[bold]Paper Analyzer[/bold] — phase={args.phase}")

    # 4. 파이프라인 분기
    if args.phase == 3:
        run_phase3_pipeline(args, config, console)
    else:
        run_phase2_pipeline(args, config, console)


if __name__ == "__main__":
    main()
