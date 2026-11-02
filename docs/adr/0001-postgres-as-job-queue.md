# Postgres is the job queue; no Redis

At 5–20 Suppliers and up to 5,000 Variants, stock checks are queued in a Postgres jobs table claimed with `SELECT … FOR UPDATE SKIP LOCKED`. Redis was rejected to keep the deployment at three containers (API, worker, Postgres). Revisit only if queue throughput becomes a bottleneck.
