# src/verifier.py 설계

## 1. 모듈 책임 (한 줄)

**ConceptNode의 explanation이 source_excerpt에 충실하고 학부 1학년에게 적절한지 Claude 호출로 검증하여 passed/confidence/errors를 반환한다.**

---

## 2. Verifier 클래스 시그니처 + 내부 상태

### 생성자

```python
from src.claude_client import ClaudeClient
from src.tree import ConceptNode

class Verifier:
    def __init__(self, client: ClaudeClient, min_confidence: float = 0.7):
        """검증기.

        Args:
            client: ClaudeClient 인스턴스 (모드 무관).
            min_confidence: 이 이상의 confidence여야 최종 통과.
        """
```

### 내부 상태

| 필드 | 타입 | 설명 |
|------|------|------|
| `_client` | ClaudeClient | Claude 호출 래퍼 |
| `_min_confidence` | float | 최종 통과 임계값 (기본 0.7) |

---

## 3. verify() 메서드 흐름

```python
def verify(self, node: ConceptNode) -> dict:
    """노드의 explanation을 검증한다.

    Args:
        node: explanation이 채워진 ConceptNode.

    Returns:
        dict: {
            "passed": bool,           # Claude가 판정한 통과 여부
            "confidence": float,      # 0.0~1.0 검증 신뢰도
            "errors": list[dict],     # 발견된 오류 리스트
            "notes": str,             # 자유 형식 코멘트
            "passed_final": bool,     # passed AND confidence >= min_confidence
        }
    """
```

### 흐름 (pseudo-code)

```
1. user_prompt = _USER_PROMPT_TEMPLATE.format(
       concept=node.concept,
       source_excerpt=node.source_excerpt,
       explanation=node.explanation,
       target_level=_TARGET_LEVEL,
   )
2. result = self._client.call(
       user_prompt=user_prompt,
       system_prompt=_SYSTEM_PROMPT,
       json_schema=_VERIFY_SCHEMA,
   )
3. # 방어: Claude 응답에 필수 키가 없으면 기본값
   passed = result.get("passed", False)
   confidence = result.get("confidence", 0.0)
   errors = result.get("errors", [])
   notes = result.get("notes", "")
4. passed_final = passed and (confidence >= self._min_confidence)
5. return {
       "passed": passed,
       "confidence": confidence,
       "errors": errors,
       "notes": notes,
       "passed_final": passed_final,
   }
```

---

## 4. 시스템 프롬프트 전문

```python
_SYSTEM_PROMPT = """\
당신은 AI 논문 해설서의 품질 검증자입니다.
주어진 '설명(explanation)'이 '원문(source_excerpt)'을 기반으로 정확하고,
목표 독자 수준에 적합한지 엄격하게 판정하십시오.

검증 항목 4가지를 모두 적용합니다:

1. **원문 충실성(faithfulness)**: 설명이 원문의 내용을 왜곡하거나,
   원문에 없는 정보를 지어내지 않았는가?
2. **수준 적절성(level)**: 목표 독자(고등학교 수학2, 물리1,
   기초 프로그래밍을 이수한 대학교 1학년)가 이해할 수 있는가?
   지나치게 어렵거나 전문 용어를 설명 없이 사용하면 실패.
3. **자기충족성(self_contained)**: 설명이 원문 없이도 독립적으로
   이해되는 완결된 설명인가? "위에서 언급한", "앞서 설명한" 등
   외부 참조 없이 자체적으로 성립해야 함.
4. **수식 정확성(formula)**: 설명에 수식이 포함되어 있다면,
   원문의 수식과 정확히 일치하는가? 변수명, 연산, 첨자 오류가 없는가?
   수식이 없는 경우 이 항목은 자동 통과.

판정 기준:
- 4가지 항목 모두 통과해야 passed=true.
- 하나라도 문제가 있으면 passed=false이고 errors에 해당 항목을 기록.
- confidence는 0.0~1.0. 설명의 전반적 품질에 대한 확신도.

반드시 지정된 JSON 형식으로만 응답하십시오.\
"""
```

---

## 5. 사용자 프롬프트 템플릿 전문

```python
_TARGET_LEVEL = "고등학교 수학2, 물리1, 기초 프로그래밍 수준을 이수한 대학교 1학년 학생"

_USER_PROMPT_TEMPLATE = """\
다음 개념에 대한 설명을 검증해 주세요.

## 개념 이름
{concept}

## 원문 (source_excerpt)
{source_excerpt}

## 검증 대상 설명 (explanation)
{explanation}

## 목표 독자 수준
{target_level}

위 4가지 검증 항목(원문 충실성, 수준 적절성, 자기충족성, 수식 정확성)을
적용하여 판정 결과를 JSON으로 반환하세요.\
"""
```

---

## 6. JSON schema 전체

```python
_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "4가지 검증 항목 모두 통과 시 true"
        },
        "confidence": {
            "type": "number",
            "description": "설명의 전반적 품질에 대한 확신도 (0.0~1.0)"
        },
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["faithfulness", "level", "self_contained", "formula"]
                    },
                    "description": {
                        "type": "string",
                        "description": "오류 설명 (한국어)"
                    }
                },
                "required": ["category", "description"]
            },
            "description": "발견된 오류 리스트. 통과 시 빈 배열."
        },
        "notes": {
            "type": "string",
            "description": "추가 코멘트 (자유 형식)"
        }
    },
    "required": ["passed", "confidence", "errors", "notes"]
}
```

---

## 7. 반환 dict 형식

```python
{
    "passed": bool,        # Claude가 판정한 통과 여부
    "confidence": float,   # 0.0~1.0 검증 신뢰도
    "errors": [            # 발견된 오류 리스트
        {
            "category": "faithfulness" | "level" | "self_contained" | "formula",
            "description": "오류 설명 (한국어)"
        },
        ...
    ],
    "notes": str,          # 자유 형식 코멘트
    "passed_final": bool,  # passed AND confidence >= min_confidence
}
```

### dry_run에서의 동작

dry_run 모드에서 `_generate_defaults`가 반환하는 값:
- `passed`: False (boolean 기본값)
- `confidence`: 0 (number 기본값)
- `errors`: [] (array 기본값)
- `notes`: "" (string 기본값)

따라서 `passed_final = False AND (0 >= 0.7) = False`. dry_run에서는 모든 검증이 실패로 간주됨. 이는 의도된 동작 — dry_run은 파이프라인 흐름만 검증하고 실제 품질 검증은 하지 않음.

---

## 8. 에러 처리

### Claude 응답이 비정상 형식

claude_client가 이미 3회 재시도 + JSON 파싱을 처리. verifier에 도착하는 시점에는 dict가 보장됨. 그래도 `.get()`으로 방어:

```python
passed = result.get("passed", False)
confidence = result.get("confidence", 0.0)
errors = result.get("errors", [])
notes = result.get("notes", "")
```

누락된 키가 있으면 보수적 기본값 (passed=False, confidence=0.0) → 실패로 처리.

### node.explanation이 빈 문자열

expander가 explanation을 채우기 전에 verifier를 호출하면 안 됨. 하지만 방어 코드는 불필요 — 빈 explanation을 Claude에게 보내면 자연스럽게 "자기충족성 실패"로 판정될 것.

### node.source_excerpt이 빈 문자열

일부 섹션(예: `# Results` → 0자)에서 발생 가능. 이 경우에도 Claude에게 그대로 전달. "원문이 없으므로 원문 충실성 판정 불가" 같은 응답이 올 것.

---

## 9. 테스트 전략

### 단계별

1. **dry_run** (할당량 0):
   - 가짜 node(concept="Test", source_excerpt="...", explanation="...") 생성
   - `verify()` 호출 → `passed_final=False` 확인 (dry_run 기본값)
   - 반환 dict 형식 검증

2. **cache mock** (할당량 1, 사용자 허락):
   - 실제 node를 만들어 `verify()` 호출
   - 반환된 errors 배열의 category가 4가지 enum 중 하나인지 확인
   - 캐시 히트 확인 (같은 node로 두 번 호출)

3. **live 1회** (사용자 허락):
   - Attention 논문의 실제 섹션으로 호출
   - 의미 있는 passed/confidence/errors 반환 확인

---

## 10. 가장 까다로울 것 같은 부분

### ① 시스템 프롬프트의 판정 기준 캘리브레이션

"passed=true"의 기준이 너무 엄격하면 모든 설명이 실패하고 (재생성 폭발), 너무 느슨하면 품질이 보장되지 않음. 특히 "수준 적절성"은 주관적이라 Claude 버전/모델에 따라 판정이 달라질 수 있음.

**현재 접근**: min_confidence=0.7로 시작. 실제 파이프라인 실행 후 조정 가능 (config.yaml의 `verification.min_confidence`).

### ② explanation과 source_excerpt의 길이 비대칭

source_excerpt가 수천 자(예: "Why Self-Attention" 섹션 4068자)인데 explanation은 수백 자일 수 있음. Claude가 긴 원문 전체를 꼼꼼히 대조할지, 일부만 보고 판정할지는 모델에 의존. user_prompt에서 "원문 전체와 대조하라"고 명시적으로 지시하지만, 토큰 제한 내에서의 정확성은 보장할 수 없음.

**현재 접근**: 원문이 매우 길면 truncation이 필요할 수 있지만, 현재는 그대로 전달. Attention 논문 기준 가장 긴 섹션이 ~10K자이므로 Claude의 컨텍스트 내에 충분히 들어감.

---

**설계 일시:** 2026-04-08  
**상태:** 검토 대기 중
