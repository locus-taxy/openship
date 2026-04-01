# Database & ORM Selection — Openship

**Author:** Yogesh K  
**Date:** March 31, 2026  
**Status:** Proposal  

---

## 1. Current State

Openship currently uses **SQLite** with raw SQL queries (Python `sqlite3` module). There is no ORM
and no migration system. Tables are created via `CREATE TABLE IF NOT EXISTS` at application startup,
with manual `ALTER TABLE` statements for schema evolution.

### Current Tables


| Table         | Purpose                                                |
| ------------- | ------------------------------------------------------ |
| `skills`      | Stores user subscriptions (email, skill, days, hours)  |
| `daily_tasks` | Stores syllabus items and generated newsletter content |


### Problems with the Current Approach


| Problem                      | Impact                                                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **No ORM**                   | Raw SQL scattered across `db_service.py` and `syllabus_generator.py`. Manual tuple-to-dict mapping in every query. Error-prone and hard to maintain.                                       |
| **No migration system**      | Schema changes rely on `PRAGMA table_info` + manual `ALTER TABLE`. No rollback capability, no migration history, no team collaboration on schema changes.                                  |
| **SQLite limitations**       | Single-writer model — only one process can write at a time. No concurrent access support. No built-in user/role management. Not suitable for production deployments with multiple workers. |
| **No foreign keys enforced** | `daily_tasks.skill_id` references `skills.id` but there is no `FOREIGN KEY` constraint. Orphaned records can exist.                                                                        |
| **No connection pooling**    | Every function opens and closes its own `sqlite3.connect()` call. No reuse, no pooling.                                                                                                    |


---

## 2. Database Selection: PostgreSQL

### Options Evaluated


| Database             | Strengths                                                                                                                | Weaknesses                                                                                                             | Verdict                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| **SQLite** (current) | Zero setup, file-based, good for prototyping                                                                             | Single-writer, no concurrency, no network access, limited types                                                        | Not suitable for production |
| **MySQL**            | Mature, widely supported, good performance                                                                               | Weaker JSON support, fewer modern features, less active open-source ecosystem compared to PostgreSQL                   | Viable but not preferred    |
| **PostgreSQL**       | Full ACID, excellent concurrency (MVCC), rich data types (JSON, arrays), full-text search, extensions, massive ecosystem | Slightly more setup than SQLite                                                                                        | **Recommended**             |
| **MongoDB**          | Flexible schema, good for unstructured data                                                                              | Our data is clearly relational (users → skills → tasks). Would require denormalization and lose referential integrity. | Not suitable                |


### Why PostgreSQL

1. **Relational data model fits perfectly** — Users own Skills, Skills contain DailyTasks. Foreign keys and joins are natural here.
2. **Concurrency** — MVCC (Multi-Version Concurrency Control) allows multiple readers and writers simultaneously. Critical when running multiple Uvicorn workers.
3. **JSON support** — `jsonb` columns can store Gemini API responses or newsletter metadata without schema changes.
4. **Full-text search** — Built-in `tsvector` can power skill/topic search without an external service.
5. **Production-ready hosting** — Free/cheap managed options: Supabase, Neon, Railway, Render, AWS RDS Free Tier.
6. **Ecosystem** — Best-supported database across Python ORMs (SQLAlchemy, SQLModel, Django ORM, Tortoise).
7. **Extensions** — `pg_cron` for scheduled newsletter jobs, `pgcrypto` for password hashing at DB level if needed.

### Connection Configuration

```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/openship
```

For local development: Docker container or native install.  
For production: Managed PostgreSQL (Supabase / Neon / Railway recommended for simplicity).

---

## 3. ORM Selection: SQLModel + Alembic

### Options Evaluated


| ORM                      | Strengths                                                                                                                       | Weaknesses                                                     | Verdict                 |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------------- |
| **Raw SQL** (current)    | Full control, no abstractions                                                                                                   | No validation, no migrations, manual mapping, error-prone      | Not suitable for growth |
| **SQLAlchemy + Alembic** | Most mature Python ORM, async support, powerful query builder                                                                   | Verbose — requires separate Pydantic models for API validation | Strong option           |
| **SQLModel + Alembic**   | Built by FastAPI creator (tiangolo). Merges SQLAlchemy + Pydantic into one class. Less boilerplate. Native FastAPI integration. | Younger project, fewer advanced features than raw SQLAlchemy   | **Recommended**         |
| **Tortoise ORM**         | Async-first, Django-inspired                                                                                                    | Smaller ecosystem, less community support                      | Not preferred           |
| **Prisma (Python)**      | Great schema language, auto migrations                                                                                          | Python client is less mature than JS/TS version                | Not preferred           |


### Why SQLModel

1. **One class = DB table + API model** — Currently, we maintain Pydantic models in `models/main.py` AND raw SQL schemas in `db_service.py` separately. SQLModel unifies them.
2. **Built for FastAPI** — Same creator, designed to work together. Models are directly usable as request/response types.
3. **SQLAlchemy under the hood** — All of SQLAlchemy's power (joins, relationships, complex queries) is available when needed.
4. **Alembic migrations** — Auto-generates migration scripts from model changes. Full version history, rollback support.
5. **Async support** — Can be extended with async drivers when needed.

### Proposed Schema (SQLModel)

```python
# models/user.py
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    name: str = Field(max_length=100)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

# models/skill.py
class Skill(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    skill: str = Field(max_length=200)
    days: int = Field(default=90, gt=0)
    hours: int = Field(default=1, gt=0)
    stop_sending: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

# models/daily_task.py
class DailyTask(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    skill_id: int = Field(foreign_key="skill.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    month: int
    week: int
    day: int
    topic: str
    task: str
    hours: float
    newsletter: str | None = None
    completed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Key Changes from Current Schema


| Change                                                                          | Reason                                                               |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `user_id` changes from `TEXT` (UUID string) to `INT` (foreign key to `user.id`) | Proper relational integrity. User must exist before creating skills. |
| `email` removed from `skills` table                                             | Email lives on the `User` model. Accessed via join. No duplication.  |
| `stop_sending` removed from `daily_tasks`                                       | Pause/resume is a skill-level concern, not per-task.                 |
| `skill_id` gets a proper `FOREIGN KEY` constraint                               | Prevents orphaned tasks. Cascade deletes when a skill is removed.    |
| All `INTEGER DEFAULT 0` booleans become proper `BOOLEAN`                        | Type safety.                                                         |


---

## 4. Migration Strategy

### Phase 1: Setup (Day 1)

- Install PostgreSQL (Docker or managed service)
- Add `sqlmodel`, `psycopg2-binary`, `alembic` to `requirements.txt`
- Define SQLModel classes for `User`, `Skill`, `DailyTask`
- Configure Alembic with `alembic init`
- Generate initial migration: `alembic revision --autogenerate -m "initial schema"`

### Phase 2: Rewrite DB Layer (Days 2–3)

- Replace all raw SQL in `db_service.py` with SQLModel queries
- Replace raw SQL in `syllabus_generator.py` with SQLModel queries
- Update `main.py` to use async session dependency injection
- Remove all `sqlite3.connect()` calls

### Phase 3: Data Migration (Day 4)

- Write a one-time script to migrate existing SQLite data into PostgreSQL
- Verify data integrity (row counts, foreign key validity)

### Phase 4: Cleanup (Day 5)

- Remove `sqlite3` imports and `DB_PATH` config
- Update `.env.example` with `DATABASE_URL`
- Update documentation

---

## 5. New Dependencies


| Package           | Version | Purpose                                  |
| ----------------- | ------- | ---------------------------------------- |
| `sqlmodel`        | latest  | ORM (SQLAlchemy + Pydantic)              |
| `psycopg2-binary` | latest  | PostgreSQL driver                        |
| `alembic`         | latest  | Database migrations                      |


---

## 6. Environment Variables

**Legacy (no longer used):**

```env
# DB_PATH=openship.db  ← removed after PostgreSQL migration
```

**Active:**

```env
DATABASE_URL=postgresql+psycopg2://your_user:your_password@localhost:5432/your_db_name
```

---

## 7. Risk Assessment


| Risk                        | Mitigation                                                                   |
| --------------------------- | ---------------------------------------------------------------------------- |
| Data loss during migration  | Write migration script with validation. Keep SQLite file as backup.          |
| Downtime during switchover  | Run both databases in parallel briefly. Switch over when validated.          |
| Learning curve for SQLModel | SQLModel documentation is excellent. Team already knows Pydantic.            |
| PostgreSQL hosting cost     | Free tiers available on Supabase (500MB), Neon (512MB), Railway ($5 credit). |


