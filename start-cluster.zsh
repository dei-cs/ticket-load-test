#!/bin/zsh

set -e

# ===== CONFIG =====

NAMESPACE="ticket-system"

# ===== START MINIKUBE =====

echo "=============================="
echo "Starting minikube"
echo "=============================="

# minikube start is a no-op when already running
# omit --cpus/--memory: minikube rejects changes to an existing profile
# to resize: minikube delete && minikube start --cpus=N --memory=M
minikube start

# ===== ADDONS (one-time, idempotent) =====

echo ""
echo "=============================="
echo "Enabling addons"
echo "=============================="

minikube addons enable metrics-server

# ===== APPLY MANIFESTS =====

echo ""
echo "=============================="
echo "Applying manifests"
echo "=============================="

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets/
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/pgbouncer/
kubectl apply -R -f k8s/apps/
kubectl apply -f k8s/observability/

# ===== WAIT FOR CORE DEPS =====

echo ""
echo "=============================="
echo "Waiting for postgres"
echo "=============================="
kubectl rollout status statefulset/postgres -n $NAMESPACE --timeout=300s

echo ""
echo "=============================="
echo "Waiting for pgbouncer"
echo "=============================="
kubectl rollout status deployment/pgbouncer -n $NAMESPACE --timeout=120s

echo ""
echo "=============================="
echo "Waiting for apps"
echo "=============================="
kubectl rollout status deployment/cart -n $NAMESPACE --timeout=300s
kubectl rollout status deployment/ticket-manager -n $NAMESPACE --timeout=300s
kubectl rollout status deployment/ticket-info -n $NAMESPACE --timeout=300s
kubectl rollout status deployment/user-generator -n $NAMESPACE --timeout=300s

# ===== PORT FORWARDS =====
# minikube docker driver on macOS: node IP not reachable from host, use port-forward instead

echo ""
echo "=============================="
echo "Starting port-forwards"
echo "=============================="

# Kill any stale port-forwards from a previous run
pkill -f "kubectl port-forward.*ticket-system" 2>/dev/null || true
sleep 1

kubectl port-forward -n $NAMESPACE svc/user-generator 8000:8000 &>/dev/null &
kubectl port-forward -n $NAMESPACE svc/ticket-manager 8001:8001 &>/dev/null &
kubectl port-forward -n $NAMESPACE svc/ticket-info    8002:8002 &>/dev/null &
kubectl port-forward -n $NAMESPACE svc/cart           8003:8003 &>/dev/null &
kubectl port-forward -n $NAMESPACE svc/grafana        3000:3000 &>/dev/null &

sleep 2

echo ""
echo "=============================="
echo "Cluster ready"
echo "=============================="
echo ""
echo "  Services:"
echo "    user-generator  http://localhost:8000  (swagger: /docs)"
echo "    ticket-manager  http://localhost:8001  (swagger: /docs)"
echo "    ticket-info     http://localhost:8002  (swagger: /docs)"
echo "    cart            http://localhost:8003  (swagger: /docs)"
echo ""
echo "  Observability:"
echo "    Grafana         http://localhost:3000  (admin/admin)"
echo ""
echo "  Load test:"
echo "    USER_GEN_URL=http://localhost:8000 \\"
echo "    TICKET_MGR_URL=http://localhost:8001 \\"
echo "    TICKET_INFO_URL=http://localhost:8002 \\"
echo "    CART_URL=http://localhost:8003 \\"
echo "    ./run-load-test.sh"
echo ""
echo "  Note: port-forwards run in background — they stop when this terminal closes."
echo ""
