# Weryfikacja: usuwanie materiału wraz z plikami pochodnymi (issue #3)

Data: 2026-09-22 · Zakres: confirmed cascade deletion of derived campaign files (slice #3 of `reports/spec-material-deletion-pmax-text-shapes-2026-09-22.md`, ticket draft `02-delete-material-descendants`).

## Co zostało zbudowane

**Backend (`app.py`)**
- `DELETE /api/campaigns/<id>/assets/<asset_id>` rozszerzone o potwierdzaną kaskadę:
  - `campaign_descendant_ids` przechodzi po wszystkich pokoleniach pochodnych (BFS po `parent_id`, tylko żywe wiersze — wygasłe kończą gałąź);
  - pojedynczy plik (bez potomków) działa jak w slice #2 — bez dodatkowego potwierdzenia;
  - kaskada wymaga `confirmed_asset_ids` dokładnie równego zestawowi (root + potomkowie + żywe wyjścia zakończonych zadań); brak/niezgodność → 409 `descendants` / 409 `impact_changed` z `required_asset_ids`;
  - aktywne zadanie na dowolnym pliku z zestawu blokuje całość (409 `job_active`); `store.lock` + re-weryfikacja w workerze zamykają wyścig „przetwarzanie odtwarza usunięte wyjście";
  - usunięcie bajtów, wierszy i jobów całego poddrzewa + pojedyncza autorska rewizja (strip_media na całym stanie, wersja +1, autor).
- **Naprawiony błąd (odkryty testami #3):** `missing_asset_ids` nie wchodził w zagnieżdżone słowniki — `elif` bez gałęzi `dict/list`. Przywracanie wersji historycznej odtwarzało referencje do plików usuniętych kaskadowo (id żyjące tylko w warstwach sceny). Poprawiony deep-walk; twardo pokryty testem `test_reopen_export_restore_after_cascade`.

**Frontend (`static/app.js`)**
- `deletionImpact` — BFS po `parent_id` w materiach kampanii: pełna lista nazw i id potomków oraz kompozycji, które faktycznie używają któregokolwiek pliku (scena bazowa, `scenes`, `template_scenes`), z zachowaniem wcześniejszego fallbacku na wybory;
- dialog potwierdzenia: tytuł „(razem z plikami pochodnymi)" i sekcja „Zostaną również trwale usunięte pliki pochodne" z listą nazw;
- `deleteMaterial` wysyła `confirmed_asset_ids` (tylko gdy zestaw > 1) i obsługuje pętlę odświeżenia: 409 `impact_changed`/`descendants` → toast + ponowne potwierdzenie z dokładnym zakresem z serwera (brak trybu, pliki niewidoczne dla klienta są ujawniane z nazwy/id);
- toasty sukcesu odróżniają kaskadę od pojedynczego pliku; anulowanie nie zmienia niczego.

## Weryfikacja lokalna (zgodnie z runbookiem wdrożeniowym)

- **Backend:** 151 testów pytest przeszło (137 istniejących + 14 w `tests/test_material_deletion.py`, w tym 6 nowych dla #3: wszystkie pokolenia, poddrzewo cięcia z zachowaniem rodzica/rodzeństwa, blokada bez potwierdzenia, `impact_changed` z odświeżonym potwierdzeniem, blokada `job_active` na potomku, reopen/export/restore po kaskadzie).
- **Frontend:** `node --check` dla `static/app.js` i `static/canvas.js`; wszystkie 5 suit Node przechodzi, w tym rozszerzony `frontend-materials.cjs` (nazwy potomków w dialogu, `confirmed_asset_ids` w żądaniu, pętla refreshed-confirmation z zakresem z serwera).
- **Izolowana podróż przeglądarkowa** (Chrome → `127.0.0.1:8765`, osobny katalog danych w `/tmp`, konto i kampania testowe):
  1. Utworzono Brand Kit, kampanię „Kaskada test", wgrano 2 zdjęcia, zapisano;
  2. „Usuń tło" dla photo-a → wycięcie; z wycięcia → wycięcie zagnieżdżone (3 pokolenia);
  3. Dialog dla photo-a ujawnił 2 potomki (widok klienta sprzed zadania); serwer odrzucił (409 `impact_changed`) i po ponownym otwarciu dialog wymieniał wszystkie 3 pliki — potwierdzenie odświeżone, kaskada usunęła całe poddrzewo;
  4. Bajty plików zniknęły z dysku, licznik miejsca zaktualizowany, autorska rewizja (v3) zapisana;
  5. photo-b w zapisanej kompozycji: dialog wskazał „Kompozycja bazowa" i „Podział" jako kompozycje z brakiem materiału; po usunięciu eksport zablokowany („Uzupełnij wskazane dane przed eksportem"), 0 żywych referencji w SQLite;
  6. Przywrócenie wersji v2 (sprzed usunięć) nie odtworzyło żadnego pliku (0 żywych referencji, „Usunięte pliki nie wracają").
- Zmiana nie wymaga migracji SQLite; zgodna z `docs/operations/deployment-runbook-uk.md` (sekcja weryfikacji lokalnej; samo `--apply` pozostaje po stronie operatora).

## Ograniczenia / notatki

- Eksport w testach API działa na plikach renderowanych po stronie klienta (ZIP budowany z manifestu), więc test backendowy weryfikuje akceptację paczki z materiałów, które przetrwały — blokadę brakującego materiału potwierdza podróż przeglądarkowa (krok 5).
- Workspace nie jest repozytorium git (znane z CONTRACT.md), więc nie ma commita; wszystkie zmiany w plikach roboczych.
