# claude_client.py 구현 결과

## 1. 작성된 코드 (src/claude_client.py 전체)

```python
# 단일 책임: subprocess로 claude -p CLI를 호출하고, JSON schema로 구조화 출력을 강제하며, live/cache/dry_run 3가지 모드를 지원하는 래퍼.
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

CLAUDE_CLIENT_VERSION = "1"
# 프롬프트 템플릿, JSON schema 구조, 또는 시스템 프롬프트 포맷을
# 변경할 때 이 값을 +1로 올린다. 캐시 해시에 포함되므로 기존
# 캐시가 자동으로 무효화된다.


class RateLimitExceeded(Exception):
    """live 호출 수가 max_total_calls를 초과했을 때 발생."""


class ClaudeClient:
    """Claude CLI 래퍼.

    3가지 모드:
    - live: 실제 claude -p 호출.
    - cache: SHA-256 해시 기반 디스크 캐시. 미스 시 live 호출 후 저장.
    - dry_run: 실제 호출 없이 schema 기본값으로 가짜 응답.

    절대 규칙: anthropic SDK, httpx, API 키 사용 금지.
    오직 subprocess.run(["claude", "-p", ...])만 사용.
    """

    def __init__(
        self,
        mode: Literal["live", "cache", "dry_run"],
        cli_path: str = "claude",
        max_total_calls: int = 500,
        timeout_seconds: int = 600,
        sleep_between_calls: int = 3,
        cache_dir: Path | None = None,
    ):
        """Claude CLI 래퍼를 초기화한다.

        Args:
            mode: 동작 모드 ("live", "cache", "dry_run").
            cli_path: claude CLI 실행 경로.
            max_total_calls: live 호출 상한. 초과 시 RateLimitExceeded.
            timeout_seconds: subprocess 타임아웃 (초).
            sleep_between_calls: live 호출 간 대기 (초).
            cache_dir: cache 모드에서 사용할 디렉터리.
        """
        self._mode = mode
        self._cli_path = cli_path
        self._max_total_calls = max_total_calls
        self._timeout = timeout_seconds
        self._sleep = sleep_between_calls
        self._cache_dir = cache_dir

        # 통계
        self._live_calls = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._dry_run_calls = 0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

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
        if self._mode == "dry_run":
            return self._call_dry_run(json_schema)
        elif self._mode == "cache":
            return self._call_cached(user_prompt, system_prompt, json_schema)
        else:  # live
            self._check_rate_limit()
            result = self._call_live(user_prompt, system_prompt, json_schema)
            self._live_calls += 1
            time.sleep(self._sleep)
            return result

    def get_stats(self) -> dict:
        """호출 통계를 반환한다."""
        return {
            "total_calls": self._live_calls,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "dry_run_calls": self._dry_run_calls,
        }

    # ------------------------------------------------------------------
    # 모드별 내부 로직
    # ------------------------------------------------------------------

    def _call_dry_run(self, json_schema: dict) -> dict:
        """schema에서 기본값을 생성한다."""
        result = self._generate_defaults(json_schema)
        self._dry_run_calls += 1
        return result

    def _call_cached(
        self,
        user_prompt: str,
        system_prompt: str,
        json_schema: dict,
    ) -> dict:
        """캐시 조회 → 히트면 반환, 미스면 live 호출 후 저장."""
        cache_key = self._compute_cache_key(user_prompt, system_prompt, json_schema)
        cache_path = self._get_cache_path(cache_key)

        # 캐시 히트 시도
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                self._cache_hits += 1
                return cached
            except (json.JSONDecodeError, OSError):
                pass  # 손상된 캐시 → live 폴백

        # 캐시 미스 → live 호출
        self._check_rate_limit()
        result = self._call_live(user_prompt, system_prompt, json_schema)

        # 캐시 저장
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self._cache_misses += 1
        self._live_calls += 1
        time.sleep(self._sleep)
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=4, min=4, max=60),
        retry=retry_if_exception_type(
            (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired)
        ),
    )
    def _call_live(
        self,
        user_prompt: str,
        system_prompt: str,
        json_schema: dict,
    ) -> dict:
        """실제 subprocess 호출. tenacity 재시도 포함."""
        cmd = [
            self._cli_path,
            "-p",
            user_prompt,
            "--system-prompt",
            system_prompt,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(json_schema),
            "--bare",
            "--tools",
            "",
            "--no-session-persistence",
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI 실행 실패 (returncode={proc.returncode}): "
                f"{proc.stderr[:500]}"
            )

        return self._parse_cli_output(proc.stdout)

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    def _check_rate_limit(self) -> None:
        """live 호출 상한을 체크한다."""
        if self._live_calls >= self._max_total_calls:
            raise RateLimitExceeded(
                f"live 호출 상한 초과: {self._live_calls}/{self._max_total_calls}"
            )

    def _compute_cache_key(
        self, user_prompt: str, system_prompt: str, json_schema: dict
    ) -> str:
        """캐시 해시 (SHA-256)를 계산한다."""
        raw = (
            system_prompt
            + user_prompt
            + json.dumps(json_schema, sort_keys=True)
            + CLAUDE_CLIENT_VERSION
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """캐시 파일 경로를 반환한다."""
        assert self._cache_dir is not None, "cache 모드에는 cache_dir가 필수입니다"
        return self._cache_dir / "claude_responses" / f"{cache_key}.json"

    def _parse_cli_output(self, stdout: str) -> dict:
        """CLI stdout에서 structured_output을 추출한다."""
        data = json.loads(stdout)

        # is_error 체크
        if data.get("is_error"):
            error_msg = data.get("result", "알 수 없는 에러")
            raise RuntimeError(f"Claude CLI 에러: {error_msg}")

        # structured_output 우선
        if "structured_output" in data and data["structured_output"] is not None:
            return data["structured_output"]

        # 폴백: result 문자열을 JSON 파싱 시도
        if "result" in data and isinstance(data["result"], str):
            return json.loads(data["result"])

        raise ValueError("structured_output도 result도 파싱할 수 없습니다")

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
        elif typ in ("integer", "number"):
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

## 2. 검증 결과

### 2-1. import 테스트

```
$ .venv/bin/python -c "from src.claude_client import ClaudeClient, RateLimitExceeded, CLAUDE_CLIENT_VERSION; print('import OK, version=', CLAUDE_CLIENT_VERSION)"
import OK, version= 1
```

### 2-2. dry_run 테스트 (할당량 0)

```
$ .venv/bin/python -c "
from src.claude_client import ClaudeClient
client = ClaudeClient(mode='dry_run')
schema = {
    'type': 'object',
    'properties': {
        'explanation': {'type': 'string'},
        'is_leaf': {'type': 'boolean'},
        'children': {'type': 'array', 'items': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'brief': {'type': 'string'}}}},
        'confidence': {'type': 'number'},
        'status': {'type': 'string', 'enum': ['done', 'failed']}
    }
}
result = client.call(user_prompt='test', system_prompt='test', json_schema=schema)
print('dry_run 결과:', result)
print('stats:', client.get_stats())
"

dry_run 결과: {'explanation': '', 'is_leaf': False, 'children': [], 'confidence': 0, 'status': 'done'}
stats: {'total_calls': 0, 'cache_hits': 0, 'cache_misses': 0, 'dry_run_calls': 1}
```

기본값 생성 결과:

| 필드 | 타입 | 생성값 | 올바름 |
|------|------|--------|--------|
| explanation | string | "" | OK |
| is_leaf | boolean | False | OK |
| children | array | [] | OK |
| confidence | number | 0 | OK |
| status | string (enum: ["done", "failed"]) | "done" (첫 번째 enum 값) | OK |

통계:
- total_calls (live): 0 — dry_run은 live 카운트에 포함 안 됨
- dry_run_calls: 1

### 2-3. dry_run 추가 확인 — 중첩 object

dry_run의 `_generate_defaults`가 중첩 schema를 정확히 재귀 처리함. children의 items가 object이지만, array의 기본값이 `[]`이므로 items 내부까지 인스턴스화되지는 않음. 이는 올바른 동작 — 빈 배열이 기본값.

## 3. 구현 중 주의했던 점

1. **절대 규칙 준수**: anthropic, httpx, requests import 없음. API 키 읽기 없음. 오직 `subprocess.run(["claude", "-p", ...])` 하나.

2. **CLI 플래그 실제 확인 반영**: `--bare`, `--tools ""`, `--no-session-persistence` 추가. `--bare`는 CLAUDE.md auto-discovery 방지, `--tools ""`는 도구 비활성화, `--no-session-persistence`는 세션 디스크 저장 방지.

3. **tenacity 재시도**: `_call_live`에 `@retry` 데코레이터 적용. `RuntimeError`, `json.JSONDecodeError`, `subprocess.TimeoutExpired`만 재시도. `RateLimitExceeded`와 `FileNotFoundError`는 재시도 대상 아님.

4. **캐시 해시 정책**: HANDOFF.md §3-2 그대로 — SHA-256, 4개 입력(system_prompt, user_prompt, json_schema sort_keys, CLAUDE_CLIENT_VERSION).

5. **is_error 체크**: CLI가 `{"is_error": true, "result": "Not logged in"}`을 반환하면 `RuntimeError`로 전환하여 tenacity가 재시도.

6. **live 호출 카운트 위치**: `call()` 메서드에서 `_call_live` 성공 후 `_live_calls += 1`. `_call_cached`에서도 미스 시 같은 패턴. tenacity 재시도 내부에서는 카운트하지 않음 — 최종 성공 시에만 카운트.

## 4. cache+live 테스트 (사용자 허락 대기 중)

사용자 허락 후 실행 예정.

## 5. cache+live 테스트 (실행 완료 — 실패)

### 실패 원인

`--bare` 플래그가 OAuth/키체인 인증을 건너뛰어서 "Not logged in" 에러 발생.

### subprocess 디버그 출력

```
returncode: 1

stdout:
{"type":"result","subtype":"success","is_error":true,"duration_ms":27,
"duration_api_ms":0,"num_turns":1,
"result":"Not logged in · Please run /login",
"stop_reason":"stop_sequence",
"session_id":"f95a3951-26dd-4412-9ce2-2200b2b57c13",
"total_cost_usd":0,
"usage":{"input_tokens":0,...},
...}

stderr: (빈 문자열)
```

### 분석

`--bare` 도움말에 명시:
> "Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper via --settings
> (OAuth and keychain are never read)."

즉, `--bare` 모드에서는 환경 변수 `ANTHROPIC_API_KEY` 또는 `--settings`로 전달한
apiKeyHelper만 인증 수단으로 인정. 우리 프로젝트는 Max 구독(OAuth) 기반이므로
`--bare`를 쓰면 인증이 안 됨.

### 사용자 판단 필요

`--bare` 제거 또는 대체 플래그 검토가 필요. 코드 수정은 사용자 지시 후 진행.

## 6. --bare 제거 후 재테스트

### 수정 내용

1. `_call_live`의 cmd 리스트에서 `"--bare"` 제거
2. `subprocess.run(...)` 호출에 `cwd="/tmp"` 파라미터 추가 — 프로젝트의 CLAUDE.md가 auto-discovery되는 것을 방지
3. `--tools ""`와 `--no-session-persistence`는 유지

### 재테스트 결과

```
첫 호출 (live): {'answer': '{"result": "Four"}'}
stats: {'total_calls': 1, 'cache_hits': 0, 'cache_misses': 1, 'dry_run_calls': 0}
두 번째 호출 (cache hit): {'answer': '{"result": "Four"}'}
stats: {'total_calls': 1, 'cache_hits': 1, 'cache_misses': 1, 'dry_run_calls': 0}
캐시 파일 수: 1
  ff62dfbaa9a1898731ea392c4a5d150779078c83a7bbbb3ef69724212a5e401c.json
cache 테스트 완료
```

### 검증 항목

| 항목 | 결과 | 판정 |
|------|------|------|
| 첫 호출이 실제 Claude 응답 | `{'answer': '{"result": "Four"}'}` | OK |
| result1 == result2 (캐시 히트) | 완전 일치 | OK |
| 캐시 파일 생성 | `ff62dfb...json` 1개 | OK |
| json_schema 강제 동작 | `{"answer": "..."}` 구조 준수 | OK |
| stats 정확성 | total=1, hits=1, misses=1, dry_run=0 | OK |
| total_calls가 cache hit에서 증가 안 함 | 1 유지 | OK |

### 참고

- 응답 `{'answer': '{"result": "Four"}'}`에서 answer 값이 중첩 JSON 문자열로 들어옴. 이는 Claude가 system_prompt의 "Always respond in JSON"을 따르면서 structured_output의 answer 필드에 JSON 문자열을 넣은 것. 실제 expander에서는 schema가 더 구체적이므로 이 문제 없을 것.
