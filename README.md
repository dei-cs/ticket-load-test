# Thesis Prototype

This thesis investigates this tension through a ticket reservation system. This is chosen as the experimental domain since it has requirements for strict correctness with periods of high concurrency. A ticket is a finite and discrete resource and should be allocated in a manner such that a single ticket can never be reserved or bought by more than one user. This makes this case well suited for studying the tension between a centralized database under high contention. 

The thesis focuses on a prototype rather than a production-scale deployment. The goal is to examine how database pressure develops under load and how connection pooling and in-memory caching affect throughput, latency, and database load when the centralized database remains the source of truth. 

This code repository contains the implementation of the core logic of the ticket reservation system described in chapter 4 & 5 of the thesis. It includes the necessary components to simulate a ticket reservation system, allowing for testing and analysis of database performance under high concurrency.

The repository also contains the Kubernetes manifests used to deploy the prototype on a Kubernetes cluster. This enabled for easy allocation of compute resources and inclusion of open-soruce tools for support and observability.

## Navigation

* The Cart service is implemented in the folder "/cart".
* Ticket-info service is implemented in the folder "/ticket-info".
* Ticket-manager service is implemented in the folder "/ticket-manager".
* The Kubernetes manifests for deployment are located in the folder "/k8s".

## Contributers
Thesis Group Number: SK18459
Members:
- Alfred Bjarneg Schou (74192)
- Daniel Emil Iversen (74206)
- Jonathan Laage Olsen (71396) 