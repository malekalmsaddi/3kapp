# Moeen AI — Multi-Tenant SaaS Platform

## Architecture

Multi-tenant WhatsApp AI assistant platform. Flask backend, Next.js frontend, Celery workers, PostgreSQL, Redis.

### Tenant Model
- All data scoped by `tenant_id` (UUID foreign key)
- Default/legacy tenant: `00000000-0000-0000-0000-000000000001` (slug: `moeen`)
- Roles: `super_admin` (platform), `tenant`

### Backend Structure
```
app.py              — Flask factory with blueprint registration (~130 lines)
blueprints/         — Route handlers (auth, webhook, dashboard, messaging, admin, platform, onboarding, settings)
services/           — Business logic (tenant_service, auth_service, entitlements, usage_rollup)
services/ai/        — AI provider abstraction (base ABC, openai_assistants, factory)
middleware/         — JWT decode middleware
crypto.py           — Fernet encryption for stored secrets
db.py               — All DB queries (every function takes tenant_id)
tasks.py            — Celery tasks (all take tenant_id as first arg)
redis_client.py     — TenantRedis wrapper (auto-prefixes keys with tenant:{id}:)
```

### Auth
- JWT HttpOnly cookies (access_token 24h, refresh_token 7d)
- Backward compat: also accepts Flask session['logged_in'] for legacy frontend
- JWT payload: `{sub, tid, tslug, role, email, jti, iat, exp}`

### Key Patterns
- **DB queries**: all accept `tenant_id` param, defaults to `LEGACY_TENANT_ID`
- **Redis keys**: `tenant:{uuid}:msg:{sid}`, `tenant:{uuid}:active_run:thread:{tid}`, etc.
- **Celery tasks**: `process_openai(tenant_id, user_number, user_message)`
- **Webhook routing**: `/whatsapp/<tenant_slug>` identifies the tenant

### Environment Variables
Required: `DATABASE_URL`, `REDIS_URL`, `FLASK_SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, `OPENAI_API_KEY`, `ASSISTANT_ID`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`

## Commands

```bash
# Run migration
python migrations/run_migration.py

# Run Flask
python app.py

# Run Celery worker
celery -A tasks.celery_app worker --loglevel=info

# Run Celery Beat (for usage rollup)
celery -A tasks.celery_app beat --loglevel=info

# Run frontend
cd frontend && npm run dev

# Run tests
pytest tests/ -v
```

## Test Patterns
- `tests/test_tenant_isolation.py` — integration tests verifying cross-tenant data isolation
- Tests need `DATABASE_URL` and `REDIS_URL` in env
