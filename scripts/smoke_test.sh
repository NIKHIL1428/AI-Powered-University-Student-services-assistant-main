#!/usr/bin/env sh
# Curl every endpoint once. Usage: API=http://localhost:8000 sh scripts/smoke_test.sh
API=${API:-http://localhost:8000}
set -e
echo "== health";  curl -fs "$API/health" | head -c 400; echo
echo "== sources"; curl -fs "$API/sources" | head -c 300; echo
echo "== ask (general)"
R=$(curl -fs "$API/ask" -H "Content-Type: application/json" \
  -d '{"question":"What is the minimum attendance required to appear for end-semester exams?"}')
echo "$R" | head -c 400; echo
TRACE=$(echo "$R" | sed -n 's/.*"trace_id":"\([^"]*\)".*/\1/p')
echo "== audit $TRACE"; curl -fs "$API/audit/$TRACE" | head -c 300; echo
echo "== ask (refused: no identity)"
curl -fs "$API/ask" -H "Content-Type: application/json" -d '{"question":"What is my attendance?"}' | head -c 200; echo
echo "== ingest (bad metadata -> 422)"
printf 'test' > /tmp/smoke.txt
curl -s -o /dev/null -w "%{http_code}\n" "$API/ingest" -F "file=@/tmp/smoke.txt" -F 'metadata={"doc_id":"x"}'
