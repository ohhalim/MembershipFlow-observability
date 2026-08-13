# Contributing

## Work unit

- 코드·인프라 변경 전 이슈 생성
- 현재 구조, 관측값, 문제 지점, 변경 범위, 검증 방법 기록
- 한 PR에 하나의 목적만 포함
- 확정되지 않은 원인은 후보로 기록

## Branch and pull request

```text
<type>/<issue-number>/<keyword> -> develop -> main
```

- 작업 브랜치는 최신 `develop`에서 생성
- `develop`, `main` 직접 push 금지
- `main` 대상 PR의 head는 `develop`만 허용
- CI 통과 전 병합 금지

## Verification

- Python lint·format·test
- Docker Compose 설정 검증
- Prometheus 설정·규칙 검증
- 컨테이너 health gate
- 배포 후 로그·메트릭·Slack 경로 확인

