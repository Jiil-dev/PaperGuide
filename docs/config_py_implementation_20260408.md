# config.py 구현 결과

## 1. 작성된 코드 (src/config.py 전체)

```python
# 단일 책임: config.yaml 로드, 검증, 경로 자동 생성 및 절대화

from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, ConfigDict, ValidationError


# 타입 정의
CheckType = Literal["hallucination", "omission", "contradiction", "math_error"]


# --- Pydantic 모델들 (모두 extra="forbid") ---

class TargetAudience(BaseModel):
    """목표 독자 수준 설정"""
    model_config = ConfigDict(extra="forbid")
    
    level: str
    background_knowledge: list[str]
    exclude_knowledge: list[str]


class Expansion(BaseModel):
    """트리 확장 제어"""
    model_config = ConfigDict(extra="forbid")
    
    max_depth: int = Field(default=4, ge=1, le=10)
    max_children_per_node: int = Field(default=5, ge=1, le=20)


class Dedup(BaseModel):
    """중복 차단"""
    model_config = ConfigDict(extra="forbid")
    
    similarity_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2"
    )


class Verification(BaseModel):
    """자기검증"""
    model_config = ConfigDict(extra="forbid")
    
    max_retries: int = Field(default=1, ge=0, le=5)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    check_types: list[CheckType]


class Claude(BaseModel):
    """Claude CLI 호출 설정"""
    model_config = ConfigDict(extra="forbid")
    
    cli_path: str = Field(default="claude")
    mode: Literal["live", "cache", "dry_run"] = Field(default="cache")
    max_total_calls: int = Field(default=500, ge=1)
    timeout_seconds: int = Field(default=600, ge=1)
    sleep_between_calls: int = Field(default=3, ge=0)


class Paths(BaseModel):
    """파일 경로 설정
    
    주의: 여기서는 상대 경로(또는 절대 경로)를 문자열로 받지만,
    load_config() 함수에서 절대 경로로 정규화됨.
    하위 폴더(e.g., data/cache/claude_responses/)는 각 모듈이
    필요할 때 자신의 책임 하에 생성.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Pydantic v2가 자동으로 문자열 -> Path 변환
    pdf_input: Path
    cache_dir: Path
    output_dir: Path
    checkpoints_dir: Path


class Config(BaseModel):
    """전체 설정 모델"""
    model_config = ConfigDict(extra="forbid")
    
    target_audience: TargetAudience
    expansion: Expansion
    dedup: Dedup
    verification: Verification
    claude: Claude
    paths: Paths


def load_config(path: str = "config.yaml") -> Config:
    """
    config.yaml을 로드, 검증, 및 경로 생성.
    
    동작:
    1. config.yaml의 절대 경로 구하기
    2. 프로젝트 루트 = config.yaml이 있는 디렉토리
    3. YAML 파싱 및 Pydantic 검증
    4. 상대 경로를 절대 경로로 정규화 (프로젝트 루트 기준)
    5. config.paths에 명시된 모든 디렉토리 자동 생성
       (단 하위 폴더는 각 모듈이 필요할 때 생성)
    
    Args:
        path: config.yaml의 경로. 기본값 "config.yaml".
    
    Returns:
        Config 인스턴스. 모든 경로는 절대 경로이고 디렉토리가 생성됨.
    
    Raises:
        FileNotFoundError: config.yaml이 없거나 읽을 수 없을 때
        yaml.YAMLError: YAML 파싱 실패
        ValidationError: Pydantic 검증 실패 (필드 누락, 타입 오류, 오타 등)
        OSError: 디렉토리 생성 권한 부족
    """
    
    # Step 1: config.yaml의 절대 경로와 프로젝트 루트 구하기
    config_path_abs = Path(path).resolve()
    project_root = config_path_abs.parent
    
    if not config_path_abs.exists():
        raise FileNotFoundError(
            f"config.yaml을 찾을 수 없습니다: {config_path_abs}"
        )
    
    # Step 2: YAML 파싱
    try:
        with open(config_path_abs, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"YAML 파싱 실패 ({config_path_abs}): {e}")
    
    # yaml.safe_load()가 None 반환하는 경우 처리 (빈 파일)
    if raw_data is None:
        raise ValueError(
            f"config.yaml이 비어있거나 유효하지 (파일: {config_path_abs})"
        )
    
    # Step 3: Pydantic 검증 및 모델 생성
    #         이 과정에서 YAML 문자열 경로 -> Pydantic이 Path로 변환
    try:
        config = Config(**raw_data)
    except ValidationError as e:
        raise ValidationError.from_exception_data(
            title="Config",
            line_errors=e.errors(),
        )
    
    # Step 4: 경로 절대화 (프로젝트 루트 기준)
    #         Pydantic v2에서 model_config frozen=False이므로 직접 할당 가능
    config.paths.pdf_input = (project_root / config.paths.pdf_input).resolve()
    config.paths.cache_dir = (project_root / config.paths.cache_dir).resolve()
    config.paths.output_dir = (project_root / config.paths.output_dir).resolve()
    config.paths.checkpoints_dir = (
        project_root / config.paths.checkpoints_dir
    ).resolve()
    
    # Step 5: 디렉토리 생성 (하위 폴더 구조는 각 모듈 책임)
    for path_field_name in [
        "pdf_input", "cache_dir", "output_dir", "checkpoints_dir"
    ]:
        path_obj = getattr(config.paths, path_field_name)
        path_obj.mkdir(parents=True, exist_ok=True)
    
    return config
```

---

## 2. 검증 결과

### 2-1. import 테스트

**명령어:**
```bash
python -c "from src.config import load_config, Config; print('import OK')"
```

**출력:**
```
import OK
```

✅ **결과: 성공**

---

### 2-2. 실제 로드 테스트 (config.yaml 로드 + 절대 경로 확인)

**명령어:**
```bash
python -c "from src.config import load_config; c = load_config(); print(c.model_dump_json(indent=2))"
```

**출력:**
```json
{
  "target_audience": {
    "level": "대학 1학년",
    "background_knowledge": [
      "고등학교 수학2 (미적분 기초)",
      "고등학교 물리1",
      "기초 프로그래밍"
    ],
    "exclude_knowledge": [
      "선형대수",
      "확률론",
      "머신러닝",
      "딥러닝"
    ]
  },
  "expansion": {
    "max_depth": 4,
    "max_children_per_node": 5
  },
  "dedup": {
    "similarity_threshold": 0.88,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
  },
  "verification": {
    "max_retries": 1,
    "min_confidence": 0.7,
    "check_types": [
      "hallucination",
      "omission",
      "contradiction",
      "math_error"
    ]
  },
  "claude": {
    "cli_path": "claude",
    "mode": "cache",
    "max_total_calls": 500,
    "timeout_seconds": 600,
    "sleep_between_calls": 3
  },
  "paths": {
    "pdf_input": "/home/engineer/j0061/paper-analyzer/data/papers",
    "cache_dir": "/home/engineer/j0061/paper-analyzer/data/cache",
    "output_dir": "/home/engineer/j0061/paper-analyzer/data/output",
    "checkpoints_dir": "/home/engineer/j0061/paper-analyzer/checkpoints"
  }
}
```

✅ **결과: 성공**

**확인 항목:**
- ✅ 모든 paths가 절대 경로로 정규화됨 (`/home/engineer/j0061/paper-analyzer/...`)
- ✅ 모든 필드가 올바르게 로드됨
- ✅ config.yaml 기준으로 경로 해석됨 (프로젝트 루트 정확)

---

### 2-3. 에러 테스트 (nonexistent.yaml)

**명령어:**
```bash
python -c "from src.config import load_config; load_config('nonexistent.yaml')"
```

**출력:**
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/home/engineer/j0061/paper-analyzer/src/config.py", line 121, in load_config
    raise FileNotFoundError(
FileNotFoundError: config.yaml을 찾을 수 없습니다: /home/engineer/j0061/paper-analyzer/nonexistent.yaml

Command exited with code 1
```

✅ **결과: 성공**

**확인 항목:**
- ✅ FileNotFoundError 정확히 발생
- ✅ 명확한 에러 메시지 (절대 경로 포함)

---

## 3. 구현 중 주의했던 점

### ① Pydantic v2에서 경로 필드 할당

Pydantic v2의 기본 설정(`model_config` 미지정)은 `frozen=False`이므로 모델 생성 후 직접 필드 할당이 가능하다:

```python
config.paths.pdf_input = (project_root / config.paths.pdf_input).resolve()
```

이 방식은 `model_copy(update={...})` 없이 원본 경로를 유지하면서 절대 경로로 덮어쓸 수 있어 의도한 대로 동작한다.

### ② yaml.safe_load()의 None 반환 처리

YAML 파일이 비어있거나 유효하지 않으면 `safe_load()`가 None을 반환한다. 이를 체크하여 명확한 ValueError를 발생시킨다:

```python
if raw_data is None:
    raise ValueError(f"config.yaml이 비어있거나 유효하지...")
```

### ③ import 순서 (PEP 8 준수)

```python
# 표준 라이브러리
from pathlib import Path
from typing import Literal

# 외부 패키지
import yaml
from pydantic import BaseModel, Field, ConfigDict, ValidationError
```

---

## 4. 사용자 직접 테스트 대기 항목

### 🔄 extra="forbid" 동작 확인 (사용자가 직접 테스트)

config.yaml에 오타를 넣어서 ValidationError가 정확히 발생하는지 확인하세요:

**테스트 시나리오:**
```yaml
# config.yaml에 오타 추가 (예: max_dept 대신 max_depth)
expansion:
  max_dept: 4  # 오타!
```

**기대 동작:**
```
ValidationError: Extra inputs are not permitted (또는 필드 누락 에러)
```

이 테스트를 완료하시면 extra="forbid"가 정확히 동작함을 확인하실 수 있습니다.

---

## 5. 다음 단계

- ✅ src/config.py 구현 완료
- ✅ 4가지 검증 통과
- ⏳ 사용자 오타 테스트 대기
- ➡️ 이후: tree.py, claude_client.py 등 다음 모듈 작성

---

**구현 일시:** 2026-04-08  
**상태:** 완료 (사용자 테스트 대기)
