# pdf_parser.py 구현 결과

## 1. pymupdf4llm API 확인

### 1-1. 버전

```
pymupdf 1.27.2.2
pymupdf4llm 1.27.2.2
```

### 1-2. to_markdown 시그니처

`to_markdown(*args, **kwargs)` — 래퍼 함수. 내부적으로 `_layout_to_markdown()`을 호출.

실제 시그니처:

```python
_layout_to_markdown(
    doc,
    *,
    dpi=150,
    embed_images=False,
    filename="",
    footer=True,
    force_ocr=False,
    force_text=True,
    header=True,
    ignore_code=False,
    image_format="png",
    image_path="",
    ocr_dpi=300,
    ocr_function=None,
    ocr_language="eng",
    page_chunks=False,
    page_height=None,
    page_separators=False,
    pages=None,
    page_width=612,
    show_progress=False,
    use_ocr=True,
    write_images=False,
    **kwargs,
)
```

설계 시 추정했던 `pages`, `page_chunks`, `write_images`, `show_progress` 옵션이 모두 실제 존재함. `embed_images`, `footer`, `header`, `force_text`, `use_ocr` 등 추가 옵션도 확인됨.

## 2. 작성된 코드 (src/pdf_parser.py 전체)

```python
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
```

## 3. 검증 결과

### 3-1. import 테스트

```
$ .venv/bin/python -c "from src.pdf_parser import parse_pdf, ParseResult; print('import OK')"
import OK
```

### 3-2. 실제 PDF 파싱 테스트

```
$ .venv/bin/python -c "
from pathlib import Path
from src.pdf_parser import parse_pdf
result = parse_pdf(Path('data/papers/distillation.pdf'))
print('page_count:', result.page_count)
print('title:', result.title)
print('extracted_at:', result.extracted_at)
print('markdown length:', len(result.markdown))
print('--- first 500 chars ---')
print(result.markdown[:500])
print('--- last 500 chars ---')
print(result.markdown[-500:])
"

page_count: 9
title: distillation
extracted_at: 2026-04-08 04:57:16.818866
markdown length: 33755
--- first 500 chars ---
**==> picture [397 x 6] intentionally omitted <==**

## **Distilling the Knowledge in a Neural Network** 

**Geoffrey Hinton**[∗†] **Oriol Vinyals**[†] **Jeff Dean** Google Inc. Google Inc. Google Inc. Mountain View Mountain View Mountain View `geoffhinton@google.com vinyals@google.com jeff@google.com` 

## **Abstract** 

A very simple way to improve the performance of almost any machine learning algorithm is to train many different models on the same data and then to average their predictions [
--- last 500 chars ---
 neural networks. In _Advances in Neural Information Processing Systems_ , pages 1097–1105, 2012. 

- [8] J. Li, R. Zhao, J. Huang, and Y. Gong. Learning small-size dnn with output-distribution-based criteria. In _Proceedings Interspeech 2014_ , pages 1910–1914, 2014. 

- [9] N. Srivastava, G.E. Hinton, A. Krizhevsky, I. Sutskever, and R. R. Salakhutdinov. Dropout: A simple way to prevent neural networks from overfitting. _The Journal of Machine Learning Research_ , 15(1):1929–1958, 2014. 

9
```

- page_count: 9 (정확)
- title: "distillation" (PDF 메타데이터에 title 없어서 파일명 폴백 — 정상)
- extracted_at: datetime 객체 (보정 반영 확인)
- markdown length: 33,755자

### 3-3. 에러 테스트 (nonexistent)

```
$ .venv/bin/python -c "from pathlib import Path; from src.pdf_parser import parse_pdf; parse_pdf(Path('nonexistent.pdf'))"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/home/engineer/j0061/paper-analyzer/src/pdf_parser.py", line 42, in parse_pdf
    raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
FileNotFoundError: PDF 파일을 찾을 수 없습니다: nonexistent.pdf
```

한국어 에러 메시지 정상 출력.

### 3-4. 에러 테스트 (비PDF)

```
$ .venv/bin/python -c "from pathlib import Path; from src.pdf_parser import parse_pdf; parse_pdf(Path('config.yaml'))"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/home/engineer/j0061/paper-analyzer/src/pdf_parser.py", line 46, in parse_pdf
    raise ValueError(
ValueError: PDF 파일이 아닙니다 (확장자: .yaml): config.yaml
```

확장자 포함 한국어 에러 메시지 정상 출력.

## 4. 수식 보존 여부 관찰

**수식이 LaTeX 문법으로 보존되지 않음.**

distillation.pdf(Hinton 2015 "Distilling the Knowledge in a Neural Network")의 추출 결과에서:

- `$...$` 또는 `$$...$$` 패턴: **0개** 발견
- 수식 관련 키워드(softmax, temperature, log, exp) 근처에서 수식 기호나 LaTeX가 아닌 **평문 영어**로만 추출됨
- 예: "raise the temperature of the final softmax" — 수식이 아닌 자연어 설명만 존재

**원인 분석**: 이 논문 자체가 수식이 거의 없는 논문. softmax 수식 등이 일부 존재하나, pymupdf4llm이 이를 LaTeX가 아닌 유니코드/평문으로 추출했을 가능성이 높음. **수식이 많은 논문(예: Attention Is All You Need)으로 추가 테스트**해야 정확한 판단 가능.

**현재 판단**: 수식 보존 여부를 확정하기에는 테스트 논문이 수식 빈약. 수식 밀도가 높은 논문으로 재테스트 필요. CLAUDE.md의 "수식 깨지면 marker-pdf로 교체 검토" 판단은 보류.

## 5. 구현 중 주의했던 점

1. **extracted_at 타입을 datetime으로 변경**: 설계 보정 반영. `field(default_factory=datetime.now)`로 생성 시점 자동 기록. 직렬화 시 호출자가 `.isoformat()`으로 변환하는 책임.

2. **doc.close() 누락 방지**: `try/finally` 패턴으로 pymupdf Document를 반드시 닫음. `is_encrypted` 체크에서 ValueError가 발생해도 finally 블록에서 close() 호출됨.

3. **pymupdf4llm.to_markdown()에 str 경로 전달**: pymupdf4llm은 내부적으로 문서를 다시 열므로, pymupdf Document 객체를 공유하지 않고 `str(pdf_path)`로 경로를 넘김. 메타데이터 추출용 pymupdf.open()과 Markdown 변환용 pymupdf4llm.to_markdown()은 독립적으로 동작.

4. **title 폴백**: PDF 메타데이터에 title이 빈 문자열이면 `pdf_path.stem` (파일명에서 확장자 제외)으로 대체. 실제 테스트에서 distillation.pdf가 title 메타데이터 없어서 "distillation"으로 정상 폴백 확인.

5. **다른 모듈 import 없음**: config.py, tree.py 모두 import하지 않음. 이 모듈은 완전히 독립적 — 입력은 Path, 출력은 ParseResult.

## 6. 사용자에게 보고할 이슈

1. **수식 보존 판정 보류**: distillation.pdf는 수식이 거의 없는 논문이라 LaTeX 보존 여부를 판단하기 어려움. 수식이 많은 논문(예: Attention Is All You Need, 또는 수학/물리 논문)을 `data/papers/`에 추가하여 재테스트할 것을 권장.

2. **이미지 placeholder**: 추출 결과 첫 줄에 `**==> picture [397 x 6] intentionally omitted <==**`이 나옴. pymupdf4llm이 `write_images=False`일 때 이미지 위치에 placeholder를 삽입하는 동작. chunker가 이 placeholder를 적절히 처리하거나 무시해야 할 수 있음.

3. **헤더 형식 확인**: 섹션 제목이 `## **Distilling the Knowledge in a Neural Network**` 형태로 `##` + 볼드로 추출됨. chunker가 `## **제목**` 패턴을 `##` 헤더로 인식하는지 확인 필요.
