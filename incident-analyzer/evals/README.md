# Incident analysis regression evals

운영 장애 분석 결과의 회귀를 고정 fixture로 확인한다.

`payment-lock-pool-exhaustion.json`은 운영 DB 원문이 아니다. 2026-08-15 결제
락 검증에서 확인한 수치와 Slack 분석 요약을 사용해 민감값 없이 재구성했다.

## 실행

```bash
cd incident-analyzer
python -m app.evaluation.regression \
  evals/payment-lock-pool-exhaustion.json
```

현재 baseline은 근거 없는 `커넥션 누수` 후보를 포함하므로 의도적으로 실패한다.
실패한 check가 있으면 명령도 종료 코드 `1`을 반환한다.
후속 Prometheus evidence 수집과 분석 규칙 변경 전후에 같은 fixture를 실행한다.

실제 Gemini 호출은 이 평가 명령에 포함하지 않는다. API 키가 없는 CI에서는 저장된
분석 결과만 검사하고, live model 평가는 별도 승인된 수동 절차로 실행한다.
