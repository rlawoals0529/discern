# Security

`discern` is a single-user evaluation-history service. Its stored runs may contain prompts, model outputs, and error text, so the HTTP API is private by default and every route requires the same bearer token.

## Application controls

- Every service route uses the `DISCERN_TOKEN` bearer-token dependency.
- If `DISCERN_TOKEN` is missing, the service fails closed with 503 instead of becoming public.
- Token comparison uses `hmac.compare_digest`.
- Failed authentication is rate-limited per source as a bounded, process-local backstop; production should also enforce an edge/distributed auth-abuse limit.
- Request bodies and run sizes are bounded.
- SQL access uses SQLAlchemy parameters rather than request-built SQL strings.
- Responses include CSP, HSTS, frame denial, MIME sniffing protection, referrer and permissions policies.
- The core has no model-provider dependency and does not execute model tools.

## Token rotation

Store `DISCERN_TOKEN` only in the deployment secret manager. Generate a high-entropy token and rotate it:

1. immediately if it appears in source, git history, CI output, logs, screenshots, issues, artifacts, or chat;
2. when access to the deployment environment changes hands;
3. periodically according to the environment's credential policy.

Rotation is intentionally simple: replace the deployment secret and restart/redeploy the service. Do not commit a fallback or previous token.

## Production requirements

Repository code cannot enforce infrastructure controls. Production should also:

- force HTTPS at the proxy/edge;
- rate-limit failed authentication across all service instances;
- run Postgres with an application-specific least-privilege role;
- restrict database network access to the application/private network;
- keep `DATABASE_URL` in managed secrets and rotate it after exposure;
- take encrypted database backups and test a restore on a recurring schedule;
- avoid logging bearer tokens, connection strings, full request bodies, prompt contents, or model outputs unless explicitly required and access-controlled;
- keep dependency/security alerts enabled and patch supported dependencies.

## Reporting

If a credential is exposed, revoke/rotate it first. Deleting the current file is not sufficient because git history, CI logs, caches and artifacts may still contain the old value.
