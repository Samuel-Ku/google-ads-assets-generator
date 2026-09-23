# Biblioteka szablonów — projekt do zatwierdzenia

## Uzgodniony cel

Gotowe kompozycje oraz wspólne szablony zapisane przez zespół, możliwe do użycia w następnych kampaniach. Szablon zachowuje układ i style; materiały, logo i teksty pochodzą z nowej kampanii.

## Gotowe schematy

Do obecnych trzech układów dodajemy sześć nowych (razem dziewięć):

| Nazwa | Kompozycja | Zastosowanie |
| --- | --- | --- |
| Katalog produktów | Nagłówek nad uporządkowanymi zdjęciami; wspólne CTA poniżej | Kilka równorzędnych produktów |
| Produkt + korzyści | Duże zdjęcie oraz wyraźnie oddzielony blok nagłówka i opisu | Oferta oparta na zaletach produktu |
| Oferta z etykietą | Produkt, krótka oferta i wyznaczone miejsce na wgrany Element | Promocja z własnym labelem |
| Zdjęcie w tle | Zdjęcie wypełnia baner, tekst znajduje się na czytelnym panelu | Kampania z własnym tłem |
| Zestaw z akcesoriami | Główny produkt większy, pozostałe zdjęcia jako dodatki | Laptop/PC plus akcesoria |
| Mocny kolor | Duża płaszczyzna koloru marki i kontrastowe pole produktu | Wyrazista, krótka oferta |

Każdy schemat ma osobny układ dla formatu poziomego, pionowego, zbliżonego do kwadratu i wąskiego paska. Materiały nie są rozciągane. W małych formatach opis może być pominięty zgodnie z dotychczasowymi regułami. Wszystkie warstwy pozostają edytowalne. Obrazy RDA/PMax zachowują dotychczasowy tryb bez nakładek tekstowych.

## Biblioteka i zapis własnych szablonów

W zakładce Kompozycja wybieramy „Gotowe” albo „Zapisane przez zespół”. Podglądy wykorzystują aktualne materiały kampanii. Obecny układ pozostaje wybrany, dopóki użytkownik nie wskaże innego.

Przycisk „Zapisz jako szablon” otwiera krótkie okno z nazwą. Zapisywana jest kopia bieżącej kompozycji bazowej i jej indywidualnych dopasowań formatów. Zapis nowego szablonu nie zmienia już używanych szablonów ani wcześniejszych kampanii. Każdy redaktor może zapisywać i stosować szablony; wspólna biblioteka pokazuje autora. Niepotrzebny zapis może zarchiwizować autor lub administrator, z możliwością przywrócenia.

Przy zastosowaniu szablonu generator przypisuje wybrane produkty i Elementy do miejsc według kolejności. Logo, font i kolory marki pochodzą z Brand Kit nowej kampanii; ręcznie ustawione style pozostałych elementów są zachowane. Teksty pochodzą z bieżących pól kampanii. Brakujące materiały są wyraźnie oznaczone do uzupełnienia; stare zdjęcia ani treści nie są automatycznie przywracane.

## Trwałość i zgodność

Zapis przechowuje geometrię, kolejność i style warstw oraz miejsca na materiały, bez kopii zdjęć, ich adresów ani tekstów promocji. Dzięki temu pozostaje użyteczny po siedmiodniowym terminie przechowywania plików. Nie jest potrzebne płatne API.

Identyfikator zapisanego szablonu jest oddzielony od schematu odpowiedzialnego za dopasowanie do proporcji. Dotychczasowe kampanie zachowują układy. Generowanie podglądów i zapisów odbywa się na żądanie; nie tworzymy z góry wszystkich kombinacji szablonów i formatów. Limit eksportu pozostaje widoczny.

## Sprawdzenie przed wdrożeniem

- Różne proporcje, małe banery i kilka produktów w nowych układach.
- Zapis oraz użycie przez drugiego redaktora w innej kampanii.
- Podmiana Brand Kit, tekstów i materiałów bez przenoszenia danych starej kampanii.
- Użycie szablonu po wygaśnięciu lub usunięciu plików kampanii źródłowej.
- Edycja warstw, synchronizacja formatów, Cofnij i eksport JPG/PNG.
- Zgodność istniejących kampanii i kontrola uprawnień biblioteki.

## Stan prac

- [x] Zbadano obecne szablony i zapis kampanii.
- [x] Uzgodniono gotową bibliotekę oraz wspólne szablony użytkowników.
- [x] Uzgodniono przechowywanie układu i stylów bez dawnych materiałów/tekstów.
- [x] Porównano rozszerzenie gotowych układów, zapis własnych oraz oba rozwiązania; użytkownik wybrał oba.
- [x] Przygotowano projekt działania i testów.
- [x] Zatwierdzono projekt przed implementacją — użytkownik zatwierdził wdrożenie i publikację na VM.
- [x] Wdrożono i sprawdzono lokalnie.
- [x] Opublikowano na VM i zweryfikowano — release `20260921-150038`.
