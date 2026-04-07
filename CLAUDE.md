# Paper Analyzer — Project Constitution

## 프로젝트 목적
AI 분야 논문 PDF를 입력받아, 학부 1학년이 이해할 수 있는 수준까지 
재귀적 top-down 설명을 생성하는 프로그램. 최종 산출물은 한 권의 책 
형태의 Markdown 가이드북.

## 절대 규칙 (NEVER 위반 금지)
1. **Anthropic API를 절대 사용하지 마라.** `anthropic` Python SDK, 
   `httpx`로 api.anthropic.com 호출, API 키 사용 — 모두 금지.
2. Claude 모델 호출은 오직 `subprocess`로 `claude -p` CLI를 부르는 
   방식으로만 한다. (Max 구독 할당량으로만 동작해야 함)
3. 모든 Claude 호출은 `--output-format json --json-schema ...`로 
   구조화 출력을 강제한다. 자유 텍스트 파싱 금지.
4. 실험적이거나 확실하지 않은 라이브러리를 임의로 추가하지 마라. 
   추가 전에 반드시 사용자에게 묻는다.
5. 한 번에 여러 파일을 동시에 만들지 마라. 한 파일씩, 합의 후 다음.

## 목표 독자 수준 (시스템 프롬프트에 항상 반영)
학부 1학년. 배경지식: 고등학교 수학2(미적분 기초), 고등학교 물리1,
기초 프로그래밍. 선형대수·확률·머신러닝·딥러닝 전혀 모름.

## 기술 스택 (고정)
- Python 3.10+
- PDF 파싱: pymupdf4llm (수식 깨지면 marker-pdf로 교체 검토)
- 임베딩: sentence-transformers (all-MiniLM-L6-v2)
- 재시도: tenacity
- 로깅: rich
- 설정: PyYAML
- 데이터 검증: pydantic v2

## 폴더 구조 (고정)
```
paper-analyzer/
├── CLAUDE.md
├── config.yaml
├── requirements.txt
├── .gitignore
├── data/{papers,cache,output}/
├── checkpoints/
└── src/
    ├── config.py
    ├── pdf_parser.py
    ├── chunker.py
    ├── tree.py
    ├── concept_cache.py
    ├── claude_client.py
    ├── expander.py
    ├── verifier.py
    ├── checkpoint.py
    ├── assembler.py
    └── main.py
```

## 핵심 알고리즘
1. PDF → Markdown 변환 (수식 LaTeX 보존)
2. 마크다운 헤더 기준으로 루트 섹션 노드 생성
3. 각 노드를 DFS로 재귀 확장:
   - Claude에게 "설명 + 하위 개념 목록 + leaf 판정" 요청 (JSON 강제)
   - 중복 차단: ① 정규화 이름 해시 ② 임베딩 코사인 유사도 ≥ 0.88 
     ③ 조상 경로 순환 체크
   - 자기검증: 별도 Claude 호출로 hallucination/omission/contradiction/
     math_error 검사. 실패 시 오류 지적을 다음 생성에 피드백.
   - leaf 판정 또는 max_depth=6 도달 시 종료
4. 트리 → DFS 순회로 Markdown 책 직렬화

## 작업 규칙 (Claude가 따라야 할 메타 규칙)
1. 새 파일을 만들기 전에 항상 그 파일의 책임과 인터페이스를 먼저 
   한국어로 요약해서 사용자에게 제시하고 OK를 받아라.
2. 코드를 작성한 직후 항상 `python -c "import src.<모듈>"`로 
   import 테스트를 돌려라. 실패하면 스스로 고쳐라.
3. 외부 호출(Claude CLI, 모델 다운로드)이 필요한 테스트는 사용자에게 
   먼저 "지금 돌려도 되나?" 묻고 진행해라.
4. 의미 있는 단위가 끝날 때마다 git commit을 제안해라.
5. 모르는 것이 있으면 추측하지 말고 물어라. 특히 사용자의 의도가 
   조금이라도 모호하면 반드시 질문해라.

## 절대 만들지 말 것
- 단위 테스트 프레임워크(pytest 등) — 지금 단계에서는 과잉
- Docker/CI — 지금 단계에서는 과잉  
- 웹 UI — 지금 단계에서는 과잉
- README.md — 마지막에 한 번에 만든다

## 파일 내용 보고 규칙
사용자가 "파일 내용을 보여줘"라고 요청하면, 반드시 `cat` 또는 파일 
읽기 도구의 원본 출력을 그대로 제시한다. 요약, 체크리스트, 섹션별 
OK 판정으로 대체하지 않는다.

## 답변 저장 규칙
사용자가 긴 결과(코드, 검증 출력, 설계안 등)를 요청하면, 반드시 
docs/ 폴더 아래에 마크다운 파일로 저장한다. 파일명 규칙은 
docs/<모듈명>_<단계>_<YYYYMMDD>.md. 저장 후 사용자에게는 
"저장 완료: <경로>" 한 줄만 보고하고 채팅에 내용 반복 금지.
단, 짧은 확인/상태 보고(예: "import OK", 한 줄 결과)는 그대로 채팅에 출력.