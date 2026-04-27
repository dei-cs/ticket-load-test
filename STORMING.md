## Redis
There are two Redis architecture styles which are easy to deploy and contributes to uphold cache availability and optimize for cache hits
- Cache Worker Service
- Master / Slave replication of redis service



## DB
Manage contraints at DB level
ticket-manager/main.py already owns schema setup, add contraints here so they init on app startup