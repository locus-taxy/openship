# PostgreSQL: `permission denied for schema public`

On **PostgreSQL 15+**, the `public` schema no longer allows every user to create objects. If Alembic fails with:

`permission denied for schema public`

connect in **pgAdmin** (or `psql`) as a **superuser** (often `postgres`), select database **`openship`**, and run:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO kshitij;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO kshitij;
```

Replace `kshitij` with your app DB user if different.

Then restart the API so startup migrations (or `alembic upgrade head`) can create `alembic_version`, `skills`, and `daily_tasks`.
