#!/usr/bin/env bash
# ./git-safe.sh --push # push 전 점검 후 push
# 사용법:
#   ./git-safe.sh              # 점검만
#   ./git-safe.sh --fix        # Co-authored-by 제거 + 점검
#   ./git-safe.sh --push       # 점검 통과 후 push
#   ./git-safe.sh --fix --push # co-author 제거 → 점검 → push
#
# 점검 항목:
#   1. .env / .cursor ignore 및 추적 여부
#   2. staging에 .env 포함 여부
#   3. Co-authored-by: Cursor (cursoragent) 흔적
#   4. 로컬 ↔ origin/main 동기화 상태
#   5. 원격 main에 .env 존재 여부

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "[FAIL] Git 저장소가 아닙니다."
  exit 1
fi
cd "$ROOT"

DO_FIX=false
DO_PUSH=false
for arg in "$@"; do
  case "$arg" in
    --fix)  DO_FIX=true ;;
    --push) DO_PUSH=true ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "알 수 없는 옵션: $arg  (--help 로 사용법 확인)"
      exit 1
      ;;
  esac
done

PASS=$'\033[32m[PASS]\033[0m'
FAIL=$'\033[31m[FAIL]\033[0m'
WARN=$'\033[33m[WARN]\033[0m'
INFO=$'\033[36m[INFO]\033[0m'
SEP="──────────────────────────────────────────────────────────────────────"

ok()   { echo "  $PASS  $1${2:+  →  $2}"; }
ng()   { echo "  $FAIL  $1  →  $2"; }
warn() { echo "  $WARN  $1  →  $2"; }
info() { echo "  $INFO  $1"; }

FAILED=0
record_fail() { FAILED=$((FAILED + 1)); }

echo "══════════════════════════════════════════════════════════════════════"
echo "  Git Safe Check  |  $(basename "$ROOT")"
echo "══════════════════════════════════════════════════════════════════════"

# ── 0. Co-authored-by 제거 (--fix) ────────────────────────────────────────
if $DO_FIX; then
  echo ""
  echo "$SEP"
  echo "0. Co-authored-by: Cursor 제거"
  echo "$SEP"
  if git log -1 --format='%B' | grep -q '^Co-authored-by: Cursor'; then
    CLEAN_MSG="$(git log -1 --format='%B' | grep -v '^Co-authored-by:' | sed '/^$/d')"
    git commit --amend --no-verify -m "$CLEAN_MSG"
    ok "git commit --amend" "Co-authored-by 제거됨"
  else
    ok "최신 커밋" "Co-authored-by 없음 (변경 불필요)"
  fi
fi

# ── 1. .gitignore ─────────────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "1. .gitignore 점검"
echo "$SEP"

for pattern in .env .cursor .claude; do
  if grep -qE "^${pattern}/?$" .gitignore 2>/dev/null; then
    ok "$pattern" "gitignore 등록됨"
  else
    ng "$pattern" "gitignore에 없음 — .gitignore에 '${pattern}/' 추가 권장"
    record_fail
  fi
done

# ── 2. .env / .cursor 추적 ────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "2. 민감·IDE 파일 추적 여부"
echo "$SEP"

if git check-ignore -q .env 2>/dev/null || [[ ! -f .env ]]; then
  ok ".env" "$(git check-ignore -v .env 2>/dev/null | awk '{print $1,$2}' || echo 'ignore 또는 파일 없음')"
else
  ng ".env" "ignore 되지 않음"
  record_fail
fi

if git ls-files --error-unmatch .env &>/dev/null; then
  ng ".env 추적" "Git이 추적 중 — git rm --cached .env 실행 필요"
  record_fail
else
  ok ".env 추적" "추적 안 함"
fi

if git ls-files --error-unmatch .cursor &>/dev/null 2>&1; then
  ng ".cursor 추적" "Git이 추적 중"
  record_fail
else
  ok ".cursor 추적" "추적 안 함"
fi

# staging에 .env 포함 여부
if git diff --cached --name-only | grep -qE '(^|/)\.env$'; then
  ng "staging .env" "git add 에 .env가 포함됨 — git restore --staged .env"
  record_fail
else
  ok "staging .env" "포함 안 됨"
fi

# ── 3. cursoragent (Co-authored-by) ───────────────────────────────────────
echo ""
echo "$SEP"
echo "3. cursoragent (Co-authored-by) 점검"
echo "$SEP"

HEAD_MSG="$(git log -1 --format='%B' 2>/dev/null || true)"
if echo "$HEAD_MSG" | grep -q '^Co-authored-by: Cursor'; then
  ng "최신 커밋" "Co-authored-by: Cursor 있음 — ./git-safe.sh --fix 실행"
  record_fail
else
  ok "최신 커밋" "Co-authored-by 없음"
fi

if git log main --format='%B' 2>/dev/null | grep -q '^Co-authored-by: Cursor'; then
  warn "main 히스토리" "과거 커밋에 Co-authored-by 존재 (GitHub Contributors에 잔존 가능)"
else
  ok "main 히스토리" "Co-authored-by 없음"
fi

# ── 4. 브랜치 / 동기화 ────────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "4. 브랜치 · 원격 동기화"
echo "$SEP"

BRANCH="$(git branch --show-current)"
info "branch: $BRANCH"
info "author: $(git log -1 --format='%an <%ae>')"
info "commit: $(git log -1 --format='%h %s')"

git fetch origin --quiet 2>/dev/null || warn "git fetch" "origin 접속 실패 (오프라인?)"

if git rev-parse --verify origin/main &>/dev/null; then
  LOCAL="$(git rev-parse main 2>/dev/null || git rev-parse HEAD)"
  REMOTE="$(git rev-parse origin/main)"
  if [[ "$LOCAL" == "$REMOTE" ]]; then
    ok "origin/main" "로컬과 동기화됨 ($LOCAL)"
  elif git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null; then
    AHEAD="$(git rev-list --count origin/main..main)"
    warn "origin/main" "로컬이 ${AHEAD}커밋 앞섬 — git push 필요"
  elif git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
    BEHIND="$(git rev-list --count main..origin/main)"
    warn "origin/main" "로컬이 ${BEHIND}커밋 뒤처짐 — git pull 필요"
  else
    ng "origin/main" "히스토리 diverged — git pull 또는 git push --force 중 선택 필요"
    record_fail
  fi
else
  warn "origin/main" "원격 브랜치 없음"
fi

if [[ -z "$(git status --porcelain)" ]]; then
  ok "working tree" "clean"
else
  info "working tree 변경:"
  git status --short | sed 's/^/    /'
fi

# ── 5. 원격 .env ──────────────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "5. 원격(origin/main) .env 존재 여부"
echo "$SEP"

if git rev-parse --verify origin/main &>/dev/null; then
  if git ls-tree -r origin/main --name-only | grep -qE '(^|/)\.env$'; then
    ng "origin/main .env" "원격에 .env 존재 — 히스토리 정리 필요"
    record_fail
  else
    ok "origin/main .env" "없음"
  fi
else
  warn "origin/main .env" "원격 확인 불가"
fi

# ── 최종 요약 ─────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo "  최종 결과"
echo "══════════════════════════════════════════════════════════════════════"

if [[ "$FAILED" -eq 0 ]]; then
  echo "  $PASS  $FAILED 건 실패 — push 가능"
  echo ""
  if $DO_PUSH; then
    info "git push origin main 실행 중..."
    git push origin main
    ok "push" "완료"
  else
    info "push 하려면:  ./git-safe.sh --push"
    info "commit 후:    git add . && git commit -m \"메시지\" && ./git-safe.sh --push"
  fi
  exit 0
else
  echo "  $FAIL  $FAILED 건 실패 — push 전에 위 항목 해결 필요"
  echo ""
  info "co-author 제거:  ./git-safe.sh --fix"
  info "점검만:          ./git-safe.sh"
  exit 1
fi
