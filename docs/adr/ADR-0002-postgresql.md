# ADR-0002: PostgreSQL as the Primary Database

> **Status:** Accepted
>
> **Date:** 2026-06-27 (Sprint 0.1)
>
> **Deciders:** Platform team
>
> **Technical Story:** [MCAICD-1](https://github.com/manikantadakarapu/multi-cloud-ai-cost-detective/issues/1) — Backend foundation

---

## Context

MCAICD needs a primary data store for the unified cost schema, anomaly
detection state, AI recommendation outputs, and future entities (users,
organisations, alert rules, audit logs). The store must handle structured
relational data (cost records, provider metadata) and semi-structured data
(API responses, tags, recommendation rationales) with strong consistency,
transactional guarantees, and operational maturity. The decision was made at
project inception (Sprint 0.1) alongside the framework choice.

---

## Decision

**Adopt PostgreSQL 16 as the primary database, accessed via async SQLAlchemy
2.x and the `asyncpg` driver.**

The platform commits to:

- **Async driver:** `postgresql+asyncpg://` — binary protocol, native async,
  connection pooling.
- **ORM:** SQLAlchemy 2.x declarative models with async sessions.
- **Migrations:** Alembic with an async `env.py` runner.
- **Naming conventions:** Deterministic constraint names (`fk_`, `pk_`,
  `ix_`, `uq_`, `ck_`) via `app/database/base.py`.
- **Connection pooling:** Tunable pool size, overflow, timeout, and recycle
  via `Settings` (`app/core/config.py`).
- **Health probe:** A live `SELECT 1` round-trip on every `GET /api/v1/health`
  call, with `pool_pre_ping` to detect stale connections.

---

## Alternatives Considered

### MongoDB

| Criterion | Assessment |
| --------- | ---------- |
| **Schema flexibility** | Excellent for semi-structured cloud billing payloads. |
| **JSON support** | Native BSON; no mapping layer needed. |
| **Transactions** | Multi-document ACID transactions since 4.0, but not the default mental model. |
| **Operational maturity** | Mature, but the tooling ecosystem (backup, point-in-time recovery, logical replication) is less standardised than PostgreSQL. |
| **Async driver** | `motor` is solid, but the ORM ecosystem is thinner. |
| **Cost data fit** | Billing data is inherently relational: resource → provider → region → service → time series. A document model forces denormalisation or `$lookup` joins. |
| **Team familiarity** | Lower than PostgreSQL for relational workloads. |

**Verdict:** Rejected. The cost domain is relational at its core. MongoDB's
flexibility is a liability when the schema is known and the queries are
analytical (aggregations across provider, region, time). PostgreSQL's
`jsonb` column type captures the semi-structured parts without sacrificing
relational integrity.

### MySQL

| Criterion | Assessment |
| --------- | ---------- |
| **Reliability** | Proven at massive scale (Facebook, Uber, GitHub). |
| **JSON support** | `JSON` column type since 5.7, improved in 8.0. Functional indexes on JSON paths. |
| **Async driver** | `aiomysql` exists but is less mature than `asyncpg`. Connection pooling is less sophisticated. |
| **Operational maturity** | Excellent, but the async story in Python is weaker. |
| **Cost data fit** | Equivalent to PostgreSQL for relational workloads. |
| **Ecosystem** | The Python async ecosystem has standardised on `asyncpg`/PostgreSQL. |

**Verdict:** Rejected. The async driver maturity and the Python community
convergence on PostgreSQL for async workloads make MySQL a second-tier
choice for this stack.

### SQLite

| Criterion | Assessment |
| --------- | ---------- |
| **Simplicity** | Zero-config, file-based. Ideal for tests and local development. |
| **Async support** | `aiosqlite` works, but the concurrency model is single-writer. |
| **Production viability** | Not suitable for concurrent write workloads or networked access. |
| **JSON support** | `json1` extension, but no `jsonb` binary storage or indexing. |
| **Use case** | **Accepted for testing only.** The test suite can use an in-memory
  SQLite database for speed. Not for production. |

**Verdict:** Rejected for production. Accepted as a test-time alternative
(planned for integration tests with a dedicated test database, not SQLite,
to catch PostgreSQL-specific behaviour).

### PostgreSQL

| Criterion | Assessment |
| --------- | ---------- |
| **Reliability** | 30+ years of production use. ACID by default. WAL-based durability. |
| **JSON support** | `jsonb` (binary, indexed, GIN/GiST) since 9.4. First-class semi-structured support. |
| **Indexes** | B-tree, hash, GiST, SP-GiST, GIN, BRIN. Partial, expression, and covering indexes. |
| **Scalability** | Read replicas, logical replication, partitioning (native since 10), parallel query. |
| **Async driver** | `asyncpg` is the gold standard — binary protocol, prepared statements, pooling. |
| **ORM integration** | SQLAlchemy 2.x async support is PostgreSQL-first. |
| **Operational tooling** | `pg_dump`, `pg_restore`, `pg_basebackup`, `pg_stat_statements`, `auto_explain`, `pgbadger`. Industry-standard. |
| **Cloud availability** | Managed service on AWS (RDS/Aurora), Azure (Flexible Server), GCP (Cloud SQL/AlloyDB). |
| **Cost data fit** | Relational core + `jsonb` for provider-specific payloads + time-series partitioning = perfect match. |

**Verdict:** Accepted. PostgreSQL is the default choice for a Python async
service with relational and semi-structured data.

---

## Consequences

### Positive

- **Unified data model:** Cost records, anomalies, recommendations, and
  future entities live in one transactional store. Cross-entity queries
  (e.g., "show anomalies with their recommendations") are simple joins.
- **`jsonb` for provider payloads:** Each cloud provider's native billing
  schema is stored verbatim in a `jsonb` column alongside the normalised
  columns. No data loss, full queryability via `->>` and GIN indexes.
- **Time-series ready:** Native partitioning by time (planned for the cost
  table) enables efficient retention and range queries.
- **Operational confidence:** The team knows PostgreSQL. The tooling is
  standard. On-call runbooks exist.
- **Async performance:** `asyncpg` + `pool_pre_ping` + tuned pool settings
  give predictable latency under load.
- **Migration safety:** Alembic + deterministic naming conventions mean
  migrations are reviewable and reversible.

### Negative

- **Operational overhead:** A PostgreSQL instance requires backups, vacuum
  monitoring, connection pooling (PgBouncer at scale), and version upgrades.
  Mitigated by using managed services in production (RDS, Cloud SQL, Azure
  PostgreSQL).
- **Single-writer bottleneck:** At very high write throughput, a single
  primary can saturate. The ingestion workload is batched and scheduled, not
  real-time streaming, so this is not a near-term concern.
- **No native vector search:** If the AI layer embeds cost patterns for
  similarity search, `pgvector` is an extension, not core. Acceptable — the
  extension is mature and managed-service-compatible.

### Neutral

- **Schema migrations are required:** Unlike a schemaless store, every
  change goes through Alembic. This is a feature, not a bug — it forces
  intent review.

---

## Future Considerations

- **Read replicas for reporting:** Dashboard queries (Sprint 0.7) will
  route to a read replica to isolate analytical load from ingestion writes.
- **TimescaleDB / partitioning:** If cost data volume exceeds single-table
  performance, native partitioning by `billing_period` or migration to
  TimescaleDB (PostgreSQL extension) is a drop-in change.
- **PgBouncer:** When connection count exceeds the primary's `max_connections`,
  PgBouncer in transaction-pooling mode sits in front. The application's
  pool settings (`db_pool_size`, `db_max_overflow`) are tuned for direct
  access today; they will be retuned for PgBouncer when needed.
- **Logical replication for CDC:** If downstream systems need change-data
  capture (e.g., a data warehouse), logical replication slots are the
  standard path.
- **Vector embeddings:** If anomaly detection uses embedding similarity,
  `pgvector` adds HNSW/IVFFlat indexes on `vector` columns. No schema
  migration to a separate vector DB required.

---

## References

- [PostgreSQL 16 Documentation](https://www.postgresql.org/docs/16/)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/current/)
- [SQLAlchemy 2.x Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [ADR-0001: FastAPI](../adr/ADR-0001-fastapi.md) — the async framework that requires an async driver
- [ADR-0003: Clean Architecture](../adr/ADR-0003-clean-architecture.md) — the layering that isolates database access in the service layer
