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

## Optimization concernes
- Expensive database queries (@cart/services/cart_service.py)

## Application flow:
1. User Generator (@user-generator/data/query_user.py) and Ticket manager (@ticket-manager/data/query_ticket.py) pre-seeds users and tickets in the database.
2. Ticket info reads the database on

## Prio list as pr 08/05:
1. Automated reservation indexing based on availability data
    - [ ] Need to be able to differ between two different exceptions, NoTicketsAvailableError and TicketDoubleBookingError.
2. Database constraints
    - [ ] Lock resource during commit in flight
    - [ ] Primary key on ticket id
3. Apache test loop running
4. Monitoring with metrics differing between reservation failure reasons (double booking vs no tickets available)
5. Redis for caching ticket availability data
    - [ ] Redis pub/sub and scale ticket-info horizontally

- How does request get distributed in cart?
- Scale pool size with resource limits and HPA

## Monitoring commands:
- kubectl get pods -n ticket-system
- kubectl logs -n ticket-system deployment/cart -tail 100
- stern -n ticket-system -l app=cart (live monitor all cart replicas)
- kubectl get events -n ticket-system --sort-by='.lastTimestamp'
- kubectl get hpa -n ticket-system -w 

## What to adjust during tests:
- Enable/disable HPA (for constant replica count)
- Resource allocation
- Replica min/max
- Redis will not have a big advantage unless we dynamically change the available ticket count

## Enable/disable Redis
- docker-compose.yml:47 — REDIS_ENABLED: "false"
- k8s/apps/ticket-info/ticket-info-deployment.yaml:29 —
  REDIS_ENABLED: "false"

# enable
  kubectl set env deployment/ticket-info -n ticket-system REDIS_ENABLED=true

# disable
  kubectl set env deployment/ticket-info -n ticket-system REDIS_ENABLED=false


  ### Network
  - ipconfig getifaddr en0
  - kubectl port-forward -n ticket-system svc/ticket-manager 8001:8001 --address 0.0.0.0 & kubectl port-forward -n ticket-system svc/ticket-info 8002:8002 --address 0.0.0.0 & kubectl port-forward -n ticket-system svc/cart 8003:8003 --address 0.0.0.0 &
  - pkill -f "kubectl port-forward.*ticket-system"
  - minikube tunnel (for LoadBalancer services)
  - kubectl get svc cart -n ticket-system


  ### Ideas for writing
  - Kubernetes Manifest and deployment strategy/process
  - Resource allocation and optimization
  - HPA configuration and impact on performance
  - Redis integration and its effect on performance
  - Database constraints and their role in ensuring data integrity and performance
  - Client connections constraints in our test setup

Testing 100 iterations across 300000 tickets with 3000 concurrent users attempting to reserve.

before running a test run
- run set-cart-profile.zsh
- check pods up with kubectl get pods -n ticket-system
- check pods up with stern -n ticket-system -l app=cart
- port forward grafana
- enable/disable redis
- warm cache if redis enabled
- add tickets to db
- note test start time stamp
- start minikube tunnel

start at:

Postgres max connections: 100
PgBouncer pool size: 50
Postgres spiking at 30% CPU
Postgres at 70% connection usage
pgbouncer at 20% pool utilization
throughput ~480 requests pr second

postgres max connections: 150
PgBouncer pool size: 100
Postgres spiking at 30% CPU
Postgres at 30% connection usage
pgbouncer at 90% pool utilization
throughput ~490 requests pr second

postgres max connections: 250
PgBouncer pool size: 200
Postgres spiking at 30% CPU
Postgres at 45% connection usage
pgbouncer at 110% pool utilization
throughput ~490 requests pr second


⏺ Two different things at two different hops:

  cart 3 replicas with 4 workers each with 3 client connections each (408 client conns) → pgbouncer → postgres (server conns)

  - max_client_conn = 2000 — pgbouncer accepts up to 2000 connections from apps (cart side)
  - max_connections = 250 — postgres accepts up to 250 connections from pgbouncer (server side)

  pgbouncer's job is to multiplex those 408 cart client connections into at most default_pool_size 
  = 200 actual postgres server connections. Postgres never sees 408 — it sees at most 200 from
  pgbouncer plus a handful from exporters.

  So both numbers are correct and consistent.

PG bouncer accepts up to 2000 client connections
Postgres accepts at most 250 server connections from pgbouncer (bouncer acts as a limiter and multiplexer)
Need to decide on a good amout of workers pr replica and client connections pr worker to optimize throughput while avoiding connection bottlenecks at pgbouncer and postgres.