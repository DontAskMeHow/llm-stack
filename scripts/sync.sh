#!/usr/bin/env bash
# Синхронизация состояния кластера с репозиторием: pull → применить → проверить →
# записать применённую ревизию. Запускается вручную с машины, где есть kubectl.
#
#   ./scripts/sync.sh                 # helm-вариант
#   ./scripts/sync.sh --kustomize     # вариант без helm
#   APPLY=0 ./scripts/sync.sh         # только diff
set -euo pipefail

cd "$(dirname "$0")/.."
NS=${NS:-llm}
RELEASE=${RELEASE:-llm}
KUBECTL=${KUBECTL:-kubectl}
LOCAL_OVERLAY=charts/llm-stack/values.local.yaml
OVERLAY="-f charts/llm-stack/values.yaml"
[ -f "$LOCAL_OVERLAY" ] && OVERLAY="$OVERLAY -f $LOCAL_OVERLAY"

git pull --ff-only

if [ "${APPLY:-1}" = "0" ]; then
  if [ "${1:-}" = "--kustomize" ]; then
    "$KUBECTL" apply -k --dry-run=server kustomize/
  else
    helm diff upgrade "$RELEASE" charts/llm-stack $OVERLAY || \
      helm template "$RELEASE" charts/llm-stack $OVERLAY | head -40
  fi
  exit 0
fi

if [ "${1:-}" = "--kustomize" ]; then
  "$KUBECTL" apply -k kustomize/
else
  helm upgrade --install "$RELEASE" charts/llm-stack $OVERLAY
fi

"$KUBECTL" -n "$NS" rollout status deploy/llm-gateway --timeout=180s
"$KUBECTL" -n "$NS" get servicemonitor
git rev-parse --short HEAD > VERSION
echo "применена ревизия $(cat VERSION)"
