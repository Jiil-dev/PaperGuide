# src/arxiv_parser.py 설계

## 1. 모듈 책임 (한 줄)

**arXiv LaTeX 소스 디렉터리를 입력받아, 수식이 LaTeX 원본으로 보존되고 섹션 구조가 Markdown 헤더로 변환된 통합 Markdown 문자열과 메타데이터를 반환한다.**

---

## 2. 공개 인터페이스

### ParseResult 재사용 판단

**pdf_parser.py에서 직접 import한다.**

| 대안 | 장점 | 단점 | 선택 |
|------|------|------|------|
| pdf_parser에서 import | 변경 0줄, 즉시 사용 가능 | arxiv_parser → pdf_parser 의존 발생 | **선택** |
| 공통 모듈(types.py 등)로 분리 | 깔끔한 의존성 | 파일 하나 추가 (CLAUDE.md 절대 규칙 5번: 합의 필요), 현재는 2개 모듈뿐 | 탈락 |

근거: ParseResult는 5개 필드의 단순 dataclass. 두 파서만 사용. 모듈이 3개 이상으로 늘어날 때 분리해도 늦지 않음. 지금 공통 모듈을 만들면 과잉 추상화.

### 함수 시그니처

```python
from pathlib import Path
from src.pdf_parser import ParseResult

def parse_arxiv(source_dir: Path) -> ParseResult:
    """arXiv LaTeX 소스 디렉터리를 Markdown으로 변환한다.

    Args:
        source_dir: .tex 파일들이 있는 디렉터리 경로.

    Returns:
        ParseResult: Markdown 문자열 + 메타데이터.
            page_count는 TeX 소스에는 페이지 개념이 없어 0으로 고정.

    Raises:
        FileNotFoundError: source_dir가 존재하지 않을 때.
        ValueError: 디렉터리가 아닐 때, .tex 파일이 없을 때,
                    메인 .tex 파일을 판정할 수 없을 때.
    """
```

### 예상 사용 예시 (main.py)

```python
from pathlib import Path
from src.pdf_parser import parse_pdf, ParseResult
from src.arxiv_parser import parse_arxiv

input_path = Path(config.paths.pdf_input)

if input_path.is_dir():
    result: ParseResult = parse_arxiv(input_path)
elif input_path.suffix.lower() == ".pdf":
    result: ParseResult = parse_pdf(input_path)
else:
    raise ValueError(f"지원하지 않는 입력 형식: {input_path}")

# 이후 chunker에 동일하게 전달
sections = split_into_sections(result.markdown)
```

---

## 3. 메인 .tex 파일 판정 전략

### 결정: **(d) 조합 — `\documentclass` 우선, 없으면 관습 이름, 없으면 실패**

#### 알고리즘

```
1. 디렉터리 내 모든 .tex 파일을 수집
2. 각 파일의 첫 100줄을 읽어 \documentclass 포함 여부 확인
3. \documentclass가 있는 파일이 정확히 1개 → 그 파일이 메인
4. \documentclass가 있는 파일이 2개 이상 → ValueError (모호)
5. \documentclass가 없으면 → 관습적 이름 검색:
   main.tex, ms.tex, paper.tex, article.tex 순서로 존재 확인
6. 관습 이름도 없으면 → ValueError (메인 파일 판정 실패)
```

#### 근거

- **(a) `\documentclass` 우선**: 가장 확실한 판별 기준. arXiv 소스에서 메인 파일만 `\documentclass`를 가짐 (서브 파일은 `\input`으로 포함됨).
- 실제 검증: `data/papers/attention/`에서 `\documentclass`가 있는 파일은 `ms.tex` 1개뿐.
- **(c) 관습 이름 폴백**: `\documentclass` 없는 비표준 소스(드물지만 가능)를 위한 안전망.
- **(b) 크기/\input 개수**: 불확실하고 오탐 위험 높아 사용하지 않음.

---

## 4. `\input{...}` / `\include{...}` 재귀 확장 로직

### 처리 순서

```
1. 주석 제거 (% 이후 줄 끝까지, 단 \%는 보존)
2. \input{filename} 또는 \include{filename} 발견 시 재귀 확장
```

주석을 먼저 제거하는 이유: `%\input{sqrt_d_trick}` 같은 주석 처리된 input을 확장하면 안 됨. 실제 `ms.tex`에 `%\input{parameter_attention}`과 `%\input{sqrt_d_trick}`이 주석 처리되어 있음.

### 확장 규칙

```python
# \input{filename} → filename.tex 또는 filename 그대로 시도
# \include{filename} → 동일하게 처리 (\include의 페이지 나누기는 무시)
```

- `\input{introduction}` → `introduction.tex` 파일 내용으로 치환
- `\input{introduction.tex}` → `introduction.tex` 파일 내용으로 치환
- 확장자가 없으면 `.tex`를 붙여서 시도, 있으면 그대로 사용

### 순환 참조 감지

- 확장 중 방문한 파일 경로를 `set`으로 추적
- 이미 방문한 파일을 다시 만나면 → 무시 (빈 문자열로 치환) + 경고 로그
- 에러를 발생시키지 않는 이유: 순환 참조는 저자의 실수이지 우리 프로그램을 중단할 이유는 아님

### 참조된 파일 없음

- `\input{nonexistent}` → 빈 문자열로 치환 + 경고 로그
- 에러를 발생시키지 않는 이유: arXiv 소스에 가끔 정리 안 된 input이 남아있음. 핵심 내용이 누락될 수 있지만, 그건 소스 품질 문제.

---

## 5. LaTeX → Markdown 변환 규칙

### 기본 원칙

1. **수식은 절대 건드리지 않는다** — `$...$`, `$$...$$`, `\begin{equation}...\end{equation}`, `\begin{align}...\end{align}` 등 수식 환경은 원본 그대로 보존. Claude가 LaTeX 수식을 직접 읽고 이해할 수 있음.
2. **의심스러우면 원문 그대로 유지** — 완벽한 LaTeX 파서가 아님. 변환 실패보다 원문 보존이 안전.

### 구체적 변환 규칙

| LaTeX 명령 | Markdown 변환 | 근거 |
|-----------|--------------|------|
| `\section{X}` | `# X` | 표준 변환 |
| `\section*{X}` | `# X` | `*` (번호 없음)는 Markdown에서 무의미 |
| `\subsection{X}` | `## X` | 표준 변환 |
| `\subsubsection{X}` | `### X` | 표준 변환 |
| `\paragraph{X}` | `**X**` | `####`는 과도. 볼드가 시각적으로 적절 |
| `\title{X}` | 메타데이터로 추출. 본문에서 제거 | title은 ParseResult.title에 저장 |
| `\author{X}` | 제거 | 저자 분석 안 함 |
| `\maketitle` | 제거 | 렌더링 명령 |
| `\begin{abstract}...\end{abstract}` | `## Abstract\n\n...` | chunker가 `##` 헤더를 기대 |
| `$...$` | **그대로 보존** | 핵심 — 인라인 수식 |
| `$$...$$` | **그대로 보존** | 핵심 — 블록 수식 |
| `\begin{equation}...\end{equation}` | **그대로 보존** | 핵심 — 번호 있는 수식 |
| `\begin{align}...\end{align}` | **그대로 보존** | 핵심 — 정렬 수식 |
| `\begin{align*}...\end{align*}` | **그대로 보존** | 핵심 — 번호 없는 정렬 수식 |
| `\cite{key}` | `[key]` | 인용 키만 남김. Claude에게 "이 논문이 참조됨"을 알려줌 |
| `\citep{key}` | `[key]` | 동일 |
| `\citet{key}` | `[key]` | 동일 |
| `\ref{label}` | `[ref:label]` | 내부 참조 힌트만 남김 |
| `\eqref{label}` | `[eq:label]` | 수식 참조 힌트 |
| `\label{...}` | 제거 | 내부 링크 불필요 |
| `\textbf{X}` | `**X**` | 표준 변환 |
| `\emph{X}` | `*X*` | 표준 변환 |
| `\textit{X}` | `*X*` | 표준 변환 |
| `\texttt{X}` | `` `X` `` | 표준 변환 |
| `\footnote{X}` | ` (각주: X)` | 본문에 괄호로 삽입. 별도 처리는 과잉 |
| `\begin{itemize}...\end{itemize}` | `- ...` 리스트 | `\item` → `- ` |
| `\begin{enumerate}...\end{enumerate}` | `1. ...` 번호 리스트 | `\item` → 순번 |
| `\begin{figure}...\end{figure}` | `[그림 생략]` | 이미지 미사용 |
| `\begin{table}...\end{table}` | **그대로 보존** | 표 내용은 Claude가 이해할 수 있으므로 원본 유지. 무리하게 Markdown table로 변환하면 깨질 위험 |
| `% 주석` | 제거 (줄 끝까지) | 단, `\%`는 `%`로 변환 (이스케이프) |
| `\documentclass{...}` | 제거 | 프리앰블 명령 |
| `\usepackage{...}` | 제거 | 프리앰블 명령 |
| `\begin{document}` | 제거 | 프리앰블 명령 |
| `\end{document}` | 제거 | 프리앰블 명령 |
| `\newcommand{...}` | 제거 | 사용자 정의 매크로 — 확장하지 않음 |
| `\def\...{...}` | 제거 | 사용자 정의 매크로 |
| `\bibliography{...}` | 제거 | 참고문헌 목록은 별도 .bib에 있고 본 프로젝트에서 불필요 |
| `\bibliographystyle{...}` | 제거 | 동일 |
| `\includegraphics[...]{...}` | `[그림: filename]` | 이미지 파일명만 힌트로 남김 |
| 기타 `\cmd{X}` (알 수 없는 명령) | `X` (콘텐츠만 남기고 명령 제거) | 안전한 기본값. 인자가 없는 명령은 그대로 유지 |
| 기타 `\cmd` (인자 없는 알 수 없는 명령) | 그대로 유지 | 삭제하면 의미 손실 가능. Claude가 원본을 봐도 이해 가능 |

### 변환 순서

```
1. 주석 제거 (% 이후 줄 끝까지, \% 보존)
2. \input / \include 재귀 확장
3. 프리앰블 제거 (\documentclass부터 \begin{document}까지)
4. \end{document} 이후 제거
5. \title{...} 추출 → ParseResult.title에 저장
6. 구조 명령 변환 (\section → #, \subsection → ##, ...)
7. 텍스트 서식 변환 (\textbf → **, \emph → *, ...)
8. 환경 변환 (abstract, itemize, enumerate, figure)
9. 참조 명령 변환 (\cite → [key], \ref → [ref:label], ...)
10. 정리 명령 제거 (\label, \maketitle, \author, ...)
11. 기타 알 수 없는 \cmd{X} → X
12. 연속 빈 줄 정리 (3줄 이상 → 2줄)
```

**수식 환경은 어떤 단계에서도 건드리지 않는다.** 변환 로직은 수식 환경 내부를 스킵해야 함.

---

## 6. 에러 처리

### 디렉터리 없음

```python
if not source_dir.exists():
    raise FileNotFoundError(f"디렉터리를 찾을 수 없습니다: {source_dir}")
```

### 디렉터리가 아님

```python
if not source_dir.is_dir():
    raise ValueError(f"디렉터리가 아닙니다: {source_dir}")
```

### .tex 파일 없음

```python
tex_files = list(source_dir.glob("*.tex"))
if not tex_files:
    raise ValueError(f"디렉터리에 .tex 파일이 없습니다: {source_dir}")
```

### 메인 파일 판정 실패

```python
raise ValueError(
    f"메인 .tex 파일을 판정할 수 없습니다. "
    f"\\documentclass가 있는 파일이 없고, "
    f"main.tex/ms.tex/paper.tex/article.tex도 없습니다: {source_dir}"
)
```

### 순환 \input 감지

- 에러 아님. 경고 로그 + 빈 문자열로 치환.
- `import warnings; warnings.warn(...)` 또는 `print()` (rich 로깅은 나중 단계)

### 참조된 파일 없음

- 에러 아님. 경고 로그 + 빈 문자열로 치환.

---

## 7. 외부 의존성

### 외부 라이브러리

없음. **표준 라이브러리만 사용.**

### 표준 라이브러리

| 모듈 | 용도 |
|------|------|
| `pathlib.Path` | 경로 처리 |
| `re` | 정규식 기반 LaTeX 파싱 |
| `datetime` | extracted_at 생성 (ParseResult가 default_factory로 자동 처리하므로 직접 사용은 안 할 수도 있음) |
| `warnings` | 순환 참조, 파일 없음 경고 |

### 다른 모듈 import 여부

- `pdf_parser.py` — **ParseResult만 import** (`from src.pdf_parser import ParseResult`)
- `config.py` — **import 안 함**. 호출자(main.py)가 경로를 인자로 넘김
- `tree.py` — **import 안 함**

---

## 8. 테스트 전략

- **Claude 호출 할당량: 0** — 이 모듈은 Claude를 전혀 사용하지 않음.
- **테스트 입력**: `data/papers/attention/` (이미 준비됨, .tex 10개 + .sty 1개)
- **확인 항목**:
  1. `\mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V`가 결과 Markdown에 **그대로** 있는지 (수식 보존 확인)
  2. 섹션 구조가 `#`, `##`, `###`로 변환되는지 (ms.tex의 `\section{Introduction}` → `# Introduction`)
  3. `%` 주석이 제거됐는지 (`%\input{parameter_attention}` 같은 주석 처리된 input이 확장되지 않는지)
  4. `\input{...}`이 재귀 확장됐는지 (ms.tex에서 불러지는 서브 파일 내용이 모두 포함되는지 — introduction, background, model_architecture, ... 전체)
  5. 순환 참조가 없는 정상 케이스에서 무한 루프 없는지
  6. title이 `"Attention Is All You Need"`로 정확히 추출됐는지
  7. 프리앰블(`\documentclass`, `\usepackage` 등)이 결과에 포함되지 않는지
- **테스트 실행은 사용자 허락 후**: CLAUDE.md 작업 규칙 3번 준수

---

## 9. 가장 까다로울 것 같은 부분

### ① 수식 환경 내부를 건드리지 않는 것

변환 로직(주석 제거, 서식 변환, 정리 명령 제거 등)이 수식 환경 내부의 `%`, `\text{...}`, `\label{...}` 등을 잘못 변환할 위험이 있다.

예: `\begin{align} x &= y \label{eq:1} \end{align}` 에서 `\label{eq:1}`을 제거하면 수식이 깨짐.

**해결 방향**: 수식 환경(`$...$`, `$$...$$`, `\begin{equation}...\end{equation}`, `\begin{align}...\end{align}` 등)의 시작/끝 위치를 먼저 파악하고, 그 범위 내부는 모든 변환에서 스킵. 구현은 "수식 구간을 placeholder로 치환 → 변환 → placeholder 복원" 패턴이 가장 안전.

### ② 중첩된 `{}` 처리

`\section{Introduction to \textbf{Deep} Learning}` 같은 중첩 브레이스를 정규식만으로 정확히 파싱하기 어렵다. 깊은 중첩은 드물지만, `\footnote{...}` 안에 `\textbf{...}`가 있는 경우 등은 실제로 발생.

**해결 방향**: 단순 정규식 대신 브레이스 카운터를 사용하는 유틸리티 함수 구현. `\cmd{` 이후 `{` 카운트 +1, `}` 카운트 -1로 매칭 `}`를 찾음. 완벽하지는 않지만 실용적으로 충분.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
