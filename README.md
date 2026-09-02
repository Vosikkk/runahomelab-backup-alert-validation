# runahomelab backup alert — validation MVP

This validates one behavior only:

`guide → button → Telegram → test alert received`

It does not connect to Proxmox yet, accept backup webhooks, monitor silence, bill users, or provide a dashboard.

## Setup
1. Create a bot with `@BotFather` and save its token + username.
2. `cp .env.example .env` and fill the values.
3. Run with `docker compose up -d --build`.
4. Put Caddy/nginx/Cloudflare Tunnel in front as `https://alerts.runahomelab.com`.
5. Register the Telegram webhook:

```bash
set -a; source .env; set +a
python register_webhook.py
```

## Stored data
SQLite `validation_sessions` stores only random session token, Telegram chat ID, and timestamps.

Validation query:

```sql
SELECT COUNT(*) sessions,
       SUM(connected_at IS NOT NULL) connected,
       SUM(test_completed_at IS NOT NULL) completed
FROM validation_sessions;
```

## Do not build next until this gets usage
Only after completed tests prove demand, add personal `/i/<token>` Proxmox webhook URLs, last-success heartbeat, 26h silence alerts, history, billing.
