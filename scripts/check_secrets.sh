#!/usr/bin/env bash
# pre-commit 훅: 개인정보/실데이터 커밋 차단
# 설치: ln -sf ../../scripts/check_secrets.sh .git/hooks/pre-commit
set -e

# 커밋 대상 파일 중 private 경로가 섞였는지 확인 (다중 방어)
if git diff --cached --name-only | grep -qE "^data/private/.+"; then
  echo "❌ data/private/ 파일이 스테이징됨 — 커밋 차단"
  exit 1
fi

# 개인정보 패턴 스캔 (커밋 전 스테이징된 내용만)
PATTERNS='[0-9]{3}-[0-9]{2,4}-[0-9]{4}|계좌번호|예금주|주민등록|010-[0-9]{4}'
if git diff --cached -U0 | grep -E "^\+" | grep -qE "$PATTERNS"; then
  echo "❌ 개인정보 의심 패턴 감지 (계좌번호/전화번호 형식 등) — 커밋 차단"
  git diff --cached -U0 | grep -E "^\+" | grep -E "$PATTERNS" | head -5
  exit 1
fi

# 큰 금액 실데이터 의심값 (원 단위 8자리 이상 숫자) 경고
if git diff --cached -U0 -- "config/*.yaml" | grep -E "^\+" | grep -qE "[0-9]{8,}"; then
  echo "⚠️  8자리 이상 숫자 감지 — 실계좌 금액이 아닌지 확인 후 커밋하세요"
fi
echo "✅ secret check 통과"
