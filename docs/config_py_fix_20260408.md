# config.py 버그 및 오타 수정

## 1. 버그 수정: Step 3의 ValidationError 재래핑 제거

### 문제
Step 3에서 ValidationError를 try/except로 잡아 `from_exception_data()`로 재래핑하는 코드가 있었다:

```python
try:
    config = Config(**raw_data)
except ValidationError as e:
    raise ValidationError.from_exception_data(
        title="Config",
        line_errors=e.errors(),
    )
```

**이유:**
- 원본 ValidationError를 잡아 재래핑하는 것은 정보 손실만 있고 가치 없음
- `e.errors()`의 dict 구조와 `from_exception_data`의 `line_errors` 파라미터가 기대하는 InitErrorDetails 구조가 달라서, 실제로 ValidationError가 발생하면 재래핑 자체가 TypeError로 터질 가능성 있음
- 설계 합의에서 "ValidationError 그대로 전파"로 정했는데 어긴 것

### 수정
try/except 블록을 완전 제거하고 Pydantic이 자동으로 ValidationError를 던지도록 변경:

```python
# Step 3: Pydantic 검증 및 모델 생성
#         이 과정에서 YAML 문자열 경로 -> Pydantic이 Path로 변환
config = Config(**raw_data)
```

---

## 2. 오타 수정: Step 2의 불완전한 문장

### 문제
Step 2의 빈 파일 체크 메시지:

```python
raise ValueError(
    f"config.yaml이 비어있거나 유효하지 (파일: {config_path_abs})"
)
```

"유효하지" 뒤에 "않습니다"가 빠짐 → 문법 오류

### 수정
완전한 문장으로 수정:

```python
raise ValueError(
    f"config.yaml이 비어있거나 유효하지 않습니다 (파일: {config_path_abs})"
)
```

---

## 3. 검증 결과

### 3-1. cat src/config.py (수정된 파일)

Step 3 부분:
```python
    # Step 3: Pydantic 검증 및 모델 생성
    #         이 과정에서 YAML 문자열 경로 -> Pydantic이 Path로 변환
    config = Config(**raw_data)
```

✅ try/except 제거, 한 줄로 단순화

Step 2 부분:
```python
    # yaml.safe_load()가 None 반환하는 경우 처리 (빈 파일)
    if raw_data is None:
        raise ValueError(
            f"config.yaml이 비어있거나 유효하지 않습니다 (파일: {config_path_abs})"
        )
```

✅ 불완전한 문장 수정

### 3-2. reload 테스트

**명령어:**
```bash
python -c "from src.config import load_config; c = load_config(); print('reload OK, mode:', c.claude.mode)"
```

**출력:**
```
reload OK, mode: cache
```

✅ **결과: 성공**

---

## 4. 최종 상태

- ✅ 버그 수정: ValidationError 재래핑 제거 (설계 합의 준수)
- ✅ 오타 수정: 불완전한 문장 완성
- ✅ 모든 검증 통과
- ✅ 동작 정상 확인

---

**수정 일시:** 2026-04-08  
**상태:** 완료
