# Simulation design

## Silnik
- SimulationCraft CLI, obraz dockerowy `simulationcraftorg/simc:<pinned-tag>` (official nightly builds na Docker Hub; build z repo `simulationcraft/simc`, branch `midnight`, ma własny Dockerfile). Pinujemy tag wersji w `.env` (SIMC_IMAGE_TAG) i zapisujemy w każdym raporcie.
- SimC sam importuje char z Armory: `armory=eu,{realm},{name}` lub — preferowane — z naszego snapshotu przez `local_json` (wiki ProfileSets: armory w profilesets spowalnia inicjalizację). Baseline budujemy z zapisanego JSON-a Armory → stabilne, odtwarzalne.
- Ręczny import `/simc` (addon) → parsujemy tekst na profil .simc → snapshot `source=simc_addon_import` → używany jako baseline zamiast Armory.

## Profilesets (jeden proces na many items)
```
# baseline (z local_json / simc_text)
profileset."BASELINE"=            # implicitnie baseline

profileset."item_185842_heroic"=tier29_shoulder=1,id=200426,bonus_id=6652/10353/10890,...
profileset."item_185843_mythic"=...
...

threads=N
profileset_work_threads=2          # parallel profilesets (simc >= 735-01)
target_error=0.002
iterations=<RAID_SIM_ITERATIONS>
fight_style=Patchwerk
duration=300
json2=report_raid.json
```
- Raid profile: Patchwerk, 1 target, 300s (konfigurowalne).
- M+ profile: `fight_style=DungeonSlice` (configurowalne duration/targets).
- `profileset_metric=dps`.

## Wykrywanie wersji
`simc --version` (lub pierwszy output runu) → parsujemy: wersja simc, build, commit → zapis w simulation_runs + raport.

## Parsowanie
- Output: **json2** (opcja `json=` jest DEPRECATED — nie używać). json2 zawiera: simulate_options, player stats, per-profileset results z mean/median/stdev/error/iterations.
- Parser: `simc/parser.py` → structured results → simulation_results.

## Special cases (moduł `simc/profile_builder.py`)
- Trinkets: postać ma 2 trinkety → candidate symulowany dwukrotnie, **zastępując każdy z osobna** (2 profilesety na trinket).
- Weapons: 2H zastępuje MH+OH; dual wield MH+OH osobno; off-hand candidate dla 2H usera → pomijamy z markerem "incompatible".
- Rings: max 2, unique-equipped per ring id — nie symulujemy duplikatu tego samego ringu który już nosi.
- Tier sets: candidate generuje osobne profilesety "swap item" + osobny wariant "swap item + zmiana setu" jeśli zmienia liczbę elementów tieru (próg 2/4pc) — liczymy actual set bonus z equipment postaci.
- Sockets/gems/enchants/crafted/embellishments: candidate dostaje **identyczne enchants/gems/sockets/embellishments jak zastępowany item** (decyzja: realistyczny 1:1 swap).

## Decyzje produktowe (zatwierdzone przez Jaceka, 2026-09-03)
1. Trinkety: candidate symulowany vs **każdy z dwóch** założonych trinketów osobno.
2. Mythic+ warianty: **tylko Great Vault track + Bonus roll** (bez base M+ dungeon-drop tracka). Założenie upraszczające: **wszystkie przedmioty są Myth track i mają swój maksymalny ilvl**.
3. Enchants/gems kandydatów: identyczne z zastępowanymi przedmiotami.
- Unique-equipped: jeśli candidate i worn item to ten sam unique item → skip.
- Slot occupancy: candidate tylko na sloty gdzie obecny item ma niższy ilvl LUB candidate z wyższego tracka — ale zawsze symulujemy też "equal ilvl, better stats" dla trinketów/ringów (config `simulate_same_ilvl`).


## Upgrade rules (upgrade_rules.py — jedyny punkt konfiguracji)
- Źródło tracków: dane klienta (SimC item data: `item_enchantment`, bonus id → track mapping z engine/dbc) + Journal `item.level.per_activity_type`.
- Raid: per difficulty LFR/N/H/M — właściwy ilvl z Journal.
- M+: ilvl z aktualnego sezonu (dungeon default + Great Vault warianty; simujemy vault-track jako osobny profileset, konfigurowalne `mplus_variants`).
- Całość deklaratywna (data-driven), zmiana patcha = aktualizacja cache + reload, zero zmian kodu.

## Koszt / czas
- Szacunek: ~30-60 kandydatów × 2 profile types; na 8 wątkach VPS: raid sim ~10-20 min, m+ podobnie. Limity: MAX_CANDIDATES_PER_SLOT (default 3 najlepsze per slot po prescreen ilvl), loop protection: timeout per run (config).

## Confidence
- Zapisujemy mean, median, min, max, stddev, iterations, target_error z json2.
- W UI: „Results are simulation estimates. Small differences may be within simulation error."
- Delta < 2×σ → flaga "within error margin".
