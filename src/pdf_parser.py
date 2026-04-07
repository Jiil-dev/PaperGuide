# 단일 책임: PDF 파일 경로를 입력받아, 수식이 LaTeX로 보존된 Markdown 문자열과 메타데이터를 반환한다.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf
import pymupdf4llm


@dataclass
class ParseResult:
    """PDF 파싱 결과.

    markdown 필드가 chunker의 입력이 된다.
    메타데이터는 assembler 표지 생성, 체크포인트 기록 등에 사용.
    """

    markdown: str  # 추출된 Markdown 전문
    source_path: Path  # 원본 PDF 경로 (pathlib.Path)
    page_count: int  # 총 페이지 수
    title: str  # PDF 메타데이터의 제목 (없으면 파일명)
    extracted_at: datetime = field(default_factory=datetime.now)  # 추출 시각


def parse_pdf(pdf_path: Path) -> ParseResult:
    """PDF를 Markdown으로 변환한다.

    Args:
        pdf_path: PDF 파일의 경로 (pathlib.Path).

    Returns:
        ParseResult: Markdown 문자열 + 메타데이터.

    Raises:
        FileNotFoundError: pdf_path가 존재하지 않을 때.
        ValueError: PDF가 아닌 파일, 암호 걸린 PDF, 또는 추출 결과가 빈 문자열일 때.
    """
    # 파일 존재 여부
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    # 확장자 체크
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"PDF 파일이 아닙니다 (확장자: {pdf_path.suffix}): {pdf_path}"
        )

    # 메타데이터 추출 (pymupdf로 직접)
    doc = pymupdf.open(pdf_path)
    try:
        if doc.is_encrypted:
            raise ValueError(
                f"암호가 걸린 PDF는 지원하지 않습니다: {pdf_path}"
            )
        page_count = len(doc)
        title = doc.metadata.get("title", "") or pdf_path.stem
    finally:
        doc.close()

    # Markdown 변환
    md_text = pymupdf4llm.to_markdown(
        str(pdf_path),
        show_progress=False,
        write_images=False,
    )

    # 빈 결과 체크
    if not md_text or not md_text.strip():
        raise ValueError(f"PDF에서 텍스트를 추출할 수 없습니다: {pdf_path}")

    return ParseResult(
        markdown=md_text,
        source_path=pdf_path,
        page_count=page_count,
        title=title,
    )
