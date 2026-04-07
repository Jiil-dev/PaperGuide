# pdf_parser.py 수식 보존 테스트 (Attention 논문)

## 1. 기본 정보

- PDF: attention.pdf (Vaswani et al. 2017, "Attention Is All You Need")
- page_count: 15
- title: "attention" (PDF 메타데이터에 title 없어서 파일명 폴백)
- markdown length: 42,272자

## 2. 수식 패턴 통계

- `$...$` inline: **0개**
- `$$...$$` block: **0개**
- `\cmd` LaTeX 명령 (`\frac`, `\sum` 등): **0개**
- 유니코드 수학 기호: **21개** (고유: `√`, `×`, `∈`, `∞`, `α`, `β`, `π`)
- 이미지 placeholder (`**==> picture ... <==**`): **12개**

## 3. 수식 샘플

LaTeX 형식 수식은 **하나도 발견되지 않음**.

유니코드 기호로 일부 수식 조각이 텍스트에 섞여서 추출됨:

```
divide each by [√] dk, and apply a softmax function
```

```
Wi[Q] ∈ R[d][model][×][d][k]
```

## 4. Attention 공식 주변 500자

핵심 수식 `Attention(Q, K, V) = softmax(QK^T / √dk) V`가 있어야 하는 위치:

```
packed together into a matrix Q. The keys and values are also packed together 
into matrices K and V. We compute the matrix of outputs as: 

**==> picture [286 x 26] intentionally omitted <==**

The two most commonly used attention functions are additive attention [2], 
and dot-product (multiplicative) attention.
```

**수식이 이미지(picture)로 처리되어 완전히 누락됨.** `Attention(Q, K, V) = ...` 수식 자체가 없고, 그 자리에 `picture [286 x 26] intentionally omitted` placeholder만 남음.

MultiHead 수식도 마찬가지:

```
MultiHead(Q, K, V) = Concat(head1, ..., headh) W[O]

**==> picture [202 x 14] intentionally omitted <==**
```

FFN 수식은 텍스트로 일부 추출되었으나 LaTeX 형식이 아님:

```
## FFN(x) = max(0, xW1 + b1)W2 + b2
```

## 5. 판정

**[B] 유니코드 기호지만 읽을 수 있음 — 단, 핵심 수식 다수가 이미지로 처리되어 누락됨**

상세 분석:

- pymupdf4llm은 PDF의 수식을 **LaTeX로 변환하지 않음**
- 텍스트 레이어에 포함된 수식 기호(√, ∈, × 등)는 유니코드로 추출됨
- **핵심 수식(Attention 공식, MultiHead 공식 등)은 PDF 내부에서 이미지/벡터 그래픽으로 렌더링되어 있어서, pymupdf4llm이 이를 "picture ... intentionally omitted"로 처리**
- LaTeX `$...$`, `$$...$$`, `\frac`, `\sum` 등의 패턴은 0개

이는 B와 C의 경계에 해당. 단순 수식(FFN 등)은 평문으로 읽을 수 있지만, 복잡한 핵심 수식은 이미지 placeholder로 대체되어 **사실상 누락**.

## 6. 권장 조치

1. **즉각적 판단 보류**: pymupdf4llm만으로는 수식 밀도가 높은 논문의 핵심 수식을 텍스트로 추출할 수 없음이 확인됨. 그러나 이 프로젝트의 파이프라인에서 수식 원문은 `source_excerpt`에 저장되어 Claude에 전달되므로, Claude가 수식 맥락을 이해하는 데 치명적인지는 실제 확장(expander) 단계에서 판단해야 함.

2. **marker-pdf 교체 검토 시점**: 지금 당장 교체하기보다는, expander에서 실제 논문을 돌려봤을 때 수식 누락으로 인해 설명 품질이 떨어지는지 확인한 후 결정하는 것을 권장. 현 단계에서는 파이프라인 구축을 계속 진행.

3. **만약 교체한다면**: CLAUDE.md에 명시된 대로 `marker-pdf`를 검토. marker-pdf는 PDF의 수식을 LaTeX로 변환하는 기능이 있는 것으로 알려져 있음. 단, 실험적 라이브러리이므로 CLAUDE.md 절대 규칙 4번("확실하지 않은 라이브러리 추가 전 사용자에게 묻기")에 따라 사용자 승인 필요.
