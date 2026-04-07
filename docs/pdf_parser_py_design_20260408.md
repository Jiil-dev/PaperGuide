# src/pdf_parser.py 설계

## 1. 모듈 책임 (한 줄)

**PDF 파일 경로를 입력받아, 수식이 LaTeX로 보존된 Markdown 문자열과 메타데이터를 반환한다.**

---

## 2. 공개 인터페이스

### 함수 시그니처

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ParseResult:
    """PDF 파싱 결과"""
    markdown: str          # 추출된 Markdown 전문
    source_path: Path      # 원본 PDF 경로 (config.py와 일관된 pathlib.Path)
    page_count: int        # 총 페이지 수
    title: str             # PDF 메타데이터의 제목 (없으면 파일명)
    extracted_at: str      # ISO 8601 추출 시각 (예: "2026-04-08T15:30:00")

def parse_pdf(pdf_path: Path) -> ParseResult:
    """PDF를 Markdown으로 변환.
    
    Args:
        pdf_path: PDF 파일의 경로 (pathlib.Path)
    
    Returns:
        ParseResult: Markdown 문자열 + 메타데이터
    
    Raises:
        FileNotFoundError: pdf_path가 존재하지 않을 때
        ValueError: PDF가 아닌 파일이거나, 추출 결과가 빈 문자열일 때
    """
```

### 입력

- `pdf_path: Path` — PDF 파일의 절대/상대 경로. 호출자(main.py)가 config에서 읽어서 넘긴다.

### 출력

- `ParseResult` dataclass — Markdown 문자열 + 메타데이터 5개 필드.
- Markdown 문자열만 반환하는 방식도 고려했으나, 메타데이터(페이지 수, 제목, 경로)가 assembler의 표지 생성과 verifier의 원문 대조에 필요하므로 구조체로 반환.

### 예상 사용 예시 (main.py)

```python
from pathlib import Path
from src.pdf_parser import parse_pdf

pdf_path = Path(config.paths.pdf_input)  # config에서 경로 가져옴
result = parse_pdf(pdf_path)

print(result.page_count)   # 9
print(result.title)        # "Attention Is All You Need"
print(result.markdown[:200])  # Markdown 앞부분 확인

# chunker에 Markdown 전달
sections = split_into_sections(result.markdown)
```

---

## 3. 출력 데이터 구조

### 결정: `ParseResult` dataclass 반환

| 대안 | 장점 | 단점 | 선택 |
|------|------|------|------|
| `str` (Markdown만) | 단순 | 메타데이터 전달 불가 | 탈락 |
| `tuple[str, dict]` | 메타데이터 포함 | 타입 불명확, dict 키 관리 어려움 | 탈락 |
| `@dataclass` | 타입 명확, IDE 자동완성, 필드 고정 | 클래스 하나 추가 | **선택** |

### ParseResult 필드

| 필드 | 타입 | 용도 |
|------|------|------|
| `markdown` | str | 추출된 Markdown 전문. chunker의 입력 |
| `source_path` | Path | 원본 PDF 경로. pathlib.Path로 보존 (config.py와 일관성) |
| `page_count` | int | 총 페이지 수. 로깅/진행률에 사용 |
| `title` | str | PDF 메타데이터의 제목. 없으면 파일명(확장자 제외)으로 대체 |
| `extracted_at` | str | ISO 8601 추출 시각. 체크포인트/감사 로그용 |

---

## 4. pymupdf4llm API 사용법

### 핵심 함수

```python
import pymupdf4llm

md_text = pymupdf4llm.to_markdown("paper.pdf")
```

`pymupdf4llm.to_markdown(doc, ...)` 이 유일한 공개 API. 내부적으로 PyMuPDF(fitz)를 사용하여 PDF를 파싱하고, Markdown으로 변환.

### 수식 LaTeX 보존

- pymupdf4llm은 PDF에서 텍스트를 추출할 때 OCR이 아닌 텍스트 레이어를 읽음
- **수식이 LaTeX로 자동 보존되는지는 불확실**. PDF 내부에 수식이 텍스트로 저장된 경우(예: arXiv 논문)에는 수식 문자가 그대로 추출됨. 하지만 이것이 `$...$`로 감싸진 LaTeX 문법인지는 PDF 원본 인코딩에 따라 다를 수 있음.
- **실제 테스트로 확인해야 함**: arXiv 논문 PDF를 변환해보고, 수식이 LaTeX로 나오는지 확인 필요. 수식이 깨지면 CLAUDE.md에 명시된 대로 marker-pdf로 교체 검토.

### 주요 옵션 (확인 필요)

```python
pymupdf4llm.to_markdown(
    doc,                    # 파일 경로 또는 fitz.Document 객체
    pages=None,             # 특정 페이지만 추출 (리스트, 예: [0,1,2])
    page_chunks=False,      # True면 페이지별로 분리된 리스트 반환
    write_images=False,     # True면 이미지를 파일로 저장
    image_path="",          # 이미지 저장 경로
    show_progress=True,     # 진행률 표시
)
```

- **불확실 사항**: 위 옵션 목록은 공개 문서 기반 추정. 실제 설치 후 `help(pymupdf4llm.to_markdown)`으로 정확한 시그니처 확인 필요.
- `page_chunks=False` (기본값): 전체 Markdown을 하나의 문자열로 반환.
- `write_images=False` (기본값): 이미지를 파일로 저장하지 않음. 우리 프로젝트에서는 이미지 추출 불필요 — 텍스트/수식만 필요.

### 페이지 수/제목 등 메타데이터 취득

pymupdf4llm 자체는 메타데이터 API를 제공하지 않음. 내부적으로 사용하는 PyMuPDF(fitz)를 직접 호출:

```python
import pymupdf  # PyMuPDF (pymupdf4llm 설치 시 함께 설치됨)

doc = pymupdf.open(pdf_path)
page_count = len(doc)
title = doc.metadata.get("title", "") or pdf_path.stem
doc.close()
```

- pymupdf(fitz)는 pymupdf4llm의 의존성이므로 별도 설치 불필요.
- **불확실 사항**: `pymupdf.open`인지 `fitz.open`인지 import 경로가 버전에 따라 다를 수 있음. 설치 후 확인 필요.

---

## 5. 에러 처리

### 파일 없음

```python
if not pdf_path.exists():
    raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
```

- 명확한 경로를 포함한 에러 메시지.

### PDF가 아닌 파일

```python
if pdf_path.suffix.lower() != ".pdf":
    raise ValueError(f"PDF 파일이 아닙니다 (확장자: {pdf_path.suffix}): {pdf_path}")
```

- 확장자 체크로 충분. 매직 넘버(%PDF-) 검사는 과잉 — pymupdf4llm이 잘못된 파일을 열면 자체적으로 에러를 발생시킬 것.

### 암호 걸린 PDF

- **불확실**: pymupdf4llm / PyMuPDF가 암호 걸린 PDF를 어떻게 처리하는지 모름. PyMuPDF는 `doc.is_encrypted` 속성과 `doc.authenticate(password)` 메서드를 제공하는 것으로 알고 있으나, 실제 동작은 테스트 필요.
- 현 단계에서는 암호 없는 PDF만 지원. 암호 걸린 PDF는 pymupdf4llm이 발생시키는 예외를 그대로 전파.

### 빈 PDF 또는 추출 결과가 빈 문자열

```python
if not md_text or not md_text.strip():
    raise ValueError(f"PDF에서 텍스트를 추출할 수 없습니다: {pdf_path}")
```

- 빈 결과를 에러로 처리. 빈 Markdown이 chunker에 전달되면 의미 없는 빈 트리가 생성됨 — 일찍 실패하는 게 올바름.

---

## 6. 외부 의존성

### 외부 라이브러리

| 패키지 | 용도 |
|--------|------|
| `pymupdf4llm` | PDF → Markdown 변환 |
| `pymupdf` (fitz) | 메타데이터(페이지 수, 제목) 취득. pymupdf4llm 설치 시 자동 포함 |

### 표준 라이브러리

| 모듈 | 용도 |
|------|------|
| `pathlib.Path` | 경로 처리 |
| `dataclasses` | ParseResult 정의 |
| `datetime` | extracted_at 생성 |

### 다른 모듈 import 여부

- `config.py` — **import 안 함**. pdf_parser.py는 config의 `paths.pdf_input`을 직접 읽지 않는다. 호출자(main.py)가 경로를 인자로 넘긴다.
- `tree.py` — **import 안 함**. pdf_parser.py는 ConceptNode를 모른다. Markdown을 반환할 뿐.
- 이 모듈은 **독립적**: 입력은 Path, 출력은 ParseResult. 다른 src/ 모듈에 대한 의존성 0.

---

## 7. 테스트 전략

- **Claude 호출 할당량: 0** — 이 모듈은 Claude를 전혀 사용하지 않음.
- **실제 PDF로 수동 테스트**:
  1. arXiv 논문 PDF(9페이지 이하)를 `data/papers/`에 넣고 `parse_pdf()`를 실행
  2. 확인 항목:
     - 수식이 LaTeX 문법(`$...$`, `$$...$$`)으로 보존되는지
     - 섹션 헤더가 Markdown `#`/`##`으로 변환되는지
     - 페이지 수, 제목이 정확한지
     - 한글/영문 혼합 논문에서 인코딩이 깨지지 않는지
  3. **수식이 깨지면**: CLAUDE.md에 따라 marker-pdf로 교체 검토를 사용자에게 제안
- **아주 큰 PDF(수백 페이지)는 나중 단계에서** — 지금은 짧은 논문(9페이지 이하)만 대상.
- **테스트 실행은 사용자 허락 후**: PDF 파일이 필요하고, pymupdf4llm 설치가 선행돼야 하므로 "지금 돌려도 되나?" 확인.

---

## 8. 가장 까다로울 것 같은 부분

### ① 수식 LaTeX 보존 여부

**핵심 불확실성.** pymupdf4llm이 PDF의 수식을 어떻게 추출하는지는 실제 테스트 전까지 확신할 수 없다.

- **최선**: `$E = mc^2$` 형태로 LaTeX가 그대로 나옴
- **차선**: 수식 문자는 추출되지만 LaTeX 문법이 아닌 유니코드 기호로 나옴 (예: `E = mc²`)
- **최악**: 수식이 깨지거나 누락됨

최선이 아닌 경우, CLAUDE.md에 따라 marker-pdf로 교체를 검토해야 한다. 이 판단은 설계 단계가 아닌 실제 PDF 테스트 후에 내린다.

### ② pymupdf4llm API의 버전별 차이

pymupdf4llm은 비교적 새로운 라이브러리로, API가 버전에 따라 바뀔 수 있다. 특히:
- `to_markdown()` 함수의 매개변수 이름과 기본값
- 반환 타입 (문자열 vs 리스트)
- PyMuPDF import 경로 (`pymupdf` vs `fitz`)

설치 후 `help(pymupdf4llm.to_markdown)`으로 실제 시그니처를 확인하고, 설계와 다른 부분이 있으면 코드를 맞춰야 한다.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
