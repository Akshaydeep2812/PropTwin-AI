# Database

The schema is defined by the SQLAlchemy models and created by Alembic migrations in `backend/alembic/`. See [docs/DATABASE_SCHEMA.md](../docs/DATABASE_SCHEMA.md).

| Path | Contents |
|---|---|
| `schema/init-test-db.sh` | Creates the `proptwin_test` database the first time the Docker volume starts |
| `seed/seed_demo.py` | Loads fictional demo users, properties and market data |

```powershell
python database/seed/seed_demo.py
```

The seed is safe to run again and refuses to run in production. Every record it creates is flagged as demo or synthetic. Demo passwords come from `DEMO_PASSWORD`, or are generated and printed once.
