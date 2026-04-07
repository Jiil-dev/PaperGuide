# arxiv_parser.py 구현 결과

## 1. 작성된 코드 (src/arxiv_parser.py 전체)

```python
# 단일 책임: arXiv LaTeX 소스 디렉터리를 입력받아, 수식이 LaTeX 원본으로 보존된 Markdown 문자열과 메타데이터를 반환한다.
from __future__ import annotations

import re
import warnings
from pathlib import Path

from src.pdf_parser import ParseResult

# 수식 환경 목록 — 이 환경 내부는 어떤 변환에서도 건드리지 않는다
MATH_ENVIRONMENTS = (
    "equation", "equation*",
    "align", "align*",
    "gather", "gather*",
    "eqnarray", "eqnarray*",
    "multline", "multline*",
)

# 메인 파일 판정에 사용하는 관습적 이름 (우선순위 순서)
_CONVENTIONAL_NAMES = ("main.tex", "ms.tex", "paper.tex", "article.tex")


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _match_braces(text: str, start: int) -> int:
    """text[start]가 '{'일 때, 매칭되는 '}'의 인덱스를 반환한다.

    중첩 브레이스를 카운트해서 정확한 종료 위치를 찾는다.
    매칭 실패 시 -1을 반환한다.
    """
    if start >= len(text) or text[start] != "{":
        return -1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_braced(text: str, start: int) -> tuple[str, int]:
    """text[start]가 '{'일 때, 브레이스 안의 내용과 '}'다음 인덱스를 반환한다.

    Returns:
        (내용, '}'다음 인덱스). 매칭 실패 시 ("", start).
    """
    end = _match_braces(text, start)
    if end == -1:
        return "", start
    return text[start + 1 : end], end + 1


# ---------------------------------------------------------------------------
# 주석 제거
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    """LaTeX 주석을 제거한다. \\%는 보존하고, % 이후 줄 끝까지 제거."""
    # \%를 임시 placeholder로 치환
    text = text.replace("\\%", "\x01ESCAPED_PERCENT\x01")
    # % 이후 줄 끝까지 제거
    text = re.sub(r"%[^\n]*", "", text)
    # placeholder 복원
    text = text.replace("\x01ESCAPED_PERCENT\x01", "\\%")
    return text


# ---------------------------------------------------------------------------
# \input / \include 재귀 확장
# ---------------------------------------------------------------------------

def _expand_inputs(text: str, base_dir: Path, visited: set[str] | None = None) -> str:
    """\\input{filename} 및 \\include{filename}을 재귀적으로 확장한다.

    Args:
        text: LaTeX 소스 텍스트.
        base_dir: .tex 파일들이 있는 디렉터리.
        visited: 순환 참조 감지용 방문 파일 집합.
    """
    if visited is None:
        visited = set()

    def replacer(m: re.Match) -> str:
        filename = m.group(1)
        # 확장자 없으면 .tex 추가
        if not filename.endswith(".tex"):
            filename += ".tex"
        filepath = base_dir / filename
        resolved = str(filepath.resolve())

        if resolved in visited:
            warnings.warn(f"순환 참조 감지, 무시합니다: {filepath}")
            return ""
        if not filepath.exists():
            warnings.warn(f"\\input 파일을 찾을 수 없습니다, 무시합니다: {filepath}")
            return ""

        visited.add(resolved)
        content = filepath.read_text(encoding="utf-8")
        # 서브 파일의 주석도 제거 후 재귀 확장
        content = _strip_comments(content)
        content = _expand_inputs(content, base_dir, visited)
        return content

    # \input{...} 또는 \include{...}
    text = re.sub(r"\\(?:input|include)\{([^}]+)\}", replacer, text)
    return text


# ---------------------------------------------------------------------------
# 메인 파일 판정
# ---------------------------------------------------------------------------

def _find_main_tex(source_dir: Path) -> Path:
    """디렉터리에서 메인 .tex 파일을 판정한다.

    판정 순서:
    1. \\documentclass가 포함된 파일이 정확히 1개면 그 파일
    2. \\documentclass가 2개 이상이면 ValueError
    3. \\documentclass가 없으면 관습적 이름(main.tex, ms.tex, paper.tex, article.tex)
    4. 관습 이름도 없으면 ValueError
    """
    tex_files = list(source_dir.glob("*.tex"))
    if not tex_files:
        raise ValueError(f"디렉터리에 .tex 파일이 없습니다: {source_dir}")

    # \documentclass 포함 파일 검색
    candidates = []
    for f in tex_files:
        head = f.read_text(encoding="utf-8", errors="replace")[:5000]
        if re.search(r"\\documentclass", head):
            candidates.append(f)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = [c.name for c in candidates]
        raise ValueError(
            f"\\documentclass가 있는 파일이 {len(candidates)}개입니다 "
            f"(모호): {names}"
        )

    # 관습적 이름 폴백
    for name in _CONVENTIONAL_NAMES:
        candidate = source_dir / name
        if candidate.exists():
            return candidate

    raise ValueError(
        f"메인 .tex 파일을 판정할 수 없습니다. "
        f"\\documentclass가 있는 파일이 없고, "
        f"main.tex/ms.tex/paper.tex/article.tex도 없습니다: {source_dir}"
    )


# ---------------------------------------------------------------------------
# 수식 보호 / 복원
# ---------------------------------------------------------------------------

def _protect_math(text: str) -> tuple[str, list[str]]:
    """수식 구간을 고유 placeholder로 치환한다.

    인라인($...$, \\(...\\)), 블록($$...$$, \\[...\\]),
    수식 환경(equation, align 등) 내부를 보호.

    Returns:
        (protected_text, math_fragments):
            placeholder는 "\\x00MATH_N\\x00" 형식.
            math_fragments[N]이 원본 수식.
    """
    fragments: list[str] = []

    def _save(m: re.Match) -> str:
        idx = len(fragments)
        fragments.append(m.group(0))
        return f"\x00MATH_{idx}\x00"

    # 1. 블록 수식 환경 (\begin{equation}...\end{equation} 등)
    env_names = "|".join(re.escape(e) for e in MATH_ENVIRONMENTS)
    text = re.sub(
        rf"\\begin\{{({env_names})\}}(.*?)\\end\{{\1\}}",
        _save,
        text,
        flags=re.DOTALL,
    )

    # 2. $$...$$ (블록 수식, $...$보다 먼저 처리)
    text = re.sub(r"\$\$(.+?)\$\$", _save, text, flags=re.DOTALL)

    # 3. \[...\] (블록 수식)
    text = re.sub(r"\\\[(.+?)\\\]", _save, text, flags=re.DOTALL)

    # 4. $...$ (인라인 수식, 줄 바꿈 불포함)
    text = re.sub(r"\$([^\$\n]+?)\$", _save, text)

    # 5. \(...\) (인라인 수식)
    text = re.sub(r"\\\((.+?)\\\)", _save, text)

    return text, fragments


def _restore_math(text: str, fragments: list[str]) -> str:
    """placeholder를 원본 수식으로 복원한다."""
    for i, frag in enumerate(fragments):
        text = text.replace(f"\x00MATH_{i}\x00", frag)
    return text


# ---------------------------------------------------------------------------
# LaTeX → Markdown 변환
# ---------------------------------------------------------------------------

def _extract_title(text: str) -> tuple[str, str]:
    """\\title{...}에서 제목을 추출하고 본문에서 제거한다.

    Returns:
        (title, text_without_title). title이 없으면 빈 문자열.
    """
    title = ""
    m = re.search(r"\\title\{", text)
    if m:
        content, end = _extract_braced(text, m.end() - 1)
        title = content.strip()
        text = text[: m.start()] + text[end:]
    return title, text


def _remove_preamble(text: str) -> str:
    """프리앰블(\\documentclass부터 \\begin{document}까지)을 제거한다."""
    m = re.search(r"\\begin\{document\}", text)
    if m:
        text = text[m.end() :]
    # \end{document} 이후 제거
    m = re.search(r"\\end\{document\}", text)
    if m:
        text = text[: m.start()]
    return text


def _convert_sections(text: str) -> str:
    """섹션 명령을 Markdown 헤더로 변환한다."""
    section_map = {
        "section": "#",
        "subsection": "##",
        "subsubsection": "###",
    }
    for cmd, md_level in section_map.items():
        pattern = rf"\\{cmd}\*?\{{"
        while True:
            m = re.search(pattern, text)
            if not m:
                break
            brace_start = m.end() - 1
            content, end = _extract_braced(text, brace_start)
            # \label{...}이 같은 줄에 붙어있을 수 있음 — 제거
            rest_of_line = ""
            label_m = re.match(r"\s*\\label\{[^}]*\}", text[end:])
            if label_m:
                end += label_m.end()
            text = text[: m.start()] + f"\n{md_level} {content.strip()}\n" + text[end:]

    # \paragraph{X} → **X**
    while True:
        m = re.search(r"\\paragraph\*?\{", text)
        if not m:
            break
        brace_start = m.end() - 1
        content, end = _extract_braced(text, brace_start)
        text = text[: m.start()] + f"\n**{content.strip()}**\n" + text[end:]

    return text


def _convert_abstract(text: str) -> str:
    """abstract 환경을 Markdown으로 변환한다."""
    # \begin{abstract}...\end{abstract}
    text = re.sub(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
        lambda m: f"\n## Abstract\n\n{m.group(1).strip()}\n",
        text,
        flags=re.DOTALL,
    )
    # \abstract{...} 매크로 형태
    m = re.search(r"\\abstract\{", text)
    if m:
        content, end = _extract_braced(text, m.end() - 1)
        text = text[: m.start()] + f"\n## Abstract\n\n{content.strip()}\n" + text[end:]
    return text


def _convert_formatting(text: str) -> str:
    """텍스트 서식 명령을 Markdown으로 변환한다."""
    formatting = {
        "textbf": ("**", "**"),
        "textit": ("*", "*"),
        "emph": ("*", "*"),
        "texttt": ("`", "`"),
    }
    for cmd, (pre, post) in formatting.items():
        pattern = rf"\\{cmd}\{{"
        while True:
            m = re.search(pattern, text)
            if not m:
                break
            brace_start = m.end() - 1
            content, end = _extract_braced(text, brace_start)
            text = text[: m.start()] + f"{pre}{content}{post}" + text[end:]
    return text


def _convert_lists(text: str) -> str:
    """itemize/enumerate 환경을 Markdown 리스트로 변환한다."""
    # itemize → - 리스트
    def _itemize_to_md(m: re.Match) -> str:
        body = m.group(1)
        body = re.sub(r"\\item\b\s*", "\n- ", body)
        return body

    text = re.sub(
        r"\\begin\{itemize\}(.*?)\\end\{itemize\}",
        _itemize_to_md,
        text,
        flags=re.DOTALL,
    )

    # enumerate → 1. 리스트
    def _enum_to_md(m: re.Match) -> str:
        body = m.group(1)
        counter = [0]
        def _numbered(item_m: re.Match) -> str:
            counter[0] += 1
            return f"\n{counter[0]}. "
        body = re.sub(r"\\item\b\s*", _numbered, body)
        return body

    text = re.sub(
        r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}",
        _enum_to_md,
        text,
        flags=re.DOTALL,
    )

    return text


def _convert_references(text: str) -> str:
    """참조/인용 명령을 변환한다."""
    # \cite{key}, \citep{key}, \citet{key} → [key]
    text = re.sub(r"\\cite[pt]?\{([^}]+)\}", r"[\1]", text)
    # \ref{label} → [ref:label]
    text = re.sub(r"\\ref\{([^}]+)\}", r"[ref:\1]", text)
    # \eqref{label} → [eq:label]
    text = re.sub(r"\\eqref\{([^}]+)\}", r"[eq:\1]", text)
    # \url{...} → URL 그대로
    text = re.sub(r"\\url\{([^}]+)\}", r"\1", text)
    return text


def _convert_figures(text: str) -> str:
    """figure 환경을 [그림 생략]으로 변환한다."""
    text = re.sub(
        r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}",
        "\n[그림 생략]\n",
        text,
        flags=re.DOTALL,
    )
    # 단독 \includegraphics
    text = re.sub(
        r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}",
        r"[그림: \1]",
        text,
    )
    return text


def _convert_footnotes(text: str) -> str:
    """\\footnote{...}를 본문 괄호 삽입으로 변환한다."""
    pattern = r"\\footnote\{"
    while True:
        m = re.search(pattern, text)
        if not m:
            break
        brace_start = m.end() - 1
        content, end = _extract_braced(text, brace_start)
        text = text[: m.start()] + f" (각주: {content})" + text[end:]
    return text


def _cleanup_commands(text: str) -> str:
    """남은 LaTeX 명령을 정리한다."""
    # 제거할 명령들 (인자 없는 것)
    text = re.sub(r"\\maketitle\b", "", text)
    text = re.sub(r"\\centering\b", "", text)
    text = re.sub(r"\\noindent\b", "", text)
    text = re.sub(r"\\newpage\b", "", text)
    text = re.sub(r"\\clearpage\b", "", text)
    text = re.sub(r"\\bigskip\b", "", text)
    text = re.sub(r"\\medskip\b", "", text)
    text = re.sub(r"\\smallskip\b", "", text)
    text = re.sub(r"\\vspace\*?\{[^}]*\}", "", text)
    text = re.sub(r"\\hspace\*?\{[^}]*\}", "", text)

    # \label{...} 제거
    text = re.sub(r"\\label\{[^}]*\}", "", text)

    # \author{...} 제거 (중첩 브레이스 가능)
    m = re.search(r"\\author\{", text)
    if m:
        _, end = _extract_braced(text, m.end() - 1)
        text = text[: m.start()] + text[end:]

    # \newcommand, \renewcommand, \def 제거
    text = re.sub(r"\\(?:re)?newcommand\*?\\[a-zA-Z]+(?:\[[^\]]*\])?\{[^}]*\}", "", text)
    # 더 복잡한 \newcommand (중첩 브레이스) — 한 줄씩 제거
    text = re.sub(r"\\(?:re)?newcommand\b.*?\n", "\n", text)
    text = re.sub(r"\\def\\[a-zA-Z]+\{[^}]*\}", "", text)

    # \bibliography{...}, \bibliographystyle{...} 제거
    text = re.sub(r"\\bibliography(?:style)?\{[^}]*\}", "", text)

    # \begin{center}...\end{center} — 내용만 남김
    text = re.sub(r"\\begin\{center\}", "", text)
    text = re.sub(r"\\end\{center\}", "", text)

    # \begin{table}...\end{table} — 그대로 보존 (Claude가 읽을 수 있음)

    # \color{...} 제거
    text = re.sub(r"\\color\{[^}]*\}", "", text)

    # \large, \small 등 크기 명령 제거
    text = re.sub(r"\\(?:tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)\b", "", text)

    # ~(non-breaking space) → 일반 공백
    text = text.replace("~", " ")

    # \\ → 줄바꿈 (수식 외부에서)
    # 주의: 수식 내부의 \\는 이미 보호됨
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", text)

    # \% → %
    text = text.replace("\\%", "%")

    return text


def _cleanup_unknown_commands(text: str) -> str:
    """알 수 없는 \\cmd{X} 형태에서 콘텐츠 X만 남긴다."""
    pattern = r"\\[a-zA-Z]+\{"
    while True:
        m = re.search(pattern, text)
        if not m:
            break
        brace_start = m.end() - 1
        content, end = _extract_braced(text, brace_start)
        text = text[: m.start()] + content + text[end:]
    return text


def _cleanup_whitespace(text: str) -> str:
    """연속 빈 줄을 최대 2줄로 정리한다."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

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
    if not source_dir.exists():
        raise FileNotFoundError(f"디렉터리를 찾을 수 없습니다: {source_dir}")
    if not source_dir.is_dir():
        raise ValueError(f"디렉터리가 아닙니다: {source_dir}")

    main_tex = _find_main_tex(source_dir)
    raw = main_tex.read_text(encoding="utf-8")

    # 1. 주석 제거
    text = _strip_comments(raw)

    # 2. \input / \include 재귀 확장
    visited = {str(main_tex.resolve())}
    text = _expand_inputs(text, source_dir, visited)

    # 3. \title 추출 (프리앰블 제거 전에 — title은 프리앰블에 있음)
    title, text = _extract_title(text)

    # 4. 프리앰블 제거
    text = _remove_preamble(text)

    # 5. 수식 보호
    text, math_fragments = _protect_math(text)

    # 6. 구조 변환
    text = _convert_abstract(text)
    text = _convert_sections(text)
    text = _convert_figures(text)
    text = _convert_footnotes(text)
    text = _convert_formatting(text)
    text = _convert_lists(text)
    text = _convert_references(text)

    # 7. 명령 정리
    text = _cleanup_commands(text)
    text = _cleanup_unknown_commands(text)

    # 8. 수식 복원
    text = _restore_math(text, math_fragments)

    # 9. 빈 줄 정리
    text = _cleanup_whitespace(text)

    # title 폴백
    if not title:
        title = source_dir.name

    return ParseResult(
        markdown=text,
        source_path=source_dir,
        page_count=0,
        title=title,
    )
```

## 2. 검증 결과

### 2-1. import 테스트

```
$ .venv/bin/python -c "from src.arxiv_parser import parse_arxiv; from src.pdf_parser import ParseResult; print('import OK')"
import OK
```

### 2-2. 파싱 기본 정보

```
title: Attention Is All You Need
page_count: 0
markdown length: 41402
```

- title이 `\title{Attention Is All You Need}`에서 정확히 추출됨
- page_count가 0으로 고정됨 (TeX 소스에는 페이지 개념 없음)

### 2-3. 핵심 수식 확인 (Attention 공식 주변)

```
set of queries simultaneously, packed together into a matrix $Q$.   The keys and values are also packed together into matrices $K$ and $V$.  We compute the matrix of outputs as:

\begin{equation}
   \mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V
\end{equation}

The two most commonly used attention functions are additive attention [bahdanau2014neural], and dot-product (multiplicative) attention.  Dot-product attention is identical to our algorithm, except for the scaling factor of $\frac{1}{\sqrt{d_k}}$.
```

**수식 완벽 보존 확인.** `\begin{equation}...\end{equation}` 블록과 인라인 `$...$` 수식 모두 원본 그대로.

### 2-4. 수식 환경 카운트

```
\begin{equation} 개수: 3
$ 개수: 266
\frac 개수: 3
\sqrt 개수: 5
```

### 2-5. 섹션 구조 (처음 20개 헤더)

```
총 헤더 개수: 24
  ## Abstract
  # Introduction
  # Background
  # Model Architecture
  ## Encoder and Decoder Stacks
  ## Attention
  ### Scaled Dot-Product Attention
  ### Multi-Head Attention
  ### Applications of Attention in our Model
  ## Position-wise Feed-Forward Networks
  ## Embeddings and Softmax
  ## Positional Encoding
  # Why Self-Attention
  # Training
  ## Training Data and Batching
  ## Hardware and Schedule
  ## Optimizer
  ## Regularization
  # Results
  ## Machine Translation
```

`\section` → `#`, `\subsection` → `##`, `\subsubsection` → `###` 변환 정상. `\begin{abstract}` → `## Abstract` 변환도 정상.

### 2-6. 주석 제거 확인

```
OK: 주석 처리된 input은 확장되지 않음
OK: sqrt_d_trick 주석 처리된 input도 확장되지 않음
OK: documentclass 제거됨
OK: usepackage 제거됨
```

ms.tex의 `%\input{parameter_attention}`과 `%\input{sqrt_d_trick}`이 올바르게 무시됨.

### 2-7. 에러 테스트

```
$ .venv/bin/python -c "from pathlib import Path; from src.arxiv_parser import parse_arxiv; parse_arxiv(Path('nonexistent_dir'))"
FileNotFoundError: 디렉터리를 찾을 수 없습니다: nonexistent_dir

$ .venv/bin/python -c "from pathlib import Path; from src.arxiv_parser import parse_arxiv; parse_arxiv(Path('src'))"
ValueError: 디렉터리에 .tex 파일이 없습니다: src
```

한국어 에러 메시지 정상.

## 3. 구현 중 주의했던 점

1. **수식 보호 패턴 (`_protect_math` / `_restore_math`)**: null 문자(`\x00`)를 사용한 placeholder `\x00MATH_N\x00`로 수식 구간을 보호. 실제 LaTeX에 null 문자가 나타날 수 없으므로 정규식 오매칭 위험 없음. 블록 수식 환경 → `$$` → `\[...\]` → `$` → `\(...\)` 순서로 처리하여 큰 단위부터 보호.

2. **주석 제거 → input 확장 순서**: ms.tex에 `%\input{parameter_attention}` 같은 주석 처리된 input이 있어서, 주석을 먼저 제거한 뒤 input을 확장해야 함. 서브 파일의 주석도 `_expand_inputs` 내에서 재귀적으로 제거.

3. **브레이스 카운터 (`_match_braces`)**: `\section{Introduction to \textbf{Deep} Learning}` 같은 중첩 브레이스를 정확히 매칭. 정규식의 `{[^}]*}`로는 처리 불가능한 케이스를 카운터 방식으로 해결.

4. **\title 추출 시점**: 프리앰블 제거 전에 `\title{...}`을 추출해야 함. `\title`은 프리앰블에 위치하므로 `_remove_preamble` 이후에는 접근 불가.

5. **MATH_ENVIRONMENTS 상수**: 보정에서 지시한 10개 수식 환경(equation, equation*, align, align*, gather, gather*, eqnarray, eqnarray*, multline, multline*)을 모두 포함. 인라인 수식(`$...$`, `\(...\)`)과 블록 수식(`$$...$$`, `\[...\]`)도 별도 처리.

6. **_cleanup_unknown_commands의 while 루프**: `\cmd{X}` 패턴을 반복 제거하여 중첩된 알 수 없는 명령도 처리. 수식 내부는 이미 placeholder로 보호되어 있어 안전.

## 4. 발견된 이슈

1. **`\cite{key}` → `[key]` 변환에서 쉼표 구분 인용**: `\cite{a,b,c}` 형태의 다중 인용이 `[a,b,c]`로 변환됨. 개별 `[a]`, `[b]`, `[c]`로 분리하지 않았지만, Claude가 이해하는 데 문제 없을 것으로 판단.

2. **`\dmodel` 등 사용자 정의 매크로**: ms.tex 프리앰블에 `\newcommand{\dmodel}{d_{\text{model}}}` 등이 정의되어 있으나, 현재는 매크로 확장을 지원하지 않음. 본문에서 `\dmodel`이 사용된 곳은 `_cleanup_unknown_commands`에 의해 빈 문자열로 대체될 수 있음. 단, 대부분의 수식 내부에서 사용되므로 수식 보호에 의해 원본 유지됨.

3. **table 환경의 `\begin{table}...\end{table}`**: 설계대로 그대로 보존. `\begin{tabular}` 등 내부 LaTeX는 Claude가 읽을 수 있으므로 무리하게 Markdown table로 변환하지 않음.
