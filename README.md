# PaperGuide

> Turn AI research papers into a complete Korean guidebook that an undergraduate freshman can read like a book.

PaperGuide is a Python pipeline that transforms academic AI papers into comprehensive, top-down Korean explanations structured as a 3-part guidebook. Unlike typical paper summarizers, PaperGuide writes from the **author's perspective**, preserves the **flow of reading**, and treats prerequisite knowledge as **standalone deep explanations** rather than shallow inline definitions.

**Built with Claude Code. Runs on Claude Code.** No Anthropic API key required — uses your existing Claude Max/Pro subscription via the `claude` CLI.

---

## What makes PaperGuide different

Most paper summarizers give you bullet points or a brief abstract. PaperGuide writes a **book**. Specifically:

- **Top-down, author-centric**: Every section is explained as "what the author argues here," not as a generic textbook. PaperGuide analyzes the author's word choices, rhetorical structure, and argumentative strategy.
- **Reading flow preserved**: Basic concepts (RNN, softmax, matrix multiplication, ...) are linked to a separate Part 3 instead of being explained inline. The main text never gets interrupted by 3-paragraph definitions of prerequisites.
- **Deep prerequisites**: Part 3 covers each prerequisite topic in enough depth that an undergraduate freshman can actually understand it — not a one-line glossary.
- **3-part structure**:
  - **Part 1 (10–15%)**: The big picture — what the paper claims, why it matters, how to read the rest.
  - **Part 2 (70–80%)**: Walking through the paper section by section, from the author's point of view.
  - **Part 3 (15–20%)**: Self-contained explanations of every prerequisite concept needed to understand Part 2.

## Example output

A complete guidebook for the "Attention Is All You Need" paper (mini version, Abstract + Introduction only) is in [`examples/`](examples/). It is approximately 2,000 lines of Korean explanation, with the author's design choices and rhetorical strategy analyzed in detail.

## Requirements

- **Python 3.12+**
- **Claude Code CLI** (`claude` command) installed and authenticated
  - Requires a Claude Max or Claude Pro subscription
  - Install: see [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code)
  - Authenticate: `claude login`
- **Linux / macOS / WSL** (tested on WSL Ubuntu)

## Installation

```bash
# 1. Clone
git clone https://github.com/Jiil-dev/PaperGuide.git
cd PaperGuide

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify Claude Code CLI is available
claude --version
```

## Quick start

Place your paper in `data/papers/<paper_name>/` (either an arXiv source folder with `.tex` files, or put the PDF directly in the folder).

```bash
.venv/bin/python -m src.main \
    --input data/papers/your_paper \
    --output samples/your_paper_guidebook.md \
    --mode cache \
    --cache-dir data/cache_your_paper \
    --phase 3
```

The result will be a single Markdown file containing the complete 3-part guidebook in Korean.

### Modes

| Mode | Description | When to use |
|------|-------------|-------------|
| `--mode live` | Make real Claude Code calls | Production runs |
| `--mode cache` | Use disk-cached responses if available, fall back to live | Re-runs (recommended) |
| `--mode dry_run` | No Claude calls, returns schema-default values | Development |

### Why a separate `--cache-dir` per paper

Different papers should not share their concept caches. Use a unique cache directory per paper to avoid cross-contamination.

## Output structure

The generated Markdown follows this structure:

```
# <Paper Title> — 완전판 가이드북

## Part 1. 논문이 무엇을 주장하는가 — 큰 그림
### 1.1 핵심 주장
### 1.2 해결하려는 문제
### 1.3 핵심 기여
### 1.4 주요 결과
### 1.5 이 논문의 의의
### 1.6 이 가이드북 읽는 법

## Part 2. 논문 따라 읽기 — 완전 해설
### 2.1 Abstract
    #### 2.1.1 ...
### 2.2 Introduction
    ...
(each paper section, recursively expanded up to depth 2)

## Part 3. 기초 지식 탄탄히
### 3.1 <prerequisite topic 1>
### 3.2 <prerequisite topic 2>
...
```

Headers are limited to Markdown Level 5 (`#####`) to preserve a "book reading" experience rather than a specification document.

## Configuration

Edit `config.yaml` to adjust generation parameters:

```yaml
part2:
  max_depth: 2          # Maximum nesting depth for Part 2 (header levels 3-5)
  max_children_per_node: 5

part3:
  max_topics: 15
  predefined_pool: [...]   # Common prerequisites Claude can pick from
  allow_claude_to_add: true

verification:
  min_confidence: 0.7    # Minimum verifier confidence to accept a node
  max_retries: 1

claude:
  max_total_calls: 1500  # Hard cap on Claude calls per run
  sleep_between_calls: 3
```

## How it works

PaperGuide is a 7-stage pipeline:

1. **Parse** — Extract markdown from arXiv tex sources or PDFs
2. **Analyze (Part 1)** — Generate the big-picture summary
3. **Chunk** — Split the paper into raw sections
4. **Expand (Part 2)** — Recursively generate top-down explanations for each section
5. **Collect prerequisites** — Gather every `[[REF:topic_id]]` placeholder mentioned in Part 2
6. **Write Part 3** — Generate a standalone explanation for each prerequisite topic
7. **Assemble** — Render the final 3-part Markdown, resolving all placeholders

All Claude calls go through `claude_client.py`, which calls the local `claude -p` CLI with JSON schema enforcement.

## Project status

- ✅ Phase 3 complete (top-down, flow-preserving, 3-part guidebook generation)
- 🧪 Tested on the "Attention Is All You Need" mini paper (Abstract + Introduction)
- 📋 Future work: full paper testing, multi-paper batch mode, custom prerequisite pools

## Documentation

- Korean README: [README_KR.md](README_KR.md)
- Development docs (design decisions, iteration history): [docs/development/](docs/development/)

## License

MIT — see [LICENSE](LICENSE)

## Acknowledgments

Built with [Claude Code](https://claude.ai/code). The entire development process — from architecture design to debugging — was conducted in collaboration with Claude.
