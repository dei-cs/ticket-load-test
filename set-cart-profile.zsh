#!/bin/zsh

set -e

NAMESPACE="ticket-system"
PROFILE=${1:-""}

usage() {
  echo "Usage: $0 <profile>"
  echo ""
  echo "  Profiles:"
  echo "    1  — 1 replica,  4000m CPU / 8Gi RAM each"
  echo "    3  — 3 replicas, 1500m CPU / 2560Mi RAM each"
  echo "    5  — 5 replicas, 900m CPU  / 1536Mi RAM each"
  exit 1
}

case $PROFILE in
  1)
    REPLICAS=1
    CPU_REQ="4000m"; CPU_LIM="5000m"
    MEM_REQ="8Gi";   MEM_LIM="10Gi"
    ;;
  3)
    REPLICAS=3
    CPU_REQ="1500m"; CPU_LIM="1700m"
    MEM_REQ="2560Mi"; MEM_LIM="3Gi"
    ;;
  5)
    REPLICAS=5
    CPU_REQ="900m";  CPU_LIM="1000m"
    MEM_REQ="1536Mi"; MEM_LIM="2Gi"
    ;;
  *)
    usage
    ;;
esac

echo "Applying cart profile: $REPLICAS replica(s) — ${CPU_REQ} CPU / ${MEM_REQ} RAM each"

kubectl patch deployment cart -n $NAMESPACE --type=json -p "[
  {\"op\": \"replace\", \"path\": \"/spec/replicas\", \"value\": $REPLICAS},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/requests/cpu\",    \"value\": \"$CPU_REQ\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/requests/memory\", \"value\": \"$MEM_REQ\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/limits/cpu\",      \"value\": \"$CPU_LIM\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/limits/memory\",   \"value\": \"$MEM_LIM\"}
]"

echo "Waiting for rollout..."
kubectl rollout status deployment/cart -n $NAMESPACE --timeout=120s

echo ""
echo "Cart profile $PROFILE active — $REPLICAS replica(s), ${CPU_REQ}-${CPU_LIM} CPU, ${MEM_REQ}-${MEM_LIM} RAM"
