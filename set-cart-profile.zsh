#!/bin/zsh

set -e

NAMESPACE="ticket-system"
PROFILE=${1:-""}

usage() {
  echo "Usage: $0 <profile>"
  echo ""
  echo "  Cart budget held constant at ~3.0 cores / 2Gi total across all profiles."
  echo "  Cart pods run Guaranteed QoS (requests == limits)."
  echo ""
  echo "  Profiles:"
  echo "    1  — 1 replica,  3000m CPU / 2048Mi RAM each"
  echo "    3  — 3 replicas, 1000m CPU / 683Mi RAM each"
  echo "    5  — 5 replicas, 600m CPU  / 410Mi RAM each"
  exit 1
}

# Cart total budget — identical across profiles so RQ1/RQ4 reflect topology, not raw resource.
CART_CPU_TOTAL="3.0"
CART_MEM_BYTES=2147483648   # 2Gi total (Grafana denominator)

case $PROFILE in
  1)
    REPLICAS=1
    CPU="3000m"; MEM="2048Mi"   # req == lim (Guaranteed)
    DB_POOL_SIZE="8"            # 4 workers * 8 * 1 replica  = 32 pgbouncer client conns
    ;;
  3)
    REPLICAS=3
    CPU="1000m"; MEM="683Mi"
    DB_POOL_SIZE="3"            # 4 workers * 3  * 3 replicas = 36 pgbouncer client conns
    ;;
  5)
    REPLICAS=5
    CPU="600m"; MEM="410Mi"
    DB_POOL_SIZE="2"            # 4 workers * 2  * 5 replicas = 40 pgbouncer client conns
    ;;
  *)
    usage
    ;;
esac

# --- Pin SUT-critical pods to Guaranteed QoS (requests == limits) ---------
# Idempotent: kubectl patch is a no-op (no restart) when values already match.
# Keeps observability (Burstable) from stealing CPU from the measured path.
pin_resources() {
  local kind=$1 name=$2 cpu=$3 mem=$4
  echo "Pinning $kind/$name → ${cpu} CPU / ${mem} RAM (Guaranteed)..."
  kubectl patch $kind $name -n $NAMESPACE --type=merge -p "{
    \"spec\": {\"template\": {\"spec\": {\"containers\": [{
      \"name\": \"$name\",
      \"resources\": {
        \"requests\": {\"cpu\": \"$cpu\", \"memory\": \"$mem\"},
        \"limits\":   {\"cpu\": \"$cpu\", \"memory\": \"$mem\"}
      }
    }]}}}
  }"
}

pin_resources statefulset postgres  "2500m" "6Gi"
pin_resources deployment  pgbouncer  "1000m" "256Mi"
pin_resources deployment  redis      "500m"  "512Mi"

# --- ticket-info is unused by the load test → scale to 0 to free its slice --
# ticket-manager stays up (idle ≈ 0 CPU) so you can re-seed via Swagger between repeats.
echo "Scaling ticket-info to 0 (not part of SUT)..."
kubectl scale deployment ticket-info -n $NAMESPACE --replicas=0 2>/dev/null || true

echo ""
echo "Applying cart profile: $REPLICAS replica(s) — ${CPU} CPU / ${MEM} RAM each (req==lim)"

echo "Scaling down to 0 to free CPU before applying new resources..."
kubectl scale deployment cart -n $NAMESPACE --replicas=0
kubectl rollout status deployment/cart -n $NAMESPACE --timeout=60s

kubectl patch deployment cart -n $NAMESPACE --type=json -p "[
  {\"op\": \"replace\", \"path\": \"/spec/replicas\", \"value\": $REPLICAS},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/requests/cpu\",    \"value\": \"$CPU\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/requests/memory\", \"value\": \"$MEM\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/limits/cpu\",      \"value\": \"$CPU\"},
  {\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/limits/memory\",   \"value\": \"$MEM\"}
]"

# DB_POOL_SIZE set by env name (robust to env ordering changes).
kubectl set env deployment/cart -n $NAMESPACE DB_POOL_SIZE=$DB_POOL_SIZE

echo "Waiting for rollout..."
kubectl rollout status deployment/cart -n $NAMESPACE --timeout=120s

echo ""
echo "Cart profile $PROFILE active — $REPLICAS replica(s), ${CPU} CPU / ${MEM} RAM each (Guaranteed)"

# Update Grafana dashboard cart resource denominators to match new profile
echo "Updating Grafana dashboard..."
CONFIGMAP="${0:A:h}/k8s/observability/grafana-combined-dashboard-configmap.yaml"

CART_CPU=$CART_CPU_TOTAL CART_MEM=$CART_MEM_BYTES CM_PATH=$CONFIGMAP python3 - <<'PYEOF'
import re, os

path = os.environ["CM_PATH"]
cpu  = os.environ["CART_CPU"]
mem  = os.environ["CART_MEM"]

with open(path) as f:
    txt = f.read()

txt = re.sub(
    r'(pod=~\\"cart-\.\*\\", container=\\"\\"\}\[1m\]\)\) / )[0-9.]+',
    lambda m: m.group(1) + cpu,
    txt
)

txt = re.sub(
    r'(pod=~\\"cart-\.\*\\", container=\\"\\"\}\) / )[0-9]+',
    lambda m: m.group(1) + mem,
    txt
)

with open(path, "w") as f:
    f.write(txt)

print(f"  Cart CPU denominator → {cpu} cores total")
print(f"  Cart memory denominator → {mem} bytes total")
PYEOF

kubectl apply -f "$CONFIGMAP"
kubectl rollout restart deployment/grafana -n $NAMESPACE
kubectl rollout status deployment/grafana -n $NAMESPACE --timeout=60s
echo "Grafana dashboard updated."

echo "Restarting Grafana port-forward..."
pkill -f "kubectl port-forward.*grafana" 2>/dev/null || true
sleep 1
kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000 &>/dev/null &
echo "Grafana available at http://localhost:3000"
