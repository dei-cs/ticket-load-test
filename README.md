# ticket-load-test

A research prototype simulating a concurrent concert ticketing system. This serves as a **baseline** for studying correctness and performance trade-offs in distributed reservation workflows under high load.

The system is built as a set of microservices using an asynchronous, event-driven architecture backed by Redis Streams and PostgreSQL.
