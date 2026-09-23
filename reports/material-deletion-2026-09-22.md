# Weryfikacja: usuwanie pojedynczych materiałów (issue #2) — 2026-09-22

Zakres: GitHub issue `Samuel-Ku/google-ads-assets-generator#2` („Delete individual campaign materials safely”),
wycinek specyfikacji `reports/spec-material-deletion-pmax-text-shapes-2026-09-22.md` (sekcja „Campaign material deletion”).
PMax-with-text i editable shapes to osobne zgłoszenia (#3, #4) i nie były tu wdrażane.

## Co zostało zrobione

- Nowy endpoint `DELETE /api/campaigns/<id>/assets/<asset_id>`: sesja + CSRF, aktualna wersja kampanii,
  plik musi należeć do tej kampanii (Brand Kit ukryty za tym samym 404), blokada plików z potomkami,
  blokada przy aktywnym zadaniu przetwarzania, trwałe usunięcie bajtów, rekonesans całego `state`,
  nowa rewizja z autorem. `store.lock` + ponowna weryfikacja w workerze zamykają wyścig „przetwarzanie vs usuwanie”.
- Refaktor bez zmiany zachowania: wyciągnięty `strip_media` (wspólny dla duplikatu kampanii, usuwania
  i przywracania wersji) oraz `missing_asset_ids`. `validate_state` odrzuca odwołania do plików,
  których już nie ma — późniejszy zapis nie może wskrzesić usuniętego materiału.
- Frontend: akcja „Usuń plik” na karcie materiału (SVG włącznie, Brand Kit wyłączone), ujawniające
  potwierdzenie (plik, kompozycje, trwałość, brak plików pochodnych), rekonesans selekcji i wszystkich
  zapisanych scen, odświeżenie licznika miejsca, polskie komunikaty błędów (409 potomek / 409 zadanie /
  409 konflikt wersji). Rekonesans niedostępnych odwołań także przy otwarciu kampanii, przywróceniu
  wersji i lokalnym undo.

## Testy automatyczne

- `tests/test_material_deletion.py` — 7 nowych testów integracyjnych: uwierzytelnianie/CSRF/rola,
  relacja kampania–plik, wersja wygasła i aktualna, blokada potomków + zachowanie rodzeństwa,
  koordynacja z zadaniem przetwarzania i bezpieczny retry, rekonesans stanu + rewizja + zwolnienie
  miejsca, niedostępny plik w zapisie/przywróceniu/`remove-background`.
- `tests/frontend-materials.cjs` — rozszerzony o scenariusz #2: akcja na karcie (i jej brak dla Brand Kit),
  ujawniające potwierdzenie z anulowaniem bez zmian, rekonesans selekcji/scen po usunięciu,
  czyszczenie martwych odwołań przy otwarciu kampanii.
- Pełny zestaw: **144 passed** (`pytest -q`), `node --check` app.js/canvas.js, wszystkie skrypty Node
  (`format-sync`, `frontend-materials`, `template-recipes`, `upload-handler`) przechodzą.

## Izolowana podróż przeglądarkowa (Chrome, 127.0.0.1:8765, osobny katalog danych /tmp)

Serwer uruchomiony lokalnie z `ADS_DATA_DIR=/tmp/studio-journey-data`; osobne konto testowe, marka i
kampania utworzone wyłącznie na potrzeby podróży; wgrane dwa zdjęcia przez prawdziwy formularz UI.

1. **Anuluj** — potwierdzenie pokazało plik (nazwa, typ, wymiary, rozmiar) i informację o trwałości;
   „Anuluj” zamknęło okno, plik i kompozycje bez zmian (toast: „Anulowano…”).
2. **Usuń** — drugie uruchomienie potwierdzenia i „Usuń plik”: karta zniknęła, toast potwierdza,
   bajty pliku usunięte z dysku (`media/`), w bazie nowa wersja z autorem, drugi plik nietknięty.
3. **Otwórz ponownie** — kampania otwarta od nowa: jedna karta, wersja zgodna, brak błędów w konsoli.
4. **Eksport** — zapis kompozycji z pozostałym zdjęciem i pełny eksport ZIP (8 plików JPG + CSV)
   przeszedł; usunięte zdjęcie nie pojawiło się w żadnym renderowanym pliku.
5. **Brak materiału** — usunięcie drugiego (ostatniego) zdjęcia: potwierdzenie wskazało kompozycje,
   w których materiał stanie się brakujący; zakładka Eksport pokazała komunikat „Uzupełnij przed
   eksportem: Wybierz zdjęcie produktu lub tło dla obrazów elastycznych”, a eksport został zablokowany.
6. **Przywrócenie historii** — restore w wersji 3 (zapisanej jeszcze z oboma zdjęciami) utworzył nową
   rewizję; w stanie nie ma żadnego działającego odwołania do usuniętych plików (weryfikacja w bazie:
   0 referencji, 0 wierszy assets), warstwy zachowały sloty i geometrię, pliki nie wróciły.
7. **Meter miejsca** — po usunięciu licznik w panelu bocznym pokazał mniejsze zużycie (`refreshStorage`).

Po podróży: fixture zdjęcia usunięte z `static/`, dane testowe w `/tmp`, konta testowe tylko w izolowanym katalogu.

## Zgodność z runbookiem (docs/operations/deployment-runbook-uk.md)

- Sekcja „Плановий deploy → 1. Перевірити локальний стан”: wszystkie wymienione komendy wykonane, wyniki powyżej.
- Zmiana **nie wymaga migracji SQLite** (brak zmian schematu), więc backup-before-migration nie był potrzebny;
  mimo to zalecany przed wdrożeniem zgodnie z ogólną zasadą runbooka.
- Wdrożenie `--apply` na VM wykonuje upoważniony operator; rollout wymaga tylko podmiany kodu i restartu usługi.
