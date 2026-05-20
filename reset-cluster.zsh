#!/bin/zsh

set -e

NAMESPACE="ticket-system"

echo "=============================="
echo "Tearing down namespace"
echo "=============================="

kubectl delete namespace $NAMESPACE --ignore-not-found=true
kubectl wait --for=delete namespace/$NAMESPACE --timeout=120s 2>/dev/null || true

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
kubectl rollout status deployment/prometheus -n $NAMESPACE --timeout=120s
kubectl rollout status deployment/grafana -n $NAMESPACE --timeout=120s

kubectl apply -f k8s/ingress/cart-ingress.yaml

echo ""
echo "=============================="
echo "Restarting port-forwards"
echo "=============================="

pkill -f "kubectl port-forward.*ticket-system" 2>/dev/null || true
pkill -f "kubectl port-forward.*ingress-nginx"  2>/dev/null || true
sleep 1

kubectl port-forward -n $NAMESPACE    svc/ticket-manager           8001:8001 &>/dev/null &
kubectl port-forward -n $NAMESPACE    svc/ticket-info              8002:8002 &>/dev/null &
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8003:80   --address 0.0.0.0 &>/dev/null &
kubectl port-forward -n $NAMESPACE    svc/grafana                  3000:3000 &>/dev/null &

echo ""
echo "=============================="
echo "Cluster reset"
echo "=============================="
