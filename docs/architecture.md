# Architecture — WoW Gear Upgrade Analyzer

## Zasada ogólna
Self-hosted app na VPS (Docker Compose). Backend Python/FastAPI, PostgreSQL, SimulationCraft CLI jako osobny kontener (worker), serwerowe HTML reports. Simulation = lokalny SimC (NIE Raidbots).

## Komponenty (docker-compose)
```
web        FastAPI: OAuth, API, SSR UI, raporty HTML, scheduler (APScheduler w procesie web)
postgres   Postgres 16 (volume)
simulator  kontener z simc CLI (obraz simulationcraftorg/simc nightly, pinowany tagiem)
           tryb: invoked by web via `docker exec` LUB prosty HTTP worker (FastAPI + kolejka w PG)
proxy      Caddy (TLS via Let's Encrypt, reverse proxy)
```
Komunikacja web↔simulator: prosta kolejka w Postgres (tabela simulation_runs, status pending→running→done/failed);
simulator polluje albo web wywołuje `docker compose exec simulator simc ...`. Wybieramy **kolejkę PG + simulator jako worker** — niezależna wersja silnika, restart bez utraty stanu.

## Przepływ dzienny (cron 12:00 Europe/Warsaw, APScheduler z tz lub system cron z CRON_TZ)
1. Odśwież snapshoty wybranych postaci z Blizzard (client-credentials token dla Game Data; user token dla Profile API jeśli aktywna sesja; fallback: ostatni snapshot, oznacz wiek).
2. Content discovery: Journal API → aktualny raid (tier z najnowszej daty), Mythic+ season (mythic-keystone/season index → current season → dungeons). Cache z TTL.
3. Build candidate items: loot tables raid bossów + dungeonów × polityka upgrade tracków (moduł `upgrade_rules.py`, konfigurowalny, dane z client-data SimC / weekly cache).
4. Dla każdej postaci: baseline + profilesets (raid i m+ osobno), json2 output.
5. Parsowanie wyników, delta, ranking, zapis do DB, generacja HTML report, status=completed.
6. Failure handling: nigdy nie nadpisuj ostatniego poprawnego raportu; raport z fallback snapshotu dosta­je WARNING + wiek snapshotu.

## OAuth (backend-only)
- Authorization Code Flow: `/auth/blizzard` → `oauth.battle.net/authorize` (scope `wow.profile`, state=HttpOnly cookie) → `/auth/blizzard/callback` → token exchange.
- Tokeny: server-side (DB, encrypted przy Fernet + SECRET_KEY); refresh po stronie serwera. Browser dostaje tylko session cookie (httponly, secure, samesite=lax).
- Client credentials flow (app-only) do Game Data API.
- Sekrety wyłącznie env/.env (nigdy w repo).

## Moduły backendu
```
app/
  auth/         blizzard oauth, session, token store
  blizzard/     client (profile, game data, journal, mythic-keystone), cache (TTL w PG)
  characters/   import, snapshot (armory + manual /simc), selection
  loot/         content discovery, candidate items, item metadata, item identity (id+bonus_ids+ilvl+track)
  simc/         profile builder (baseline, profilesets), simc runner adapter, json2 parser, version info
  reports/      ranking, delta, html generation, history
  scheduler/    daily job
  upgrade_rules.py   jedyny punkt logiki tracków/difficulty per patch
```

## Frontend
SSR Jinja2 + mało vanilla JS (fetch do własnego API). Zero frameworka — wystarczy: wybór postaci (checkboxy), dashboard per postać, ranking z filtrami/sortowaniem, history, wykres (svg inline).
