#!/bin/zsh

set -e

# ===== CONFIG =====

NAMESPACE="ticket-system"

# ===== START MINIKUBE =====

echo "=============================="
echo "Starting minikube"
echo "=============================="

# minikube start is a no-op when already running
# --cpus/--memory ignored on existing profile; to resize: minikube delete && re-run this script
minikube start --cpus=8 --memory=15973

echo ""
echo "=============================="
echo "Waiting for API server"
echo "=============================="
kubectl wait --for=condition=Ready node --all --timeout=120s

# minikube VM DNS may point at host resolver (192.168.65.254) which can't resolve external names
# patch to 8.8.8.8 so image pulls work; this is idempotent
minikube ssh "sudo sh -c 'echo nameserver 8.8.8.8 > /tmp/resolv.conf && cp /tmp/resolv.conf /etc/resolv.conf'" 2>/dev/null || true

# ===== ADDONS (one-time, idempotent) =====

echo ""
echo "=============================="
echo "Enabling addons"
echo "=============================="

minikube addons enable metrics-server
minikube addons enable ingress

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

echo ""
echo "=============================="
echo "Waiting for observability"
echo "=============================="
kubectl rollout status deployment/postgres-exporter -n $NAMESPACE --timeout=120s
kubectl rollout status deployment/pgbouncer-exporter -n $NAMESPACE --timeout=120s
kubectl rollout status deployment/prometheus -n $NAMESPACE --timeout=120s
kubectl rollout status deployment/grafana -n $NAMESPACE --timeout=120s
echo "Waiting for ingress controller"
echo "=============================="
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s

# Apply ingress after controller is ready (webhook requires controller to be running)
kubectl apply -f k8s/ingress/cart-ingress.yaml

# ===== PORT FORWARDS =====
# minikube docker driver on macOS: node IP not reachable from host, use port-forward instead

echo ""
echo "=============================="
echo "Starting port-forwards"
echo "=============================="

# Kill any stale port-forwards from a previous run
pkill -f "kubectl port-forward.*ticket-system" 2>/dev/null || true
pkill -f "kubectl port-forward.*ingress-nginx"  2>/dev/null || true
sleep 1

kubectl port-forward -n $NAMESPACE    svc/ticket-manager           8001:8001 &>/dev/null &
kubectl port-forward -n $NAMESPACE    svc/ticket-info              8002:8002 &>/dev/null &
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8003:80   --address 0.0.0.0 &>/dev/null &
kubectl port-forward -n $NAMESPACE    svc/grafana                  3000:3000 &>/dev/null &

sleep 2

echo ""
echo "=============================="
echo "Cluster ready"
echo "=============================="
echo ""
echo "  Services:"
echo "    ticket-manager  http://localhost:8001  (swagger: /docs)"
echo "    ticket-info     http://localhost:8002  (swagger: /docs)"
echo "    cart            http://localhost:8003  (via ingress — load-balanced across all replicas)"
echo ""
echo "  Observability:"
echo "    Grafana            http://localhost:3000  (admin/admin)"
echo "    postgres-exporter  :9187/metrics  (custom queries: connection health, bgwriter)"
echo "    pgbouncer-exporter :9127/metrics  (pool utilization, client wait, maxwait)"
echo ""
echo "  Load test:"
echo "    TICKET_MGR_URL=http://localhost:8001 \\"
echo "    TICKET_INFO_URL=http://localhost:8002 \\"
echo "    CART_URL=http://localhost:8003 \\"
echo "    ./run-load-test.sh"
echo ""
echo "  Note: port-forwards run in background — they stop when this terminal closes."
echo ""
