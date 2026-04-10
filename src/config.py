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
    default_mode: Literal["live", "cache", "dry_run"] = Field(default="cache")
    default_cache_dir: str = Field(default="data/cache")
    max_total_calls: int = Field(default=500, ge=1)
    timeout_seconds: int = Field(default=600, ge=1)
    sleep_between_calls: int = Field(default=3, ge=0)
    max_workers: int = Field(default=3, ge=1, le=10)


class Part1Config(BaseModel):
    """Part 1 생성 제어"""
    model_config = ConfigDict(extra="forbid")

    max_key_contributions: int = 4
    max_main_results: int = 5


class Part2Config(BaseModel):
    """Part 2 생성 제어"""
    model_config = ConfigDict(extra="forbid")

    max_depth: int = 4
    max_children_per_node: int = 5
    use_placeholders: bool = True


class PrerequisitePoolItem(BaseModel):
    """Part 3 사전 정의 주제 항목"""
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str


class Part3Config(BaseModel):
    """Part 3 생성 제어"""
    model_config = ConfigDict(extra="forbid")

    min_topics: int = 5
    max_topics: int = 15
    subsections_per_topic: int = 6
    allow_claude_to_add: bool = True
    predefined_pool: list[PrerequisitePoolItem] = Field(default_factory=list)


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
    part1: Part1Config = Field(default_factory=Part1Config)
    part2: Part2Config = Field(default_factory=Part2Config)
    part3: Part3Config = Field(default_factory=Part3Config)
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
            f"config.yaml이 비어있거나 유효하지 않습니다 (파일: {config_path_abs})"
        )
    
    # Step 3: Pydantic 검증 및 모델 생성
    #         이 과정에서 YAML 문자열 경로 -> Pydantic이 Path로 변환
    config = Config(**raw_data)
    
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
