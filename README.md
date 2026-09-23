# Google Ads Assets Studio

Wewnętrzny edytor materiałów Google Ads: Flask + SQLite, Canvas w przeglądarce, lokalne usuwanie tła U²-NetP na CPU. Interfejs po polsku. Bez płatnych API i automatycznego importu z Bitrix24 / Google Sheets.

## Структура папок
Створи таку структуру на своєму сервері:

```
banner-tool/
├── app.py
├── banner_pipeline.py
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js       (файл названо app_script.js — перейменуй на app.js)
└── jobs/            (створюється автоматично)
```

Файли, які згенеровано в цій сесії, розклади так:
- `app.py` → в корінь
- `banner_pipeline.py` (з попереднього кроку) → в корінь
- `index.html` → у папку `templates/`
- `style.css` → у папку `static/`
- `app_script.js` → у папку `static/`, **перейменувавши на `app.js`**

## Встановлення (один раз)

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask playwright pillow jinja2 pyyaml
playwright install chromium
```

## Запуск

```bash
python app.py
```

Відкрий у браузері `http://localhost:5000` (або `http://<IP_сервера>:5000`, якщо хостиш на віддаленій машині — не забудь відкрити порт 5000 у файрволі).

## Як користується нетехнічна людина

1. Опційно завантажує лого (одне для всіх банерів).
2. Для кожного банера: перетягує фото, вписує заголовок, опис і текст кнопки, вибирає колір бренду.
3. Натискає "+ Додати ще один банер", якщо потрібно кілька варіацій.
4. Натискає "Створити всі банери" — бачить прев'ю прямо в браузері.
5. Натискає "Завантажити ZIP" і надсилає файл спеціалісту Google Ads.

Кожен ZIP містить усі 12 стандартних розмірів (300×250, 728×90, 1200×628 тощо) для кожної варіації плюс `manifest.csv` з описом, що куди заливати.

## Продакшн-нотатки

Вбудований Flask-сервер (`app.run`) підходить для локального/домашнього використання. Для постійного хостингу на сервері запусти через `gunicorn` або `waitress` і постав позаду nginx/Caddy з HTTPS, якщо доступ буде ззовні мережі.


## Praca zespołu

1. Administrator tworzy konta oraz Brand Kit: kolory, logo, font i wskazówki językowe.
2. Redaktor tworzy kampanię, wybiera markę, wkleja brief oraz własne teksty i dodaje zdjęcia.
3. Dodaje kilka produktów oraz niezależne „Elementy”, np. etykiety. Opcjonalnie usuwa tło metodą Smart lub AI, reguluje odzyskiwanie detali i miękkość krawędzi, poprawia maskę pędzlem lub usuwa pozostałość tła jednym kliknięciem („Usuń obszar”) i zapisuje PNG.
4. Wybiera jeden z dziewięciu gotowych układów albo szablon zespołu, przesuwa i skaluje warstwy, poprawia teksty, kadrowanie i wygląd CTA. Zmiany domyślnie aktualizują pozostałe formaty tej kompozycji; przełącznik pozwala edytować rozmiar osobno.
5. Wybiera formaty i warianty, także przyciskami zaznacz/odznacz wszystkie. Gotowe banery Display zawierają tekst i CTA; obrazy do RDA/PMax oraz logo są osobnymi materiałami.
6. Potwierdza warunki oferty, sprawdza ostrzeżenia i pobiera ZIP z obrazami oraz CSV tekstów i manifestu. Nazwy obrazów to wymiary, np. `300x250.jpg`; warianty znajdują się w osobnych folderach.

Kampanie są wspólne dla wszystkich redaktorów. Historia zapisuje autora i wersję. Konflikt równoczesnej edycji wymaga ponownego wczytania aktualnej wersji — zapis nie nadpisuje po cichu pracy drugiej osoby.

## Biblioteka szablonów

W zakładce **Kompozycja** dostępne są: Podział, Produkt w centrum, Typografia, Katalog produktów, Produkt + korzyści, Oferta z etykietą, Zdjęcie w tle, Zestaw z akcesoriami i Mocny kolor. Dla zestawu pierwsze zaznaczone zdjęcie jest produktem głównym. Oferta z etykietą wymaga Elementu, a Zdjęcie w tle własnego tła.

**Zapisz jako szablon** zachowuje układ, style i osobne dopasowania formatów. Zapis trafia do wspólnej zakładki **Zapisane przez zespół**. Użycie w innej kampanii podstawia jej teksty, zaznaczone zdjęcia/Elementy oraz Brand Kit. Brakujące materiały widać w edytorze; należy je uzupełnić lub usunąć niepotrzebną warstwę przed eksportem. Podgląd po podmianie zdjęć i długości tekstów wymaga sprawdzenia.

Szablony nie przechowują dawnych zdjęć ani treści promocji i pozostają dostępne po wygaśnięciu materiałów kampanii. Autor lub administrator może je archiwizować i przywracać. Archiwizacja nie zmienia wcześniej zastosowanych kompozycji. Limit biblioteki to 100 zapisów, łącznie z archiwum. Zapis jest kopią — zmiana kampanii nie nadpisuje szablonu.

## Ograniczenia pilota

- SVG dla logo, produktów, teł i Elementów: maks. 2 MB. Zachowujemy wektory, gradienty, ścieżki, maski i przezroczystość; eksport banerów pozostaje JPG/PNG. Obsługujemy statyczne SVG bez skryptów, animacji i zewnętrznych plików. Dla dokładnego wyglądu niestandardowych fontów zamień tekst w pliku na krzywe. Tło SVG popraw w pliku źródłowym; usuwanie tła działa na JPG/PNG/WebP.
- Zdjęcia PNG/JPEG/WebP: maks. 12 MB i 60 megapikseli na wejściu. Obrazy powyżej 20 MP są automatycznie zmniejszane do maks. 20 MP, z zachowaniem proporcji, orientacji i przezroczystości; mniejsze zachowują swoje wymiary. Pełne pliki źródłowe pozostają u użytkownika. Logo i fonty są przechowywane z Brand Kit.
- Media kampanii i ZIP są usuwane po 7 dniach, zgodnie z datą widoczną w aplikacji. Brand Kit, treść i historia pozostają.
- Kwota plików na VM: 1 GiB; rezerwa wolnego dysku: 1 GiB. Nowe operacje są blokowane przy braku miejsca. Pliki innych usług nie są czyszczone.
- Jedno zadanie usuwania tła naraz; przeglądarka renderuje komplet reklam.
- U²-NetP wymaga kontroli cienkich krawędzi, przewodów i białych produktów. Pędzel i „Usuń obszar” poprawiają maskę bez zmiany RGB. Wybierz „Popraw maskę” → „Usuń obszar” i kliknij pozostałość tła. Tolerancja koloru (domyślnie 8%) dotyczy następnego kliknięcia; po zmianie tolerancji cofnij poprzedni wynik i kliknij ponownie. Usuwana jest tylko połączona część podobnego koloru. Zapisz PNG, a następnie zmiany kampanii.
- Eksport CSV jest czytelną tabelą materiałów, nie deklarowanym formatem automatycznego importu Google Ads Editor.
- Kontrole techniczne nie gwarantują akceptacji reklamy ani wyników kampanii. Propozycję, ceny, daty i wygląd produktu potwierdza człowiek.

## Uruchomienie lokalne

Python 3.12 lub nowszy. Model `models/u2netp.onnx` jest już dołączony; aplikacja weryfikuje jego SHA256. Źródło i licencja: [third_party/README.md](third_party/README.md).

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Najpierw utwórz konto administratora przez prywatny plik hasła,
# zgodnie z poleceniem CLI: .venv/bin/python app.py create-admin --help
.venv/bin/python scripts/serve.py
```

Adres lokalny: `http://127.0.0.1:8765`. Dane pozostają na dysku serwera. Nie uruchamiaj wielu procesów serwera — kolejka i blokady zapisu działają w jednym procesie.

## Weryfikacja

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
node --check static/app.js
node --check static/canvas.js
node tests/format-sync.cjs
node tests/frontend-materials.cjs
node tests/upload-handler.cjs
node tests/template-recipes.cjs
```

Przeglądarka jest weryfikowana oddzielnie: tworzenie kampanii, upload, maska, edycja, warianty, ZIP, odtworzenie zapisu, widoki desktop/mobile. Raport rzeczywiście wykonanych testów będzie w `reports/verification.md`.

[Zatwierdzony zakres](SPEC.md) · [Kontrakt modułów](CONTRACT.md) · [Rozmieszczenie i odzyskiwanie](DEPLOY.md) · [Операційний runbook українською](docs/operations/deployment-runbook-uk.md)

Pliki w `legacy/` to kopia poprzedniego prototypu. Nie są częścią wdrożonego serwisu.
