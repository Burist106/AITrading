# Supabase Edge Functions

No Supabase Edge Function is implemented in Milestone 1. The authorized control-plane actions are transactional PostgreSQL functions defined and tested in the versioned migrations under `supabase/migrations/`.

Those SQL functions accept authenticated user intents, validate exact typed payloads, enforce owner-scoped idempotency and optimistic resource versions, and write durable commands plus append-only evidence. Dedicated Worker SQL functions support claim, lease, lifecycle, heartbeat, and incident bookkeeping only. Realtime remains disabled and is not the durable command source.

This directory must not contain:

- broker access or position mutation;
- Live Trading support or switches;
- a broad browser write path;
- a service-role key, Worker credential, LINE secret, MT5 credential, or any other real secret.

An Edge Function may be added only in a later explicitly authorized milestone with its own authentication, authorization, idempotency, and security tests. Milestone 1 introduces no network handler or external side effect.
