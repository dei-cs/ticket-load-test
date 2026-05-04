## Redis
There are two Redis architecture styles which are easy to deploy and contributes to uphold cache availability and optimize for cache hits
- Cache Worker Service
- Master / Slave replication of redis service



## DB
Manage contraints at DB level
ticket-manager/main.py already owns schema setup, add contraints here so they init on app startup



## Our main bottlenecks for concurrency ATM
- cart/main.py and ticket-info/main.py db max connection pool



## Relevant topics for report
- Connection pooling (we use PgBouncer)
    - This is probably our biggest bottleneck?
    - Future research: what could be do to avoid connection pooling bottleneck?



## Kubernetes
kubectl apply -f k8s/namespace.yaml

kubectl apply -f k8s/secrets/

kubectl apply -f k8s/observability/

kubectl apply -f k8s/pgbouncer/

kubectl apply -f k8s/postgres/

kubectl apply -f k8s/pgbouncer/

kubectl apply -f k8s/observability/

kubectl apply -f k8s/apps/

Step X: Verify and Access
Check pod status: kubectl get pods -n ticket-system
Check services: kubectl get services -n ticket-system
Access apps (if using NodePort):
Cart: http://<node-ip>:30003
User Generator: http://<node-ip>:30000
Ticket Manager: http://<node-ip>:30001
Ticket Info: http://<node-ip>:30002
Access observability:
Grafana: http://<node-ip>:30000 (port 3000, default user: admin/admin)
Prometheus: http://<node-ip>:30001 (port 9090)


## TODOs prio list
1. Deploy on kubernetes (Kubernetes Manifest) + replicate cart
2. Make load testing + monitoring work
3. Introduce DB constraints
4. Add Redis