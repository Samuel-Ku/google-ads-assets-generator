# Biblioteka szablonów — weryfikacja 2026-09-21

## Zakres

Dziewięć gotowych układów, zapis wspólnych szablonów z geometrią i stylami, dopasowania formatów, podstawianie bieżących materiałów/tekstów/Brand Kit, archiwum autora/administratora.

## Wykonane sprawdzenia

- Backend: 137 testów pytest zakończonych powodzeniem, w tym 47 testów biblioteki (uwierzytelnianie, CSRF, uprawnienia, archiwizacja, limity, walidacja receptur, niezależność od usunięcia/wygaśnięcia kampanii źródłowej).
- Node: format-sync, frontend-materials, upload-handler, template-recipes — wszystkie przechodzą. Receptura z rzeczywistego modułu JS przechodzi walidator Python.
- Przeglądarkowy canvas-harness: 26 sprawdzeń, dziewięć układów w różnych proporcjach, warstwy i teksty, brakujące materiały, czyste RDA/PMax, SVG, eksport, maska i Cofnij. Osobna regresja zachowania brakującego logo podczas zmiany proporcji.
- Lokalna aplikacja, wyłącznie izolowane dane testowe: zapis szablonu Zestaw z akcesoriami z CTA zaokrąglonym do40%; użycie w innej kampanii z nową marką i dwoma produktami zamiast trzech; poprawne placeholdery produktu/logo, aktualne zdjęcia, nagłówek, CTA, font i kolory.
- Usunięcie niepotrzebnych brakujących warstw, eksport rzeczywistego ZIP. Sprawdzono JPG300×250, nazwę300x250.jpg w folderze szablonu, nowe teksty CSV, identyfikatory plików tylko z nowej kampanii, brak źródłowych URL-i i tekstów w zapisanej recepturze.
- Zapis/ponowne otwarcie przez drugiego redaktora; dostęp do szablonu i zastosowanej kompozycji, brak przycisku archiwizacji cudzego szablonu. Archiwizacja/przywrócenie przez autora zachowuje kompozycję kampanii.
- Dodatkowe Elementy w nowych układach domyślnie omijają tekst/logo; sprawdzono generowanie i zmianę proporcji z trzema produktami i dwoma Elementami.
- Podgląd desktop, brak błędów konsoli w testowanej ścieżce. Podglądy biblioteki tworzone na żądanie; domyślny wybór eksportu zachowany.

## Wdrożenie

Przed migracją wykonano spójną kopię SQLite na VM: `data/pre-template-library-20260921.sqlite3` (192512B, mode600, integrity_check=ok). Nowa tabela jest niezależna od dotychczasowych danych; powrót do wcześniejszego kodu nie wymaga kasowania bazy.

Opublikowano release `20260921-150038` pod `http://192.168.15.42:8765/`. Kontrola produkcyjna: logowanie i uwierzytelnione API biblioteki, zapis/odczyt/archiwizacja/przywrócenie tymczasowego szablonu, identyczność SHA256 plików JS/CSS z testowaną wersją i poprawne ładowanie aplikacji w przeglądarce. Tymczasowy szablon został usunięty, istniejąca biblioteka zachowana. Wcześniej istniejące kampanie i konta nie były edytowane.

## Ograniczenia

Szablon zachowuje układ, ale długość nowych tekstów i proporcje zdjęć nadal wymagają kontroli podglądu. Kontrole techniczne nie przewidują skuteczności reklamy. Zdjęcia kampanii zachowują dotychczasowy termin7dni; same szablony pozostają w bibliotece.
