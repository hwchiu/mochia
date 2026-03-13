#!/bin/bash
# ============================================================
#  smoke-test.sh — Docker 容器 E2E 煙霧測試
#
#  驗證 web container 啟動後，所有核心 API 都能正常回應。
#  本地執行：bash smoke-test.sh
#  CI 執行：由 .github/workflows/ci.yml 呼叫
# ============================================================
set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0
ERRORS=()

# ─── 工具函式 ─────────────────────────────────────────────────

check() {
  local desc="$1"
  local expected_status="$2"
  local url="$3"
  local extra_args="${4:-}"

  # shellcheck disable=SC2086
  actual_status=$(curl -s -o /tmp/smoke_body.txt -w "%{http_code}" $extra_args "$url")
  body=$(cat /tmp/smoke_body.txt)

  if [ "$actual_status" = "$expected_status" ]; then
    echo "  ✅ [$actual_status] $desc"
    PASS=$((PASS + 1))
  else
    echo "  ❌ [$actual_status != $expected_status] $desc"
    echo "     URL: $url"
    echo "     Body: ${body:0:200}"
    FAIL=$((FAIL + 1))
    ERRORS+=("$desc")
  fi
}

check_json_field() {
  local desc="$1"
  local url="$2"
  local field="$3"

  body=$(curl -s "$url")
  if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$field' in d" 2>/dev/null; then
    echo "  ✅ [JSON:$field] $desc"
    PASS=$((PASS + 1))
  else
    echo "  ❌ [missing:$field] $desc"
    echo "     Body: ${body:0:200}"
    FAIL=$((FAIL + 1))
    ERRORS+=("$desc (missing field: $field)")
  fi
}

wait_for_server() {
  echo "⏳ 等待服務啟動 ($BASE_URL/health)..."
  attempts=0
  while [ $attempts -lt 30 ]; do
    if curl -s -f "$BASE_URL/health" > /dev/null 2>&1; then
      echo "✅ 服務已就緒（第 $((attempts + 1)) 次嘗試）"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "❌ 服務 60 秒內未就緒，放棄。"
  return 1
}

# ─── 等待服務 ─────────────────────────────────────────────────
wait_for_server

echo ""
echo "=== 基礎健康檢查 ==="
check "Health endpoint" "200" "$BASE_URL/health"
check_json_field "Health returns status field" "$BASE_URL/health" "status"

echo ""
echo "=== 前端頁面 ==="
check "首頁 HTML" "200" "$BASE_URL/"
check "靜態 CSS" "200" "$BASE_URL/static/css/style.css"
check "影片詳情頁（空 ID）" "200" "$BASE_URL/video/nonexistent"

echo ""
echo "=== 影片 API ==="
check "GET /api/videos/ (列表)" "200" "$BASE_URL/api/videos/"
check_json_field "影片列表有 items 欄位" "$BASE_URL/api/videos/" "items"
check "GET /api/videos/?status=completed" "200" "$BASE_URL/api/videos/?status=completed"
check "GET /api/videos/nonexistent (404)" "404" "$BASE_URL/api/videos/nonexistent"

echo ""
echo "=== 搜尋 API ==="
check "GET /api/search/?q=test" "200" "$BASE_URL/api/search/?q=test"
check_json_field "搜尋結果有 items 欄位" "$BASE_URL/api/search/?q=test" "items"
check "GET /api/search/ 無 query (422)" "422" "$BASE_URL/api/search/"

echo ""
echo "=== 複習系統 API ==="
check "GET /api/review/due" "200" "$BASE_URL/api/review/due"
check "GET /api/review/stats" "200" "$BASE_URL/api/review/stats"
check "GET /api/review/upcoming" "200" "$BASE_URL/api/review/upcoming"

echo ""
echo "=== 學習統計 API ==="
check "GET /api/stats/overview" "200" "$BASE_URL/api/stats/overview"
check_json_field "統計有 total_videos 欄位" "$BASE_URL/api/stats/overview" "total_videos"
check "GET /api/stats/daily" "200" "$BASE_URL/api/stats/daily"
check "GET /api/stats/confidence" "200" "$BASE_URL/api/stats/confidence"

echo ""
echo "=== 標籤 API ==="
check "GET /api/labels/" "200" "$BASE_URL/api/labels/"

echo ""
echo "=== 分析 API ==="
check "GET /api/analysis/nonexistent/status (404)" "404" "$BASE_URL/api/analysis/nonexistent/status"

echo ""
echo "=== 版本 API ==="
check "GET /api/version" "200" "$BASE_URL/api/version"
check_json_field "版本回應有 version 欄位" "$BASE_URL/api/version" "version"
check_json_field "版本回應有 build_date 欄位" "$BASE_URL/api/version" "build_date"

echo ""
echo "=== 批量操作 API ==="
check "GET /api/batch/status (批量狀態)" "200" "$BASE_URL/api/batch/status"

echo ""
echo "══════════════════════════════════════"
echo "  Smoke Test 結果：✅ $PASS 通過 / ❌ $FAIL 失敗"
echo "══════════════════════════════════════"

if [ $FAIL -gt 0 ]; then
  echo ""
  echo "失敗項目："
  for err in "${ERRORS[@]}"; do
    echo "  - $err"
  done
  exit 1
fi

exit 0
