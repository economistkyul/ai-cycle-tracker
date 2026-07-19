# 개인정보 보호 정책

이 레포는 퍼블릭이다. 다음은 **어떤 파일에도 절대 기록하지 않는다**:

- 계좌번호, 증권사명, 예금주명, 실명, 가족관계
- 실계좌 금액(원화/달러), 보유 수량
- 전화번호, 이메일, 주소

## 방어 계층

1. **설계 분리**: 퍼블릭 설정(`config/`)에는 비중(%)·버킷·룰만 존재
2. **gitignore**: `data/private/` 전체 제외, PDF/출력물 제외
3. **pre-commit 훅**: `scripts/check_secrets.sh` — 계좌번호 패턴·private 경로 커밋 차단
   ```bash
   ln -sf ../../scripts/check_secrets.sh .git/hooks/pre-commit
   ```
4. **식별자 규칙**: 계좌는 `account_a`, `account_b` 로만 지칭

## 이미 커밋된 경우 (사고 대응)

퍼블릭 레포에 개인정보가 한 번이라도 push되면 **히스토리에 영구 잔존**한다.
단순 삭제 커밋으로는 제거되지 않으므로:

1. 즉시 레포를 private 전환
2. `git filter-repo` 로 히스토리에서 해당 파일/문자열 제거 후 force push
3. GitHub Support에 캐시 제거 요청
4. 노출된 것이 계좌번호라면 증권사에 연락해 조치

가장 좋은 대응은 애초에 커밋되지 않게 하는 것 — 훅 설치를 첫 작업으로 한다.
