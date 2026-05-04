#!/bin/zsh

set -e  # exit on error

# ===== CONFIG =====

REGISTRY="deidock"

# Tag strategy: git SHA + latest

TAG=$(git rev-parse --short HEAD)

# Define your services manually

# Format: "service_name:path_to_docker_context"

services=(
"user-generator:./user-generator"
"ticket-info:./ticket-info"
"cart:./cart"
"ticket-manager:./ticket-manager"
)

# ===== BUILD & PUSH =====

for entry in "${services[@]}"; do
service_name="${entry%%:*}"
context_path="${entry##*:}"

image_latest="$REGISTRY/ticket-load-test-${service_name}:latest"
image_tagged="$REGISTRY/ticket-load-test-${service_name}:${TAG}"

echo "=============================="
echo "Building $service_name"
echo "Context: $context_path"
echo "Tags: $TAG, latest"
echo "=============================="

docker build -t "$image_tagged" -t "$image_latest" "$context_path"

echo "Pushing $image_tagged"
docker push "$image_tagged"

echo "Pushing $image_latest"
docker push "$image_latest"

echo "Done $service_name"
echo ""
done

echo "🎉 All services built and pushed successfully"
