# Blizzard API — endpointy (zweryfikowane z aktualną dokumentacją, wrzesień 2026)

## OAuth
- Authorize: `GET https://oauth.battle.net/authorize` — params: client_id, redirect_uri, scope=`wow.profile`, state, response_type=code
- Token: `POST https://oauth.battle.net/token` (Basic auth client_id:secret) — grant_type=authorization_code / refresh_token / client_credentials
- **Tokeny przesyłane wyłącznie w HTTP header** (wymóg od 2024-09-30, nie w query string)
- Region: OAuth hosty są globalne (oauth.battle.net); API hosty per region: `eu.api.blizzard.com`, `us.api.blizzard.com`

## Profile API (wymaga user token ze scope wow.profile, namespace `profile-{region}`)
```
GET /profile/user/wow                                    # wszystkie accounts → characters
GET /profile/user/wow/{account_id}                       # per WoW account
GET /profile/wow/character/{realm-slug}/{name}           # character profile summary (status, class, race, ilvl...)
GET /profile/wow/character/{realm-slug}/{name}/status    # czy widoczna
GET /profile/wow/character/{realm-slug}/{name}/equipment # items + bonus_ids/gems/sockets/enchant id?
GET /profile/wow/character/{realm-slug}/{name}/specializations
GET /profile/wow/character/{realm-slug}/{name}/talents
GET /profile/wow/character/{realm-slug}/{name}/character-media
GET /profile/wow/character/{realm-slug}/{name}/encounters/raids
```
Uwagi:
- profil może być chroniony (protected character) — wymaga user OAuth i 2FA na koncie; 404 gdy realm niedostępny
- `/profile/user/wow` zwraca tylko ostatnio grałe postacie (max 500/account); po raz pierwszy wystarczy
- dane Armory bywają opóźnione → każdy snapshot z timestamp + source

## Game Data API (client credentials, namespace `dynamic-{region}` / `static-{region}`)
```
GET /data/wow/journal-instance/index                     # wszystkie instancje
GET /data/wow/journal-instance/{id}                      # encounters + itemy w loot table (media, description)
GET /data/wow/journal-encounter/{id}                     # boss details + items (bonusLists per item!)
GET /data/wow/journal-expansion/index                    # expansiony → filtr tierów
GET /data/wow/item/{item_id}                             # static namespace
GET /data/wow/item/{item_id}/media
GET /data/wow/item-class/index … /item-class/{id}/item-subclass/{sid}/items
GET /data/wow/mythic-keystone/dungeon/index              # dungeony M+ (static?) — dynamic
GET /data/wow/mythic-keystone/season/index               # seasons; current = season z najnowszym start
GET /data/wow/mythic-keystone/season/{id}                # periods, dungeons
GET /data/wow/mythic-keystone/period/{id}                # aktualny period
GET /data/wow/playable-class/index, /playable-specialization/{id}
GET /data/wow/realm/index, /connected-realm/index
```
Loot tables: Journal Encounter daje `items[].bonus_lists` i `item.level.per_activity_type` / media — ale **brak pełnych wariantów bonus IDs/upgrade tracków** → uzupełniamy z danych klienta (SimC item database / dbc data w repo simc: `engine/dbc`, `engine/items.json` generowane z klienta gry). Preferencja: lokalny cache (PG, TTL), zero requestów w czasie symulacji.

## Mythic+ (rating/season info)
Character `statistics`/`mythic-keystone-profile` nie jest niezbędny do raportu — season/dungeony bierzemy z Game Data.

## Błędy / limity
- 36 000 req/h per client (soft); trzymamy cache i ETag/Last-Modified gdy możliwe
- 401 → token wygasł → refresh; 404 → brak danych (np. char z innej subregion); 429 → backoff
