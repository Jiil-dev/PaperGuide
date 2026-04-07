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
            "--tools",
            "",
            "--no-session-persistence",
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            cwd="/tmp",  # CLAUDE.md auto-discovery 방지
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
