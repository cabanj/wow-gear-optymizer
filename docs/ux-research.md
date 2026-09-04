# UX Research — wygląd strony (2026-09-03)

Źródła: Raidbots (Droptimizer/TopGear), Bloodmallet, Wowhead. Cel: strona ma wyglądać
jak narzędzie gracza, nie jak tabela z lat 90. Stack bez zmian: SSR Jinja + vanilla JS.

## Co robi konkurencja (wspólne wzorce)

1. **Droptimizer (Raidbots)** — wynik grupowany po bossie/dungeonie, nie płaska lista:
   Best Drop, Expected Value, Priority. Pełna lista itemów poniżej, domyślnie tylko
   najlepsza wersja itemu + toggle "Show All Variations". Lekcja: nasz ranking ma mieć
   grupowanie po źródle (boss/dungeon) i zwijanie wariantów.
2. **Bloodmallet** — poziome wykresy słupkowe DPS per item (słupek = zysk), baseline
   jako linia odniesienia. Ikony itemów + linki do Wowhead z bonusami w URL.
   Lekcja: ranking jako słupki, nie sama tabela; kolory jakości itemów.
3. **Wowhead** — kolory jakości (epic fiolet, rare niebieski, legendary pomarańcz),
   tooltipy po najechaniu, ikony 56px. Lekcja: bierzemy ich paletę jakości + publiczny
   skrypt tooltipów (dozwolony embed, nie scraping) albo minimum linki `wowhead.com/item=X`.

## Propozycja dla naszych 3 widoków

### 1. Dashboard (`/`) — karty postaci, nie lista
- Karta per postać: avatar (character media), imię + realm, klasa w kolorze klasy,
  spec, ilvl, "Best raid upgrade +X%", "Best M+ upgrade +Y%", wiek snapshotu,
  status ostatniego raportu. Klik → raport.
- Klasa w kolorach WoW (warlock fiolet #9482C9, mage jasnoniebieski itd.).

### 2. Raport (`/reports/{id}`) — najważniejszy widok
- Nagłówek: postać, snapshot time + source, SimC/WoW build, baseline DPS dużą liczbą.
- Zakładki: Raid | Mythic+ | Combined. Filtry slotów jako chipsy (All/Head/.../Trinket).
- Wiersz rankingu: pozycja, ikona + nazwa w kolorze jakości, slot, boss/dungeon,
  ilvl, słupek zysku DPS (szerokość ∝ delta), +DPS i +% liczbowo, znaczek ± gdy w błędzie.
- Rozwijany wiersz: staty itemu, bonus IDs, link Wowhead, "zastępuje: <obecny item>",
  mean/median/stddev/iteracje.
- Grupowanie opcjonalne: po bossie (jak Droptimizer) z Best Drop per boss.
- Disclaimer o błędzie symulacji na dole, nie na górze.

### 3. Postacie (`/characters`) — naprawić puste stany
- Pusty stan ma mówić co zrobić ("Refresh from Blizzard" + "lub dodaj ręcznie realm+nazwa"),
  nie pokazywać gołej listy. Manual add: dwa inputy + przycisk.
- Checkboxy w stylu kart (klikane całe), przycisk Save z potwierdzeniem.

### Historia
- Oś czasu raportów per postać + mini-wykres SVG baseline DPS (bez libki).

## System (żeby nie było 1994)
- Ciemny motyw jak gra: tło #0d0f14, panele #161a23, akcent niebieski #2f5fbe,
  zysk zielony #6fce7d, ostrzeżenie bursztyn #e8b34a. Kolory jakości itemów z Wowhead.
- Font systemowy, liczby tabular-nums, jednostki zwijane spacją (110 000).
- Mobile first: tabela → karty na <700px (słupek + najważniejsze liczby, reszta w rozwinięciu).
- Zero frameworków CSS — jeden plik, ~200 linii. Ikony itemów: Blizzard media API
  (mamy URL-e z character media / item media), fallback inicjał.

## Decyzje dla Jacka
1. Grupowanie rankingu po bossie ( Droptimizer) czy płaska lista? Proponuję: płaska domyślnie + toggle grupowania.
2. Tooltipy Wowhead (zewnętrzny JS) czy własne rozwijane szczegóły? Proponuję: własne szczegóły + link, bez obcego JS (prywatność, szybkość).
3. Wykresy: czysty SVG inline czy libka (chart.js)? Proponuję SVG — jeden wykres baseline, nie warto ciągnąć libki.
