# pdf_parser.py 커밋 결과

## 1. git status (커밋 전)

```
On branch master
Changes not staged for commit:
	modified:   HANDOFF.md

Untracked files:
	docs/pdf_parser_py_design_20260408.md
	docs/pdf_parser_py_formula_test_20260408.md
	docs/pdf_parser_py_implementation_20260408.md
	docs/tree_py_commit_20260408.md
	src/pdf_parser.py
```

- `data/papers/attention/` (TeX 소스 11개 파일)은 `.gitignore`에 의해 제외됨 확인

## 2. git add (명시적 스테이징)

```
$ git add src/pdf_parser.py docs/pdf_parser_py_design_20260408.md docs/pdf_parser_py_implementation_20260408.md docs/pdf_parser_py_formula_test_20260408.md docs/tree_py_commit_20260408.md HANDOFF.md
```

## 3. git status (스테이징 후)

```
On branch master
Changes to be committed:
	modified:   HANDOFF.md
	new file:   docs/pdf_parser_py_design_20260408.md
	new file:   docs/pdf_parser_py_formula_test_20260408.md
	new file:   docs/pdf_parser_py_implementation_20260408.md
	new file:   docs/tree_py_commit_20260408.md
	new file:   src/pdf_parser.py
```

- 6개 파일만 스테이징됨
- data/ 경로 파일 포함되지 않음

## 4. git commit

```
$ git commit -m "feat(pdf_parser): add PDF to Markdown parser via pymupdf4llm

- Add src/pdf_parser.py with ParseResult dataclass
- extracted_at uses datetime (not string)
- doc.close() guaranteed via try/finally
- Encrypted PDFs rejected with Korean error message
- Verified on distillation.pdf (9 pages, text-only, works)
- Formula preservation test on attention.pdf FAILED:
  core equations rendered as images, extracted as
  \"picture [W x H] intentionally omitted\" placeholders
- arXiv TeX source verified to preserve LaTeX formulas perfectly
- Decision: keep pdf_parser as fallback for text-only papers,
  add arxiv_parser (next) for formula-heavy arXiv papers
- HANDOFF.md updated with parser strategy section"

[master 6086e8b] feat(pdf_parser): add PDF to Markdown parser via pymupdf4llm
 6 files changed, 753 insertions(+)
 create mode 100644 docs/pdf_parser_py_design_20260408.md
 create mode 100644 docs/pdf_parser_py_formula_test_20260408.md
 create mode 100644 docs/pdf_parser_py_implementation_20260408.md
 create mode 100644 docs/tree_py_commit_20260408.md
 create mode 100644 src/pdf_parser.py
```

## 5. git log --oneline (커밋 후)

```
6086e8b feat(pdf_parser): add PDF to Markdown parser via pymupdf4llm
7fddafc chore: add previous commit record and git commit rule
9e7f35e feat(tree): add ConceptNode dataclass and DFS traversal helpers
cc2c80d feat(config): add Pydantic-based config loader
b4ad53b chore: initial project setup with CLAUDE.md, HANDOFF.md, config, and dependencies
```

5개 커밋 정상 확인.
