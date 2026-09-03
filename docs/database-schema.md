# Database schema (PostgreSQL 16, migracje: Alembic)

```sql
users             (id PK, bnet_id UNIQUE, battletag, created_at, last_login)
blizzard_accounts (id PK, user_id FK, region, wow_accounts jsonb, tokens_encrypted bytea, token_expires_at)
characters        (id PK, blizzard_account_id FK, region, realm_slug, name, class_id, class_name,
                   active_spec_id, active_spec_name, level, race_id, selected bool, media_url,
                   UNIQUE(region, realm_slug, name))
character_snapshots(id PK, character_id FK, source enum('blizzard_armory','simc_addon_import'),
                   timestamp, raw jsonb,           # pełny payload equipment+talents+summary
                   simc_text text,                 # gdy source=simc_addon_import
                   item_level numeric, is_current bool)
items             (id PK, item_id int, name, slot, item_class, item_subclass,
                   quality, unique_equipped bool, required_level,
                   identity jsonb)                # bonus_ids, sockets, embellishment itd. (canonical form)
content_sources   (id PK, type enum('raid','dungeon'), journal_instance_id, name, slug,
                   is_current bool, detected_at, wow_build)
content_encounters(id PK, content_source_id FK, journal_encounter_id, name, order)
content_items     (id PK, encounter_id NULL, dungeon_id NULL, item_id FK,
                   difficulty enum('lfr','normal','heroic','mythic'), item_level int,
                   upgrade_track text, bonus_ids int[], source_metadata jsonb)
simulation_runs   (id PK uuid, character_id FK, snapshot_id FK,
                   simc_version, simc_commit, wow_build, content_version,
                   simulation_config jsonb,       # iterations, target_error, fight_style, duration...
                   profile text,                  # wygenerowany input simc
                   status enum('pending','running','completed','failed'), error text,
                   created_at, started_at, finished_at)
simulation_results(id PK, simulation_run_id FK, profileset_name,  -- NULL = baseline
                   profile_type enum('raid','mplus'),
                   mean numeric, median numeric, min numeric, max numeric, stddev numeric,
                   iterations int, confidence_interval jsonb, raw json2_output jsonb)
reports           (id PK uuid, character_id FK, simulation_run_raid FK, simulation_run_mplus FK,
                   report_date date, generated_at,
                   baseline_dps_raid, baseline_dps_mplus,
                   best_raid_upgrade_item_id, best_mplus_upgrade_item_id,
                   snapshot_age_warning text,
                   html_path, status enum('generating','completed','failed'))
api_cache         (key text PK, payload jsonb, fetched_at, ttl_seconds)   -- realm/content/item cache
```
Indeksy: reports(character_id, report_date desc), simulation_results(simulation_run_id),
content_items(item_id, difficulty), api_cache(fetched_at) do czyszczenia.
