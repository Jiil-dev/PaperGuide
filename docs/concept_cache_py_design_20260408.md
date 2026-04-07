# src/concept_cache.py 설계

## 1. 모듈 책임 (한 줄)

**개념 이름과 설명을 기반으로 정규화 해시, 임베딩 유사도, 조상 순환의 3단계 필터로 중복/순환을 차단하는 캐시.**

---

## 2. 클래스 ConceptCache — `__init__` 시그니처와 내부 상태

### 생성자 시그니처

```python
from pathlib import Path

class ConceptCache:
    def __init__(
        self,
        cache_dir: Path,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        threshold: float = 0.88,
    ):
        """중복/순환 차단 캐시.

        Args:
            cache_dir: concepts.jsonl과 embeddings.npy를 저장/로드할 디렉터리.
            model_name: sentence-transformers 모델명.
            threshold: 임베딩 코사인 유사도 임계값. 이 이상이면 중복 판정.
        """
```

### 내부 상태 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `_cache_dir` | Path | 디스크 저장 경로 |
| `_threshold` | float | 유사도 임계값 (기본 0.88) |
| `_model_name` | str | 임베딩 모델명 |
| `_model` | SentenceTransformer \| None | 임베딩 모델 인스턴스 (lazy 로드) |
| `_records` | list[dict] | 레코드 리스트. 각 dict: `{"id": str, "concept": str, "norm": str, "hash": str}` |
| `_hash_to_id` | dict[str, str] | 정규화 해시 → node_id 매핑 (1단계 O(1) 조회) |
| `_embeddings` | numpy.ndarray \| None | shape=(N, dim). 레코드와 같은 순서. N=0이면 None |

---

## 3. 정규화 함수 `_normalize`

```python
def _normalize(self, name: str) -> str:
    """개념 이름을 정규화한다.

    1. 소문자 변환
    2. 연속 공백 → 단일 공백
    3. 앞뒤 공백 제거
    4. 특수문자 보존 (하이픈, 슬래시 등은 개념 구분에 의미 있음)
    """
```

특수문자를 제거하지 않는 이유:
- "self-attention"과 "self attention"은 다른 개념일 수 있음
- "encoder-decoder"와 "encoder decoder"도 마찬가지
- 하이픈, 슬래시, 괄호 등은 보존하되 공백만 정리

해시 생성: `hashlib.md5(_normalize(name).encode()).hexdigest()`

MD5를 쓰는 이유: 보안 목적이 아니라 문자열 동등성 판별용. SHA-256보다 짧고 빠름. claude_client의 캐시 해시(SHA-256)와 혼동하지 말 것 — 여기서는 개념 이름의 정규화 비교 전용.

---

## 4. 3단계 필터 구현 개요

### `lookup(concept_name: str, brief: str = "") -> str | None`

```
1단계: 정규화 해시 완전 일치
    norm = _normalize(concept_name)
    h = md5(norm)
    if h in _hash_to_id:
        return _hash_to_id[h]  # 원본 node_id

2단계: 임베딩 코사인 유사도
    if _embeddings is None or len(_records) == 0:
        return None  # 비교 대상 없음
    model = _get_model()  # lazy 로드
    query_text = f"{concept_name}. {brief}" if brief else concept_name
    query_vec = model.encode(query_text)  # shape=(dim,)
    # 모든 기존 임베딩과 코사인 유사도 계산
    similarities = cosine_similarity(query_vec, _embeddings)  # shape=(N,)
    max_idx = argmax(similarities)
    if similarities[max_idx] >= _threshold:
        return _records[max_idx]["id"]  # 가장 유사한 기존 개념의 node_id

3단계는 lookup에 포함되지 않음 — check_ancestor_cycle이 별도 메서드
    return None
```

### `add(node_id: str, concept_name: str, brief: str = "") -> None`

```
norm = _normalize(concept_name)
h = md5(norm)
record = {"id": node_id, "concept": concept_name, "norm": norm, "hash": h}

# 메모리 갱신
_records.append(record)
_hash_to_id[h] = node_id

# 임베딩 계산 + 추가
model = _get_model()
embed_text = f"{concept_name}. {brief}" if brief else concept_name
vec = model.encode(embed_text)  # shape=(dim,)
if _embeddings is None:
    _embeddings = vec.reshape(1, -1)
else:
    _embeddings = numpy.vstack([_embeddings, vec])

# 디스크 저장
_save_to_disk()
```

### `check_ancestor_cycle(concept_name: str, ancestor_path: list[str]) -> bool`

```
norm = _normalize(concept_name)
for ancestor in ancestor_path:
    if _normalize(ancestor) == norm:
        return True  # 순환 감지
return False
```

이 메서드는 캐시 상태(`_records`, `_embeddings`)를 전혀 사용하지 않음. 순수하게 이름 비교만 수행. 그럼에도 ConceptCache의 메서드인 이유: HANDOFF.md에 그렇게 정의됨 (§3-1 항목 4), 그리고 `_normalize`를 재사용하기 위함.

---

## 5. 디스크 로드/저장 로직

### 파일 구조

```
{cache_dir}/
  concepts.jsonl     — 한 줄에 한 JSON 객체 ({"id", "concept", "norm", "hash"})
  embeddings.npy     — numpy 배열 shape=(N, dim)
```

JSONL을 쓰는 이유: append가 간단 (파일 끝에 한 줄 추가). JSON 배열은 전체를 다시 써야 함.

### 로드 (`__init__`에서 호출)

```python
def _load_from_disk(self):
    jsonl_path = self._cache_dir / "concepts.jsonl"
    npy_path = self._cache_dir / "embeddings.npy"

    if not jsonl_path.exists():
        self._records = []
        self._hash_to_id = {}
        self._embeddings = None
        return

    # JSONL 로드
    records = []
    for line in jsonl_path.read_text().splitlines():
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
            emb = numpy.load(npy_path)
            if emb.shape[0] == len(records):
                self._embeddings = emb
            else:
                # 레코드와 임베딩 개수 불일치 → 임베딩 재생성 필요
                # 지금은 임베딩 버리고 None으로 (다음 add 때 다시 쌓임)
                self._embeddings = None
        except Exception:
            self._embeddings = None  # 손상된 npy 무시
    else:
        self._embeddings = None
```

### 저장 (`add` 때마다 호출)

```python
def _save_to_disk(self):
    self._cache_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = self._cache_dir / "concepts.jsonl"
    npy_path = self._cache_dir / "embeddings.npy"

    # JSONL 전체 다시 쓰기 (append 방식도 가능하나, 레코드 수가 수백 개 수준이라 전체 쓰기가 안전)
    lines = [json.dumps(r, ensure_ascii=False) for r in self._records]
    jsonl_path.write_text("\n".join(lines) + "\n")

    # NPY 저장
    if self._embeddings is not None:
        numpy.save(npy_path, self._embeddings)
```

### 파일 없을 때

빈 캐시로 시작. 정상 동작.

### 파일 손상됐을 때

- JSONL의 손상된 줄: 해당 줄만 건너뜀 (try/except)
- NPY 손상 또는 레코드 수 불일치: 임베딩 None으로 초기화. 2단계 필터가 일시적으로 비활성화되지만, 1단계(해시)와 3단계(순환)는 정상 동작. 다음 `add` 호출부터 임베딩이 다시 쌓임.

---

## 6. 임베딩 모델 로딩 타이밍

### 결정: **Lazy 로딩**

```python
def _get_model(self) -> SentenceTransformer:
    """임베딩 모델을 lazy 로드한다."""
    if self._model is None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self._model_name)
    return self._model
```

| 대안 | 장점 | 단점 | 선택 |
|------|------|------|------|
| Eager (생성자에서 로드) | 즉시 사용 가능 | dry_run 모드에서도 ~90MB 다운로드 + 수 초 로딩 | 탈락 |
| Lazy (첫 사용 시 로드) | dry_run에서 로드 안 됨, 1단계만 쓰면 불필요한 로딩 회피 | 첫 lookup/add가 약간 느림 | **선택** |

`from sentence_transformers import SentenceTransformer`도 `_get_model` 내부에서 수행 — import 자체가 torch를 로드해서 수 초 걸리기 때문.

---

## 7. 에러 처리

### 모델 다운로드 실패

`_get_model` 내부에서 `SentenceTransformer(model_name)` 호출이 실패하면 예외가 그대로 전파됨. 호출자(expander/main)가 처리.

### 디스크 쓰기 실패

`_save_to_disk`에서 권한 문제 등으로 실패하면 예외 전파. 메모리 상태는 이미 갱신됐으므로 현재 세션 내에서는 정상 동작. 다음 세션에서 디스크 로드가 불완전할 수 있음.

### 빈 concept_name

```python
if not concept_name or not concept_name.strip():
    return None  # lookup에서 빈 이름은 중복 아님
```

`add`에서도 빈 이름은 무시 (return 즉시).

### numpy 없음

requirements.txt에 numpy가 있으므로 발생하지 않음. 방어 불필요.

---

## 8. 테스트 전략

- **Claude 호출 할당량: 0** — 이 모듈은 Claude를 사용하지 않음.
- **임베딩 모델 다운로드**: 첫 실행 시 `all-MiniLM-L6-v2` (~90MB) 다운로드 발생. 사용자에게 "지금 돌려도 되나?" 확인 필요 (CLAUDE.md 작업 규칙 3번).
- **테스트 시나리오**:
  1. 빈 캐시 생성 → add 3개 → lookup으로 정확히 동일한 이름 중복 감지 (1단계)
  2. "Self-Attention" 추가 후 "self-attention" lookup → 정규화로 중복 감지 (1단계)
  3. "Multi-Head Attention" 추가 후 "Multi Head Attention mechanism" lookup → 임베딩 유사도로 중복 감지 (2단계, threshold 의존)
  4. ancestor_path에 "Attention" 포함 → check_ancestor_cycle("Attention", path) → True
  5. 디스크 저장 후 새 ConceptCache 인스턴스 생성 → 로드 확인 (레코드 수, 해시 일치)
- **주의**: 2단계 테스트의 결과는 모델 및 threshold에 의존. 유사도 값을 출력해서 0.88 기준에 맞는지 확인.

---

## 9. 가장 까다로울 것 같은 부분

### ① 임베딩과 레코드의 동기화

`_records`와 `_embeddings`는 항상 같은 순서, 같은 개수여야 한다. 디스크 저장/로드 과정에서 하나만 실패하면 불일치 발생. 예: JSONL은 성공했는데 NPY 저장 실패 → 다음 로드 시 레코드 N개, 임베딩 N-1개.

**해결 방향**: 로드 시 개수 불일치를 감지하면 임베딩을 None으로 초기화. 2단계가 일시적으로 비활성화되지만 1/3단계는 정상. `_save_to_disk`에서 JSONL과 NPY를 항상 함께 저장하여 불일치 최소화.

### ② 코사인 유사도 계산 효율

현재 설계는 매 `lookup`마다 query_vec과 모든 기존 임베딩의 유사도를 계산 (O(N)). N이 수백 개면 무시할 수 있지만, 수천 개가 되면 느려질 수 있음.

**현재 결정**: 그냥 O(N) 계산. 우리 프로젝트에서 한 논문의 개념 수는 최대 수백 개. FAISS 같은 ANN 라이브러리는 과잉. numpy의 벡터 연산으로 충분.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
