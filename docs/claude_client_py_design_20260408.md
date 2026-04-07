# src/claude_client.py 설계

## 1. 모듈 책임 (한 줄)

**subprocess로 `claude -p` CLI를 호출하고, JSON schema로 구조화 출력을 강제하며, live/cache/dry_run 3가지 모드를 지원하는 래퍼.**

---

## 2. 클래스 ClaudeClient 전체 인터페이스

### 파일 상단 상수

```python
CLAUDE_CLIENT_VERSION = "1"
# 프롬프트 템플릿이나 스키마 구조를 변경할 때 +1로 올려서
# 캐시를 일괄 무효화한다. 코드 변경 없이 캐시만 교체하는 효과.
```

### 커스텀 예외

```python
class RateLimitExceeded(Exception):
    """live 호출 수가 max_total_calls를 초과했을 때 발생."""
```

### 생성자

```python
class ClaudeClient:
    def __init__(
        self,
        mode: Literal["live", "cache", "dry_run"],
        cli_path: str = "claude",
        max_total_calls: int = 500,
        timeout_seconds: int = 600,
        sleep_between_calls: int = 3,
        cache_dir: Path | None = None,
    ):
        """Claude CLI 래퍼.

        Args:
            mode: 동작 모드.
                - "live": 실제 claude -p 호출.
                - "cache": SHA-256 해시 기반 디스크 캐시. 미스 시 live 호출 후 저장.
                - "dry_run": 실제 호출 없이 schema 기본값으로 가짜 응답.
            cli_path: claude CLI 실행 경로.
            max_total_calls: live 호출 상한. 초과 시 RateLimitExceeded.
            timeout_seconds: subprocess 타임아웃 (초).
            sleep_between_calls: live 호출 간 대기 (초).
            cache_dir: cache 모드에서 사용할 디렉터리.
                mode="cache"일 때 필수. {cache_dir}/claude_responses/<hash>.json에 저장.
        """
```

### 내부 상태

| 필드 | 타입 | 설명 |
|------|------|------|
| `_mode` | str | "live" / "cache" / "dry_run" |
| `_cli_path` | str | claude CLI 경로 |
| `_max_total_calls` | int | live 호출 상한 |
| `_timeout` | int | subprocess 타임아웃 (초) |
| `_sleep` | int | 호출 간 대기 (초) |
| `_cache_dir` | Path \| None | 캐시 디렉터리 |
| `_live_calls` | int | live 호출 횟수 (상한 체크용) |
| `_cache_hits` | int | 캐시 히트 횟수 |
| `_cache_misses` | int | 캐시 미스 횟수 |
| `_dry_run_calls` | int | dry_run 호출 횟수 |

### 공개 메서드

```python
def call(
    self,
    user_prompt: str,
    system_prompt: str,
    json_schema: dict,
) -> dict:
    """claude -p를 호출하고 structured output을 dict로 반환한다.

    Args:
        user_prompt: 사용자 프롬프트.
        system_prompt: 시스템 프롬프트.
        json_schema: JSON Schema dict. 구조화 출력을 강제.

    Returns:
        dict: structured_output 파싱 결과.

    Raises:
        RateLimitExceeded: live 호출 수가 상한을 초과했을 때.
        RuntimeError: subprocess 실패 또는 JSON 파싱 실패 (재시도 소진 후).
    """

def get_stats(self) -> dict:
    """호출 통계를 반환한다.

    Returns:
        {"total_calls": int, "cache_hits": int, "cache_misses": int, "dry_run_calls": int}
    """
```

### 내부 헬퍼

```python
def _compute_cache_key(self, user_prompt: str, system_prompt: str, json_schema: dict) -> str:
    """캐시 해시 (SHA-256)를 계산한다."""

def _call_live(self, user_prompt: str, system_prompt: str, json_schema: dict) -> dict:
    """실제 subprocess 호출. tenacity 재시도 포함."""

def _call_cached(self, user_prompt: str, system_prompt: str, json_schema: dict) -> dict:
    """캐시 조회 → 히트면 반환, 미스면 _call_live 후 저장."""

def _call_dry_run(self, json_schema: dict) -> dict:
    """schema에서 기본값 생성."""

def _generate_defaults(self, schema: dict) -> Any:
    """JSON schema를 재귀 순회하며 타입별 기본값을 채운다."""

def _parse_cli_output(self, stdout: str) -> dict:
    """CLI stdout에서 structured_output을 추출한다."""
```

---

## 3. 3가지 모드의 call() 흐름

### mode="live"

```
1. _live_calls >= _max_total_calls → raise RateLimitExceeded
2. _call_live(user_prompt, system_prompt, json_schema)
   a. subprocess.run(["claude", "-p", user_prompt,
        "--system-prompt", system_prompt,
        "--output-format", "json",
        "--json-schema", json.dumps(json_schema),
        "--bare"],
        capture_output=True, text=True, timeout=_timeout)
   b. returncode != 0 → 재시도 (tenacity)
   c. stdout → JSON 파싱 → structured_output 추출
   d. JSON 파싱 실패 → 재시도
3. _live_calls += 1
4. time.sleep(_sleep)
5. return result
```

### mode="cache"

```
1. cache_key = _compute_cache_key(...)
2. cache_path = _cache_dir / "claude_responses" / f"{cache_key}.json"
3. cache_path 존재 → json.loads(cache_path.read_text())
   a. 파싱 성공 → _cache_hits += 1, return result
   b. 파싱 실패 (손상) → 무시, live 폴백
4. 캐시 미스 또는 손상 →
   a. _live_calls >= _max_total_calls → raise RateLimitExceeded
   b. result = _call_live(...)
   c. cache_path.write_text(json.dumps(result, ensure_ascii=False))
   d. _cache_misses += 1, _live_calls += 1
   e. return result
```

### mode="dry_run"

```
1. result = _call_dry_run(json_schema)
2. _dry_run_calls += 1
3. return result  (live_calls 증가 안 함, 상한 체크 안 함)
```

---

## 4. 캐시 해시 생성 로직

```python
def _compute_cache_key(self, user_prompt, system_prompt, json_schema):
    raw = (
        system_prompt
        + user_prompt
        + json.dumps(json_schema, sort_keys=True)
        + CLAUDE_CLIENT_VERSION
    )
    return hashlib.sha256(raw.encode()).hexdigest()
```

HANDOFF.md §3-2 그대로:
- SHA-256
- 4개 입력: system_prompt, user_prompt, json_schema(sort_keys), CLAUDE_CLIENT_VERSION
- 결과: 64자 hex 문자열

---

## 5. subprocess 호출 + stdout 파싱

### 호출 명령

```python
cmd = [
    self._cli_path, "-p", user_prompt,
    "--system-prompt", system_prompt,
    "--output-format", "json",
    "--json-schema", json.dumps(json_schema),
    "--bare",
]
proc = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=self._timeout,
)
```

`--bare` 사용 이유: hooks, LSP, CLAUDE.md auto-discovery 등을 건너뛰어 순수 API 호출만 수행. 우리 프로젝트의 CLAUDE.md가 호출에 영향을 주면 안 됨.

### stdout 파싱

CLI의 `--output-format json` 출력 형식:

```json
{
  "type": "result",
  "subtype": "success",
  "result": "...",
  "structured_output": { ... },
  ...
}
```

파싱 로직:

```python
def _parse_cli_output(self, stdout: str) -> dict:
    data = json.loads(stdout)

    # structured_output 우선
    if "structured_output" in data and data["structured_output"] is not None:
        return data["structured_output"]

    # 폴백: result 문자열을 JSON 파싱 시도
    if "result" in data and isinstance(data["result"], str):
        return json.loads(data["result"])

    raise ValueError("structured_output도 result도 파싱할 수 없습니다")
```

### is_error 체크

```python
if data.get("is_error"):
    error_msg = data.get("result", "알 수 없는 에러")
    raise RuntimeError(f"Claude CLI 에러: {error_msg}")
```

---

## 6. dry_run 기본값 생성 로직

```python
def _generate_defaults(self, schema: dict) -> Any:
    """JSON schema를 재귀 순회하며 타입별 기본값을 채운다."""

    # enum이 있으면 첫 번째 값
    if "enum" in schema:
        return schema["enum"][0]

    # default가 있으면 그 값
    if "default" in schema:
        return schema["default"]

    typ = schema.get("type", "object")

    if typ == "string":
        return ""
    elif typ == "integer" or typ == "number":
        return 0
    elif typ == "boolean":
        return False
    elif typ == "array":
        return []
    elif typ == "object":
        result = {}
        for prop, prop_schema in schema.get("properties", {}).items():
            result[prop] = self._generate_defaults(prop_schema)
        return result
    else:
        return None
```

---

## 7. tenacity 재시도 조건

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=4, min=4, max=60),
    retry=retry_if_exception_type((RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired)),
)
def _call_live(self, user_prompt, system_prompt, json_schema):
    ...
```

재시도 대상:
- `subprocess.TimeoutExpired`: 타임아웃
- `RuntimeError`: returncode != 0 또는 is_error=True
- `json.JSONDecodeError`: stdout JSON 파싱 실패

재시도하지 않는 대상:
- `RateLimitExceeded`: 상한 초과는 재시도 무의미
- `FileNotFoundError`: claude CLI가 없는 경우

---

## 8. CLAUDE_CLIENT_VERSION 상수

```python
# 파일 최상단, import 직후
CLAUDE_CLIENT_VERSION = "1"
# 프롬프트 템플릿, JSON schema 구조, 또는 시스템 프롬프트 포맷을
# 변경할 때 이 값을 +1로 올린다. 캐시 해시에 포함되므로 기존
# 캐시가 자동으로 무효화된다. 코드를 수정하지 않고도 캐시를
# 완전히 교체할 수 있는 안전핀.
```

---

## 9. 에러 처리

### subprocess 실패 (returncode != 0)

```python
if proc.returncode != 0:
    raise RuntimeError(
        f"claude CLI 실행 실패 (returncode={proc.returncode}): {proc.stderr[:500]}"
    )
```

tenacity에 의해 3회 재시도. 모두 실패하면 RuntimeError 전파.

### JSON 파싱 실패

stdout이 유효한 JSON이 아닌 경우. tenacity에 의해 재시도. 모두 실패하면 json.JSONDecodeError 전파.

### 호출 상한 초과

```python
if self._live_calls >= self._max_total_calls:
    raise RateLimitExceeded(
        f"live 호출 상한 초과: {self._live_calls}/{self._max_total_calls}"
    )
```

재시도 불가. 즉시 발생.

### 손상된 캐시 파일

```python
try:
    cached = json.loads(cache_path.read_text())
    self._cache_hits += 1
    return cached
except (json.JSONDecodeError, OSError):
    pass  # 조용히 live 폴백
```

### CLI 미설치 (FileNotFoundError)

`subprocess.run`이 `FileNotFoundError`를 발생시킴. tenacity가 재시도하지 않도록 `retry_if_exception_type`에서 제외. 즉시 전파.

### is_error=True 응답

"Not logged in" 같은 CLI 에러. `_parse_cli_output`에서 `RuntimeError`를 발생시켜 tenacity 재시도 대상에 포함.

---

## 10. 외부 의존성

### 외부 라이브러리

| 패키지 | 용도 |
|--------|------|
| `tenacity` | 재시도 로직 |

### 표준 라이브러리

| 모듈 | 용도 |
|------|------|
| `subprocess` | claude CLI 호출 |
| `json` | JSON 직렬화/역직렬화 |
| `hashlib` | SHA-256 캐시 해시 |
| `pathlib` | 캐시 파일 경로 |
| `time` | sleep_between_calls |
| `typing` | Literal, Any |

### 절대 금지 (재확인)

- `anthropic` — Python SDK import 금지
- `httpx` — API 직접 호출 금지
- `os.environ["ANTHROPIC_API_KEY"]` — API 키 읽기 금지
- `requests` — HTTP 호출 금지

이 모듈에서 Claude와의 통신은 **오직 `subprocess.run(["claude", "-p", ...])`** 하나뿐.

---

## 11. 테스트 전략

### 단계별 테스트

1. **dry_run 먼저** (Claude 호출 0, 할당량 0):
   - 다양한 JSON schema로 `_generate_defaults` 결과 확인
   - get_stats() 확인
   - 상한 체크 동작 안 함 확인

2. **cache 모드** (첫 호출은 live 필요 → 사용자 허락):
   - 첫 호출: 캐시 미스 → live 호출 → 파일 생성 확인
   - 두 번째 호출: 같은 프롬프트 → 캐시 히트 → 파일에서 읽기
   - get_stats() 확인 (hits=1, misses=1)

3. **live 모드** (사용자 허락):
   - 단일 호출 → structured_output 반환 확인
   - 상한=1로 설정 후 두 번째 호출 → RateLimitExceeded

### 외부 호출 필요

Claude CLI 호출 (cache 미스 + live 모드)은 Max 구독 할당량을 소모하므로 반드시 사용자에게 먼저 확인.

---

## 12. 가장 까다로울 것 같은 부분

### ① CLI stdout 파싱의 신뢰성

`claude -p --output-format json`의 출력 형식이 버전에 따라 바뀔 수 있다. 현재 확인된 형식:

```json
{"type":"result", "subtype":"success", "is_error":false, "result":"...", "structured_output":{...}}
```

하지만 에러 케이스, 타임아웃 케이스, 또는 미래 버전에서 형식이 다를 수 있음. `_parse_cli_output`에서 `structured_output` → `result` 폴백 체인과 `is_error` 체크를 구현하지만, 예상치 못한 형식이 나오면 `json.JSONDecodeError`로 tenacity 재시도.

### ② user_prompt 길이 제한

`subprocess.run`의 인자로 user_prompt를 직접 넘기므로, OS의 인자 길이 제한(Linux: ~2MB)에 걸릴 수 있다. 논문 한 섹션의 source_excerpt(수천 자)를 user_prompt에 포함해도 2MB 이내이므로 현실적으로 문제없지만, 매우 긴 프롬프트는 stdin으로 전달하는 방식으로 전환이 필요할 수 있음.

**현재 결정**: 인자로 전달. 문제 발생 시 stdin 방식으로 전환.

### ③ sleep_between_calls의 적용 시점

`_call_live` 내부에서 sleep하면 tenacity 재시도 시에도 sleep이 적용됨. 이는 의도된 동작 — 재시도도 "호출"이므로 속도 제한을 지켜야 함.

단, cache 히트 시에는 sleep하지 않음 (네트워크 호출 없으므로).

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
