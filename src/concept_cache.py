# 단일 책임: 개념 이름과 설명을 기반으로 정규화 해시, 임베딩 유사도, 조상 순환의 3단계 필터로 중복/순환을 차단하는 캐시.
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np


class ConceptCache:
    """중복/순환 차단 캐시.

    3단계 필터:
    1. 정규화 이름 해시 완전 일치 (O(1))
    2. 임베딩 코사인 유사도 ≥ threshold
    3. 조상 경로 순환 체크 (별도 메서드)

    임베딩 모델은 lazy 로드. dry_run이나 1단계만 사용할 때 불필요한 로딩을 피한다.
    """

    def __init__(
        self,
        cache_dir: Path,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        threshold: float = 0.88,
    ):
        """캐시를 초기화한다. 디스크에 기존 데이터가 있으면 자동 로드.

        Args:
            cache_dir: concepts.jsonl과 embeddings.npy를 저장/로드할 디렉터리.
            model_name: sentence-transformers 모델명.
            threshold: 임베딩 코사인 유사도 임계값. 이 이상이면 중복 판정.
        """
        self._cache_dir = cache_dir
        self._model_name = model_name
        self._threshold = threshold
        self._model = None  # lazy 로드

        # 내부 상태
        self._records: list[dict] = []
        self._hash_to_id: dict[str, str] = {}
        self._embeddings: np.ndarray | None = None

        self._load_from_disk()

    # ------------------------------------------------------------------
    # 공개 API (3개)
    # ------------------------------------------------------------------

    def lookup(self, concept_name: str, brief: str = "") -> str | None:
        """중복이면 원본 node_id를 반환한다. 아니면 None.

        1단계: 정규화 이름 해시 완전 일치.
        2단계: 임베딩 코사인 유사도 ≥ threshold.
        """
        if not concept_name or not concept_name.strip():
            return None

        # 1단계: 해시 일치
        norm = self._normalize(concept_name)
        h = hashlib.md5(norm.encode()).hexdigest()
        if h in self._hash_to_id:
            return self._hash_to_id[h]

        # 2단계: 임베딩 유사도
        if self._embeddings is None or len(self._records) == 0:
            return None

        model = self._get_model()
        query_text = f"{concept_name}. {brief}" if brief else concept_name
        query_vec = model.encode(query_text, normalize_embeddings=True)

        # 코사인 유사도 = 내적 (임베딩이 이미 정규화되어 있으므로)
        similarities = self._embeddings @ query_vec
        max_idx = int(np.argmax(similarities))
        if similarities[max_idx] >= self._threshold:
            return self._records[max_idx]["id"]

        return None

    def add(self, node_id: str, concept_name: str, brief: str = "") -> None:
        """캐시에 개념을 추가한다.

        메모리와 디스크를 동시에 갱신.
        """
        if not concept_name or not concept_name.strip():
            return

        norm = self._normalize(concept_name)
        h = hashlib.md5(norm.encode()).hexdigest()
        record = {"id": node_id, "concept": concept_name, "norm": norm, "hash": h}

        # 메모리 갱신
        self._records.append(record)
        self._hash_to_id[h] = node_id

        # 임베딩 계산 + 추가
        model = self._get_model()
        embed_text = f"{concept_name}. {brief}" if brief else concept_name
        vec = model.encode(embed_text, normalize_embeddings=True)

        if self._embeddings is None:
            self._embeddings = vec.reshape(1, -1)
        else:
            self._embeddings = np.vstack([self._embeddings, vec])

        # 디스크 저장
        self._save_to_disk()

    def check_ancestor_cycle(
        self, concept_name: str, ancestor_path: list[str]
    ) -> bool:
        """조상 경로에 같은 정규화 이름이 있으면 True (순환).

        캐시 상태를 사용하지 않고 순수 이름 비교만 수행.
        """
        norm = self._normalize(concept_name)
        for ancestor in ancestor_path:
            if self._normalize(ancestor) == norm:
                return True
        return False

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _normalize(self, name: str) -> str:
        """개념 이름을 정규화한다.

        소문자 변환, 연속 공백 → 단일 공백, 앞뒤 공백 제거.
        하이픈·슬래시 등 특수문자는 보존 (개념 구분에 의미 있음).
        """
        text = name.lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _get_model(self):
        """임베딩 모델을 lazy 로드한다."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _load_from_disk(self) -> None:
        """디스크에서 캐시를 로드한다. 파일 없으면 빈 상태."""
        jsonl_path = self._cache_dir / "concepts.jsonl"
        npy_path = self._cache_dir / "embeddings.npy"

        if not jsonl_path.exists():
            self._records = []
            self._hash_to_id = {}
            self._embeddings = None
            return

        # JSONL 로드
        records = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 손상된 줄 무시

        self._records = records
        self._hash_to_id = {r["hash"]: r["id"] for r in records}

        # NPY 로드
        if npy_path.exists() and len(records) > 0:
            try:
                emb = np.load(npy_path)
                if emb.shape[0] == len(records):
                    self._embeddings = emb
                else:
                    self._embeddings = None  # 레코드와 개수 불일치
            except Exception:
                self._embeddings = None  # 손상된 npy 무시
        else:
            self._embeddings = None

    def _save_to_disk(self) -> None:
        """캐시를 디스크에 저장한다."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self._cache_dir / "concepts.jsonl"
        npy_path = self._cache_dir / "embeddings.npy"

        # JSONL 전체 쓰기
        lines = [json.dumps(r, ensure_ascii=False) for r in self._records]
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # NPY 저장
        if self._embeddings is not None:
            np.save(npy_path, self._embeddings)
