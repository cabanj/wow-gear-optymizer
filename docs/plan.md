# First deliverable — plan, compose, ryzyka

## Docker Compose (szkic)
```yaml
services:
  web:
    build: ./app
    env_file: .env
    depends_on: [postgres]
  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
  simulator:
    image: simulationcraftorg/simc:${SIMC_IMAGE_TAG}   # pinned
    entrypoint: ["python", "/app/worker.py"]           # cienki worker w kontenerze simc
    volumes: [simwork:/work]
  proxy:
    image: caddy:2
    ports: ["80:80", "443:443"]
```
simulator = official simc image + nasz mini-worker (poll PG queue, odpala simc, zapisuje json2). Wersja silnika niezależna od web.

## Plan implementacji (fazy)
1. ✅ Research API (docs/api.md)
2. ✅ Architecture docs
3. Skeleton: FastAPI + Postgres + Alembic + .env + docker-compose; healthcheck
4. OAuth Blizzard (auth code flow, token store, refresh) + /profile/user/wow discovery
5. Character selection UI + snapshoty (armory), import /simc
6. SimC integration: profile builder (local_json baseline), profilesets, json2 parser, version detection — test na 1 postaci
7. Content discovery (Journal + M+ season) + candidate items + upgrade_rules
8. Ranking + raport HTML (raid/m+ tabs, filtry, sort)
9. Multi-char dashboard, history, wykres baseline DPS
10. Cron daily 12:00 Europe/Warsaw + failure handling
11. Testy (patrz lista w specyfikacji) + CI w GH Actions? (opcjonalnie)

Kolejność zgodna z fazami 3–10 z briefu. Każda faza: pokazać efekt przed commitem.

## Ryzyka i ograniczenia
| Ryzyko | Impact | Mitygacja |
|---|---|---|
| SimC json2 format zmienia się między wersjami | parser breaks | version-aware parser + testy snapshot json2 per wersja; pinned image |
| Journal API nie pokazuje wszystkich bonus IDs / variantów | brakujące kandydatki | uzupełnienie z SimC client data (items.json z repo simc); cache tygodniowy |
| Protected character profile (403) | brak snapshotu | wymagany user OAuth + 2FA; komunikat w UI |
| /profile/user/wow pokazuje tylko ostatnio grałe postacie | postać nieaktualna | import na żądanie po realm+name (manual add) |
| VPS CPU: dużo kandydatów × 2 profile types | długi runtime | prescreen ilvl, MAX_CANDIDATES, threads config, sequential nights OK |
| Mythic+ ilvl/track zmiana sezonowa | zły ranking | upgrade_rules.py data-driven, cache season |
| Armory delay | nieaktualny DPS | manual /simc import (dokładniejszy), warning o wieku snapshotu |
| Blizzard rate limit / outage | brak raportu | cache, backoff, fallback na stary snapshot, raport z flagą |
| DPS spec bez wsparcia APL w SimC | brak wyników | simc exit code 72 → raport failed, komunikat |
| Raidbots nie jest używany jako silnik | brak fallback symulacji | założenie świadome; opcjonalny link do Raidbots w UI (manual), bez reverse-engineeringu |

## Konfiguracja (.env)
BLIZZARD_CLIENT_ID, BLIZZARD_CLIENT_SECRET, BLIZZARD_REGION=eu, BLIZZARD_LOCALE=en_GB,
DATABASE_URL, SECRET_KEY (Fernet for tokens),
SIMC_PATH (w kontenerze simulator), SIMC_IMAGE_TAG,
REPORT_PATH, RAID_SIM_ITERATIONS, MPLUS_SIM_ITERATIONS, RAID_TARGET_ERROR, MPLUS_TARGET_ERROR,
RAID_FIGHT_STYLE=Patchwerk, RAID_DURATION=300, MPLUS_FIGHT_STYLE=DungeonSlice,
MAX_CANDIDATES_PER_SLOT=3, SIM_TIMEOUT_SECONDS=3600,
CRON_TZ=Europe/Warsaw, CRON_REPORT=0 12 * * *