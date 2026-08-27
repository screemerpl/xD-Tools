"""Polska wersja instrukcji obsługi. Słownictwo bloków opisuje
build_manual.py ("p", "ul", "ol", "table", "fig", "note", "warn", "tip",
"h2").

Znaczniki w tekście: **pogrubienie**, `dosłownie`.

Nazwy poleceń muszą być dokładnie takie, jak w polskim interfejsie --
zrzuty ekranu w tej wersji też są polskie, więc rozjazd byłby widoczny od
razu. Źródłem prawdy jest src/mdtools/i18n/mdtools_pl.ts.
"""

TITLE = "xD-Tools"
SUBTITLE = "Studio Retro Nośników — instrukcja obsługi"
TITLE_NOTE = "Projektowanie etykiet, nagrywanie MiniDisców i kaset, wypalanie CD-R i nadawanie tytułów"
COVER_CAPTION = "Co z czym rozmawia: komendy przez USB, klawisze przez podczerwień, dźwięk przez S/PDIF."
VERSION_LINE = "Wersja 0.3.3"
AUTHOR_LINE = 'Artur "Screemer" Jakubowicz'
DATE_LINE = "Sierpień 2026"
TOC_TITLE = "Spis treści"
FOOTER_LEFT = "xD-Tools — Studio Retro Nośników — instrukcja obsługi"

BOOK = [
    # ------------------------------------------------------------------
    {
        "title": "Czym to jest",
        "blocks": [
            {"p": "xD-Tools to komputerowy warsztat do pracy ze starymi nośnikami muzyki: MiniDiskiem, "
                  "CD-R i kasetą magnetofonową. (X zastępuje M albo C — zaczęło się jako żart, a wyszło "
                  "z tego całkiem trafny opis). Zaczęło się od projektowania etykiet, a wyrosło z tego "
                  "kilka narzędzi współdzielących jeden plik projektu:"},
            {"ul": [
                "**Projektowanie** etykiet: naklejki na MiniDisc i wkładki J-card albo pierścienia na "
                "płytę CD i wkładki do pudełka slim — wraz z eksportem gotowym do druku i cięcia.",
                "**Nagrywanie** całego albumu na MiniDisc — z płyty CD albo z folderu plików — ze "
                "znacznikiem przy każdym utworze.",
                "**Wypalanie** płyty audio CD-R z folderu plików, razem z tytułami w CD-Text.",
                "**Nadawanie tytułów** MiniDiscowi: zapisanie nazwy albumu i wszystkich utworów na samej "
                "płycie, tak żeby pokazywał je wyświetlacz magnetofonu.",
                "**Sterowanie magnetofonem** z programowego pilota — transport, numery ścieżek, tryby "
                "odtwarzania.",
            ]},
            {"p": "**Nośnik wybierasz raz, przy zakładaniu projektu**, i wszystko dalej z tego wynika: "
                  "jakie szablony dostajesz do wyboru, jak nazywa się druga strona i które pozycje "
                  "pokazuje menu Nagrywanie. Projekt MiniDisc nigdy nie dostaje wypalania CD, a projekt "
                  "CD — pilota do magnetofonu."},
            {"p": "Pierwsze z nich nie wymaga niczego poza komputerem. Pozostałe trzy potrzebują "
                  "**MDRem**: małej płytki RP2040, która udaje pilota Sony RM-D10P i wpina się w USB. "
                  "Wszystko, co dotyczy MDRem, jest opcjonalne i wyłączone, dopóki go nie włączysz."},
            {"fig": ("signal-chain", COVER_CAPTION)},
            {"p": "Trzy osobne połączenia — i warto od razu wiedzieć, które co przenosi. Kabel USB "
                  "przenosi wyłącznie komendy; dźwięk nigdy nim nie płynie. Wiązka podczerwieni przenosi "
                  "naciśnięcia klawiszy, dokładnie tak jak zwykły pilot. Dźwięk idzie zupełnie inną "
                  "drogą, przez S/PDIF, i jest potrzebny tylko przy nagrywaniu."},
            {"h2": "Co jest potrzebne"},
            {"table": {
                "head": ["Do czego", "Co potrzeba"],
                "rows": [
                    ["Projektowanie i druk", "xD-Tools, drukarka, a do cięcia — ploter Cricut albo pewna "
                                             "ręka i nożyczki."],
                    ["Nadawanie tytułów", "Przystawka MDRem w porcie USB i magnetofon MiniDisc Sony, w "
                                          "który da się nią wycelować."],
                    ["Nagrywanie albumu", "Powyższe oraz kabel cyfrowy (S/PDIF) z komputera do "
                                          "magnetofonu — albo analogowy, realnym kosztem jakości. Nic "
                                          "poza samym xD-Tools: album odtwarza sam program."],
                ],
            }},
            {"note": "Wszystko w tej instrukcji zostało ustalone na **Sony MDS-JE480**. Inne magnetofony "
                     "Sony obsługujące protokół klawiaturowy RM-D10P powinny zachowywać się tak samo, ale "
                     "zwłaszcza czasy zmierzono właśnie na tym modelu."},
            {"h2": "Jedna rzecz do zrozumienia na starcie"},
            {"p": "Magnetofon nie może odpowiedzieć. Podczerwień działa tylko w jedną stronę, a magistrala "
                  "Control A1 nie jest w tym modelu podłączona. xD-Tools może więc wysłać polecenie, ale "
                  "nigdy nie dowie się, czy magnetofon je wykonał."},
            {"p": "To kształtuje całą część programu związaną z MDRem: pokazuje dokładnie, co zamierza "
                  "zrobić, zanim to zrobi; woli zrobić za dużo niż za mało (kasuje stary tytuł większą "
                  "liczbą naciśnięć, niż mogłaby być potrzebna); a kiedy melduje powodzenie, znaczy to "
                  "„wszystko zostało wysłane”, nigdy „na płycie jest teraz to i to”. Sprawdź wyświetlacz "
                  "magnetofonu samodzielnie."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Pierwsze kroki",
        "blocks": [
            {"h2": "Instalacja"},
            {"p": "Jeżeli masz gotową paczkę, uruchom `xD-Tools.exe`. Ze źródeł:"},
            {"ul": [
                "`python -m venv .venv`",
                "`.venv\\Scripts\\pip install -e \".[dev]\"`",
                "`.venv\\Scripts\\python -m mdtools.main`",
            ]},
            {"h2": "Wybór języka"},
            {"p": "**Pomoc > Język** daje English, Polski i japoński. Zmiana wymaga restartu, a program "
                  "sam proponuje, że go wykona."},
            {"h2": "Ekran powitalny"},
            {"p": "xD-Tools zaczyna od krótkiej listy tego, co możesz chcieć zrobić: wrócić do jednego z "
                  "ostatnich projektów, wskazać inny albo zacząć nowy."},
            {"fig": ("startup", "Ekran powitalny. Przycisk Pilot... pojawia się dopiero po włączeniu przystawki.")},
            {"ul": [
                "**Otwórz wybrany** albo dwuklik — powrót do ostatniego projektu.",
                "**Otwórz inny projekt...** — wskazanie pliku `.mdproj` w dowolnym miejscu.",
                "**Nowy projekt...** — wybór nośnika, a potem szablonu dla każdej strony, jaką ma.",
                "**Multiprint...** — złożenie grafik z kilku różnych projektów na jednej kartce. To nie "
                "otwiera żadnego projektu; to samodzielne zadanie.",
                "**Pilot...** — programowy pilot. Też samodzielny, widoczny tylko przy włączonym MDRem.",
            ]},
            {"h2": "Projekt to jego strony plus metadane"},
            {"p": "Ile stron i jakich — o tym decyduje nośnik. Projekt MiniDisc ma **Etykietę płyty** i "
                  "**Okładkę / J-Card**. Projekt CD ma etykietę płyty i **Wkładkę do pudełka**, a jako "
                  "trzecią może wziąć **Tył pudełka**. Projekt kasety nie ma etykiety płyty wcale: ma "
                  "wkładkę **J-Card** i po jednej **etykiecie na każdą stronę** taśmy. Przełączasz się "
                  "między nimi listą w lewym górnym rogu okna."},
            {"p": "Obok stron każdy projekt trzyma tytuł albumu, wykonawcę, rok i listę utworów — z "
                  "których korzystają zarówno same projekty, jak i nadawanie tytułów oraz automatyczne "
                  "układanie."},
            {"fig": ("new-project", "Plik > Nowy pyta o jeden szablon na stronę.")},
            {"p": "**Plik > Zapisz** (Ctrl+S) zapisuje to wszystko — oba projekty, metadane i wstawione "
                  "obrazy — do jednego pliku `.mdproj`. Obrazy są osadzone, a nie dowiązane, więc "
                  "przeniesienie projektu ani skasowanie oryginalnego zdjęcia niczego nie zepsuje."},
            {"h2": "Zamykanie projektu"},
            {"p": "**Plik > Zamknij projekt** (Ctrl+W) nie kończy programu, tylko przywraca ekran "
                  "powitalny — przejście do kolejnej płyty nie wymaga więc ponownego uruchamiania. "
                  "Krzyżyk okna robi to samo. Jeżeli są niezapisane zmiany, program najpierw o nie "
                  "zapyta."},
            {"p": "Żeby wyjść z xD-Tools na dobre, użyj **Plik > Zakończ** albo anuluj ekran powitalny, "
                  "kiedy się pojawi."},
            {"h2": "Gdzie zapisywane są projekty"},
            {"p": "Przy pierwszym zapisie xD-Tools proponuje **Dokumenty\\XDProjects** i nazwę pliku "
                  "zbudowaną z samego albumu - `Skillet - Unleashed (2016).mdproj`. To ten sam napis, "
                  "który dostaje magnetofon, więc plik na komputerze i tytuł na płycie się zgadzają."},
            {"p": "Pozostałe okna plików też startują w sensownym miejscu: **Dodaj obraz...** i okładka "
                  "otwierają się w folderze Obrazy, a eksporty SVG, PNG i PDF **obok projektu, z "
                  "którego pochodzą**, żeby projekt i pliki, które go tną i drukują, trzymały się razem."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Okno główne",
        "blocks": [
            {"fig": ("main-disc", "Strona etykiety płyty, ułożona automatycznie z albumu.")},
            {"h2": "Obszar roboczy"},
            {"p": "Środek okna to strona, którą edytujesz, narysowana w rzeczywistym rozmiarze. Czerwone i "
                  "niebieskie linie to linie cięcia i zagięcia szablonu — rysowane zawsze na wierzchu "
                  "grafiki, żeby było widać, gdzie są krawędzie, i nigdy nie trafiają do "
                  "wyeksportowanego PNG. Zakreskowany obszar poza nimi zostanie odcięty."},
            {"ul": [
                "**Powiększ / Pomniejsz / 100% / Dopasuj** na pasku narzędzi, albo Ctrl z kółkiem myszy, "
                "albo Ctrl+= i Ctrl+-.",
                "**Skala szarości** pokazuje stronę tak, jak wyjdzie na wydruku czarno-białym, z "
                "suwakami jasności i kontrastu obok. To tylko podgląd — obszar roboczy jest wtedy tylko "
                "do odczytu — a to, co tu ustawisz, wykorzysta Eksportuj wydruk PNG (skala szarości).",
            ]},
            {"p": "Nad obszarem roboczym są dwa paski narzędzi. Górny to zwykły rząd operacji na "
                  "pliku i edycji, jaki ma każdy program — Nowy, Otwórz, Zapisz, Drukuj, Cofnij, Ponów, "
                  "Wytnij, Kopiuj, Wklej i Usuń — a każdy przycisk to dokładnie to samo polecenie co "
                  "pozycja menu o tej samej nazwie, z tym samym skrótem klawiszowym. Dolny należy do "
                  "strony, którą masz przed sobą: która strona, który szablon, powiększenie i podgląd w "
                  "skali szarości."},
            {"h2": "Trzy panele"},
            {"p": "**Narzędzia** (po lewej) dodaje rzeczy na stronę: tekst, wypełniony prostokąt, obraz z "
                  "pliku, obraz z wbudowanej galerii albo tekst wzięty wprost z metadanych projektu. Pod "
                  "separatorem są cztery operacje działające na całej stronie — Przycinaj warstwy, "
                  "Spłaszcz warstwy, Zapisz jako szablon i automatyczne układanie. Wszystkie przyciski są "
                  "same ikony; najedź myszą, żeby zobaczyć nazwę."},
            {"p": "**Właściwości** (prawy górny) edytuje to, co jest zaznaczone, i pokazuje wyłącznie pola, "
                  "które mają sens: tekst dostaje treść, rozmiar, czcionkę i kolor; prostokąt sam kolor; "
                  "obraz żadnego z nich. **Pobierz kolor...** pobiera kolor prosto z obszaru roboczego — "
                  "tak dopasujesz tekst do barwy z okładki."},
            {"p": "**Warstwy** (prawy dolny) wypisuje wszystko na stronie, od przodu do tyłu. Zaznacz, "
                  "zmień nazwę, przestaw kolejność (Przesuń w górę / Przesuń w dół) albo usuń. Obrys "
                  "szablonu nie jest warstwą i nie da się go tu ruszyć."},
            {"note": "Wszystkie trzy panele można zamknąć i przywrócić z menu **Widok**, a także wyciągnąć "
                     "jako osobne okna."},
            {"h2": "Kiedy coś się nagrywa"},
            {"p": "Nagrywanie, zgrywanie, wypalanie i zapisywanie tytułów odbywa się w osobnym oknie - "
                  "a gdy takie okno pracuje, jego **przycisk zamknięcia (X)** chowa je, zamiast "
                  "przerywać pracę. Praca trwa dalej: główne okno znów jest dostępne, a na dole, nad "
                  "paskiem stanu, pojawia się pasek postępu. Pokazuje postęp całości, bieżący utwór "
                  "(jeśli jest), przycisk **Zatrzymaj** oraz **Pokaż okno nagrywania**, który przywraca "
                  "okno."},
            {"note": "Gdy nic nie trwa, X zamyka okno tak jak wszędzie indziej. Od przerywania pracy "
                     "jest **Zatrzymaj** — a przycisk obok niego nosi nazwę **Anuluj**, gdy coś trwa, i "
                     "**Zamknij**, gdy nie, żeby ten, który porzuca pracę, nigdy nie wyglądał tak samo "
                     "jak ten, który tylko zamyka skończone okno."},
            {"p": "Pasek zostaje tak długo, jak długo to okno jest otwarte - również po zakończeniu samej "
                  "pracy. To jedyna droga powrotu do ukrytego okna, więc znika dopiero razem z nim."},
            {"note": "Naraz może działać tylko jedna taka operacja. W trakcie jej trwania uruchomienie "
                     "kolejnej - albo zamknięcie xD-Tools - zostanie odrzucone: biłyby się o ten sam "
                     "adapter, napęd lub urządzenie dźwiękowe."},
            {"h2": "Który projekt jest otwarty"},
            {"p": "Gdy projekt został już zapisany, na pasku tytułu widnieje nazwa jego pliku - "
                  "*Kind of Blue - xD-Tools*. Ta sama nazwa pojawia się na pasku zadań i w Alt+Tab, co "
                  "pozwala odróżnić dwa okna xD-Tools. Projekt jeszcze niezapisany nie ma nazwy pliku, "
                  "więc zostaje przy *xD-Tools - Retro Media Studio*."},
            {"h2": "Przesuwanie, skalowanie i obracanie"},
            {"ul": [
                "Przeciągnij **środek** elementu, żeby go przesunąć.",
                "Przeciągnij **niebieski kwadrat w narożniku**, żeby zmienić rozmiar. Domyślnie szerokość "
                "i wysokość zmieniają się niezależnie; przytrzymaj **Ctrl**, żeby zachować proporcje.",
                "Przeciągnij **kółko nad nim**, żeby obracać. **Ctrl** przyciąga do co 10 stopni — tak "
                "uzyskasz dokładny obrót o ćwierć obrotu.",
                "Delete albo Backspace usuwa zaznaczenie.",
            ]},
            {"p": "Wszystko przechodzi przez cofanie (Ctrl+Z), łącznie z automatycznym układaniem."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Szablony",
        "blocks": [
            {"p": "Szablon to fizyczny kształt drukowanej rzeczy: rozmiar, narożniki i miejsca zagięć. "
                  "xD-Tools ma dwanaście wbudowanych, na trzy nośniki."},
            {"table": {
                "head": ["Szablon", "Co to jest"],
                "rows": [
                    ["MiniDisc Disc Label", "Klasyczna naklejka 37 × 52 mm na front płyty, ze ścięciem 3 "
                                            "mm w lewym górnym narożniku i zaokrągleniami w pozostałych."],
                    ["MiniDisc Disc Label (with Slider)", "To samo plus osobna mała naklejka na przesuwną "
                                                          "osłonę kasety."],
                    ["Full disc label", "Etykieta na całą powierzchnię kasety, 71 × 68 mm pomniejszone o "
                                        "margines 0,8 mm, z wyciętą osłoną."],
                    ["Full disc label (with Slider)", "Cała powierzchnia plus naklejka osłony, wpasowana "
                                                      "w wycięcie, w którym leży. To proponuje Plik > "
                                                      "Nowy przy nowym projekcie MiniDisc."],
                    ["MiniDisc Cover (J-Card)", "Trzypanelowa wkładka do pudełka: przód, grzbiet, tył."],
                    ["MiniDisc Cover (J-Card + Window)", "To samo z okienkiem 40 × 40 mm wyciętym w "
                                                         "przodzie, przez które widać płytę."],
                    ["CD Disc Label (Standard Hub)", "Pierścień na wierzch płyty CD-R: 117 mm średnicy z "
                                                     "otworem 35 mm na piastę."],
                    ["CD Slim Case Insert (Front)", "Jedna karta 120 × 120 mm — przód pudełka slim, bez "
                                                    "zagięcia i bez listy utworów."],
                    ["CD Slim Case Insert (Folded, 2 Panels)", "240 × 120 mm zgięte w połowie: okładka na "
                                                               "prawym panelu, lista utworów na lewym, "
                                                               "czytana przez przezroczysty tył pudełka."],
                    ["CD Jewel Case Back (Tray Card)", "151 × 117,5 mm: panel 138 mm z zadrukowanym "
                                                       "grzbietem 6,5 mm po każdej stronie, na tackę za "
                                                       "płytą."],
                    ["Cassette J-Card", "Wkładka 4 × 4 cale: przód, grzbiet i zakładka wsuwana do środka."],
                    ["Cassette Shell Label", "90 × 40,8 mm, wycinana wokół otworu na szpule, z górnymi "
                                             "narożnikami ściętymi pod 45 stopni. Jedna na stronę."],
                ],
            }},
            {"note": "**Osłona** to przesuwana klapka na kasecie, która chroni płytę od kurzu — magnetofon "
                     "odsuwa ją, żeby dostać się do powierzchni. To nie jest suwak zabezpieczenia przed "
                     "zapisem, który jest osobną małą blokadą na krawędzi kasety i nigdy nie dostaje "
                     "naklejki. Ponieważ osłona musi się nadal przesuwać, szablony na całą powierzchnię "
                     "wycinają kanał na cały jej skok, a nie tylko na pozycję spoczynkową: etykieta nad "
                     "tym kanałem zablokowałaby ją na zamknięte."},
            {"fig": ("templates", "Szablony > Zarządzaj szablonami.")},
            {"h2": "Zweryfikowane i niezweryfikowane"},
            {"p": "Szablon jest oznaczony jako **Zweryfikowany** dopiero wtedy, gdy jego wymiary "
                  "sprawdzono na prawdziwym elemencie. Kiedy patrzysz na stronę z niezweryfikowanym "
                  "szablonem, mówi o tym pasek stanu — zmierz własne pudełko, popraw liczby i zaznacz "
                  "pole, zanim cokolwiek naprawdę wytniesz."},
            {"h2": "Własne szablony"},
            {"p": "Wbudowane szablony można edytować, ale nie da się ich usunąć, więc Plik > Nowy zawsze "
                  "ma co zaproponować. Dodane samodzielnie usuwa się bez przeszkód."},
            {"p": "**Narzędzia > Zapisz jako szablon...** zapisuje kształt bieżącej strony *razem ze "
                  "wszystkim, co na niej leży*, jako nowy szablon — układ, który ci się podoba, może być "
                  "punktem wyjścia dla następnej płyty."},
            {"h2": "Dodawanie i usuwanie stron"},
            {"p": "Projekt zaczyna się od dwóch stron — etykiety płyty i okładki — a projekt CD może mieć "
                  "trzecią: **tył pudełka**, czyli tackę, która siedzi za płytą, z zadrukowanym paskiem "
                  "wzdłuż każdego boku pudełka. Proponowana jest przy zakładaniu projektu (wiersz **Tył "
                  "pudełka**, który zaczyna od *(brak)*), a później można ją dołożyć lub zdjąć przyciskami "
                  "**+**/**-** na pasku narzędzi, obok wyboru strony."},
            {"p": "Przycisk **+** pyta o wszystko w jednym okienku: o którą stronę, o szablon i o to, czy "
                  "zacząć ją pustą, czy od razu wypełnić danymi albumu. Lista szablonów zmienia się wraz "
                  "z wybraną stroną, a wypełnianie jest wygaszone przy szablonie, dla którego "
                  "automatyczny układ nie ma przepisu."},
            {"note": "Etykieta płyty i okładka są częścią każdego projektu i nie da się ich usunąć. Zdjąć "
                     "można tylko strony opcjonalne, a usunięcie kasuje wszystko, co na nich jest — "
                     "dlatego program pyta wcześniej i zeruje potem historię cofania."},
            {"h2": "Zmiana szablonu później"},
            {"p": "Rozwijana lista **Szablon** na pasku narzędzi, obok wyboru strony, pokazuje każdy "
                  "szablon dostępny dla bieżącej strony. Wybranie własnego (zapisanego przez **Zapisz "
                  "jako szablon...** albo dodanego w Menedżerze szablonów) od razu przełącza stronę na "
                  "niego. Wybranie wbudowanego pyta najpierw i daje wybór: zacząć stronę **pustą** albo "
                  "zbudować ją od nowa z metadanych projektu przyciskiem **Wygenerowany z metadanych**, "
                  "który działa dla każdego szablonu dołączonego do programu. Wygaszony jest tylko w "
                  "jednym przypadku: gdy wbudowany szablon został przemianowany i żaden układ już go po "
                  "nazwie nie rozpoznaje."},
            {"warn": "W obu przypadkach **czyści to stronę**: znikają wszystkie warstwy, a historia "
                     "cofania jest zerowana. Druga strona i metadane pozostają nietknięte."},
            {"h2": "Przebudowa strony"},
            {"p": "Dwa przyciski na pasku narzędzi budują oglądaną stronę od nowa z metadanych projektu, "
                  "nie ruszając jej szablonu. **Wygeneruj ponownie** używa domyślnych krojów i stylu "
                  "strony — i tą samą drogą wraca się do nich po wypróbowaniu innego kroju. "
                  "**Wygeneruj ponownie z czcionką...** otwiera zamiast tego okno wyboru czcionki: po "
                  "wskazaniu kroju strona od razu rysuje się na nowo, więc wynik widać jeszcze przed "
                  "zatwierdzeniem. Z wyboru brany jest tylko sam krój — rozmiary i grubości nadal "
                  "pochodzą z układu, który dopasowuje je do każdego panelu."},
            {"warn": "Oba czyszczą stronę i zerują historię cofania, i oba pytają, zanim to zrobią. Na "
                     "stronie z Twoim własnym szablonem nie ma czego przebudowywać — automatyczny układ "
                     "zna tylko kształty wbudowane — i program to napisze, zamiast zostawiać cię z "
                     "pytaniem, dlaczego nic się nie stało."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Metadane i okładka",
        "blocks": [
            {"p": "**Metadane...** w panelu Narzędzia trzymają tytuł albumu, wykonawcę, rok i listę "
                  "utworów. Warto je "
                  "wypełnić nawet przy samym projektowaniu etykiety: listę utworów można wrzucić na "
                  "grafikę jako tekst, a automatyczne układanie i nadawanie tytułów czytają właśnie stąd."},
            {"fig": ("metadata", "Okno Metadane, z pobraną okładką i wczytaną listą utworów.")},
            {"h2": "Trzy sposoby wypełnienia"},
            {"ol": [
                "**Ręcznie.** Dodaj utwór, wpisz, ustaw kolejność przyciskami Przesuń w górę / w dół. "
                "Czasy są opcjonalne i zapisuje się je jako mm:ss.",
                "**Wyszukaj listę utworów...** przeszukuje katalog iTunes po wpisanym albumie i "
                "wykonawcy, po czym uzupełnia listę utworów, rok i okładkę. Jeżeli pasuje więcej niż "
                "jedno wydanie, program pyta które.",
                "**Importuj z folderu...** czyta własne tagi z folderu albumu — tym samym mechanizmem, "
                "co samo nagrywanie — i na ich podstawie uzupełnia wykonawcę, album, rok i listę "
                "utworów, a potem szuka do tego okładki.",
            ]},
            {"tip": "**Import z folderu to zwykle lepsze źródło.** To są te konkretne pliki, które zaraz "
                    "nagrasz, z ich własnymi tagami i w ich własnej kolejności — wyszukiwanie może "
                    "zwrócić inne wydanie z inną kolejnością utworów."},
            {"h2": "Okładka"},
            {"p": "Pobrana okładka zapisuje się w dwóch miejscach: w projekcie, żeby była tam przy "
                  "następnym otwarciu, oraz w galerii użytkownika, żeby **Narzędzia > Wstaw zasób...** "
                  "mogło ją wstawić na stronę jak każdy inny obraz."},
            {"tip": "**Jeżeli pobrana okładka jest nie ta, kliknij ją.** Podgląd jest przyciskiem: "
                    "otwiera okno wyboru pliku, żebyś sam wskazał właściwą. Oba automatyczne źródła "
                    "zgadują i przy wznowieniu, składance albo zespole o popularnej nazwie regularnie "
                    "zgadują źle — wyszukiwarka nie ma jak wiedzieć, które tłoczenie trzymasz w ręku."},
            {"h2": "Gdy nie ma czego znaleźć"},
            {"p": "xD-Tools woli nie pokazać żadnej okładki niż złą. Wynik musi zgadzać się i z "
                  "tytułem albumu, **i** z wykonawcą: sam tytuł nie wystarcza, bo przeróbka "
                  "tytułowego utworu nagrana przez kogoś innego pasuje do niego idealnie. Kiedy nic "
                  "nie przechodzi progu, podgląd zostaje pusty — to uczciwa odpowiedź, a do "
                  "poprawienia jej wystarczy jedno kliknięcie."},
            {"p": "Jest jeszcze jedno miejsce do sprawdzenia. Pliki FLAC często niosą okładkę w "
                  "sobie, a większość zgranych własnych płyt ją ma. Gdy wyszukiwarka nie zwróci nic "
                  "sensownego, używany jest właśnie ten obrazek. To na pewno okładka tego wydania; "
                  "jest druga w kolejce tylko dlatego, że bywa mniejszym skanem niż 600-pikselowa "
                  "grafika z wyszukiwarki. Pliki MP3 nie są w ten sposób czytane."},
            {"h2": "Metadane na stronie"},
            {"p": "Przycisk metadanych w panelu Narzędzia wstawia dowolne pojedyncze pole — album, "
                  "wykonawcę, rok — albo całą numerowaną listę utworów jako warstwę tekstową. Potrafi też "
                  "wstawić listę w **dwóch kolumnach obok siebie**, czego wymaga dłuższa lista na tylnym "
                  "panelu J-card."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Automatyczne układanie",
        "blocks": [
            {"p": "**Różdżka** w panelu Narzędzia wypełnia każdą stronę projektu okładką i listą utworów "
                  "albumu. To najszybsza droga od „mam płytę” do „mam co wydrukować”."},
            {"p": "Każdą stronę buduje **na tym szablonie, który ta strona już ma** — nie zmienia twojego "
                  "wyboru kształtu. Stronę z twoim własnym szablonem pomija w całości: automatyczny układ "
                  "zna tylko kształty wbudowane, a w szablonie zapisanym samodzielnie może już leżeć "
                  "dokładnie to, o co ci chodziło."},
            {"p": "Najpierw wypełnij album i wykonawcę w **Metadanych...** — po tym program szuka. "
                  "Jeżeli nie ma jeszcze okładki, najpierw ją znajdzie."},
            {"warn": "To **zastępuje zawartość każdej budowanej strony** i zeruje historię cofania, więc "
                     "program prosi o potwierdzenie. Same metadane zostają nietknięte."},
            {"h2": "Co powstaje"},
            {"p": "**Etykieta płyty**: szablon na całą powierzchnię, okładka rozciągnięta na nią i "
                  "przycięta do linii cięcia oraz logo MiniDisc na naklejce osłony. Trójkąt kierunku "
                  "wkładania i jego podpis zostają na wierzchu grafiki, zamiast zniknąć pod nią."},
            {"p": "Ten znak **zmienia też kolor pod okładkę**: na czarny albo biały, zależnie od tego, "
                  "który pozostanie czytelny na górze konkretnej okładki. Zostawiony w domyślnej czerni "
                  "na ciemnej okładce na spad nadal tam był, tylko niewidoczny — a to wygląda dokładnie "
                  "tak, jakby zniknął."},
            {"fig": ("main-jcard", "J-card, z kolorami wziętymi wprost z okładki.")},
            {"p": "**J-card**, w trzech panelach:"},
            {"ul": [
                "**Przód** — okładka obrócona o ćwierć obrotu, tak że jej górna krawędź biegnie wzdłuż "
                "lewego boku wkładki, wypełniająca panel, z małym logo MiniDisc w rogu.",
                "**Grzbiet** — pas w kolorze akcentu wyjętym z okładki, z rokiem, albumem i wykonawcą "
                "obróconymi tak, żeby czytać wzdłuż niego.",
                "**Tył** — najczęstszy kolor okładki, z numerowaną listą utworów, dzieloną na dwie "
                "kolumny, gdy zrobi się długa, i łącznym czasem u dołu.",
            ]},
            {"p": "Przód i tył są obrócone w *przeciwne* strony celowo: wkładka owija się wokół pudełka, "
                  "więc tył wypada odwrotnie."},
            {"note": "Wszystko, co powstaje, to zwykłe warstwy. Przesuwaj je, zmieniaj styl, usuwaj — to "
                     "pierwszy szkic, a nie gotowy projekt."},
            {"h2": "Tył pudełka, jeśli jest"},
            {"p": "Projekt CD z tyłem pudełka dostaje i jego układ: nazwa albumu i wykonawcy biegnie "
                  "wzdłuż **obu** bocznych pasków — to, która strona pudełka jest widoczna, zależy od "
                  "tego, jak stoi na półce — a między nimi ląduje spis utworów w kolorach okładki."},
            {"fig": ("cd-back", "Tacka: zadrukowany pasek wzdłuż każdego boku pudełka i spis utworów na "
                                "panelu, który siedzi za płytą.")},
            {"note": "W odróżnieniu od dwóch pozostałych stron ta zachowuje szablon, który jej nadałeś. "
                     "Istnieje tylko dlatego, że sam ją dodałeś i wybrałeś jej kształt, a układ nie ma "
                     "prawa tego cofać."},
            {"h2": "Przycinaj warstwy i Spłaszcz warstwy"},
            {"p": "**Przycinaj warstwy** dociąga wszystko do obszaru drukowalnego: warstwy leżące "
                  "całkowicie poza nim znikają, obrazy wystające poza krawędź są do niej przycinane. "
                  "Automatyczne układanie etykiety używa tego, żeby przyciąć celowo za dużą okładkę do "
                  "linii cięcia."},
            {"p": "**Spłaszcz warstwy** zamienia całą stronę w jeden obraz, dokładnie tak, jak wyrenderuje "
                  "ją eksport PNG. Przydaje się do zamknięcia gotowego projektu; pamiętaj, że "
                  "rozdzielczość spłaszczonej warstwy jest już nieodwracalna — dlatego renderuje się w "
                  "wyższym DPI niż zwykły eksport."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Druk i cięcie",
        "blocks": [
            {"h2": "Dwa eksporty"},
            {"p": "Projekt opuszcza xD-Tools jako dwa pliki opisujące ten sam przedmiot na dwa sposoby."},
            {"table": {
                "head": ["Eksport", "Zawiera", "Do czego"],
                "rows": [
                    ["**Eksportuj wydruk PNG...**", "Twoją grafikę, domyślnie w 300 DPI, przyciętą do "
                                                    "obrysu szablonu — poza nim przezroczystą, łącznie ze "
                                                    "ściętym i zaokrąglonymi narożnikami.", "Do druku."],
                    ["**Eksportuj cięcie SVG...**", "Wyłącznie linie cięcia i zagięcia bieżącej strony, w "
                                                    "rzeczywistych jednostkach. Bez grafiki.", "Do plotera."],
                    ["**Eksportuj wydruk PNG (skala szarości)...**", "Tę samą grafikę zamienioną na "
                                                                     "szarości, poprzedzoną oknem "
                                                                     "jasności/kontrastu z podglądem na "
                                                                     "żywo.", "Do drukarek mono."],
                ],
            }},
            {"h2": "Droga przez Cricut"},
            {"ol": [
                "Wyeksportuj PNG i wydrukuj je na papierze samoprzylepnym albo kartonie.",
                "Zaimportuj SVG do Cricut Design Space.",
                "Użyj **Print Then Cut**: ploter znajduje znaczniki na wydrukowanej kartce i wycina obrys "
                "z SVG dokładnie na niej.",
            ]},
            {"p": "SVG niesie rzeczywiste milimetry, więc po drugiej stronie nie trzeba niczego skalować "
                  "ręcznie."},
            {"h2": "Orientacja i osobne arkusze"},
            {"p": "Okno druku ma **Rozmiar strony** i **Orientację**. Pozioma nie jest ozdobnikiem: "
                  "składana wkładka do slima ma 242 mm szerokości i na pionowej kartce nie mieści się "
                  "prosto — na pionowym A4 da się ją wydrukować wyłącznie obróconą o ćwierć obrotu."},
            {"p": "**Każda etykieta na osobnym arkuszu** robi dokładnie to, co mówi, a dla projektu CD "
                  "włącza się sama. Powód jest arytmetyczny, nie estetyczny: etykieta płyty (118 mm) obok "
                  "tej wkładki (242 mm) potrzebuje 363 mm z arkusza, który daje 287 mm — więc razem nie "
                  "zmieszczą się w żadnym ułożeniu. Przy włączonej opcji podgląd pokazuje jeden arkusz "
                  "naraz (wybierasz go polem **Pokazywany**), a druk, eksport PDF i eksport PNG obchodzą "
                  "oba. PNG mieści jedną stronę, więc eksport dwóch arkuszy zapisuje dwa ponumerowane "
                  "pliki."},
            {"fig": ("cd-print", "Układ druku projektu CD: etykieta płyty na jednym arkuszu, składana "
                                 "wkładka na drugim.")},
            {"h2": "Druk bezpośrednio"},
            {"p": "**Plik > Drukuj...** pomija etap eksportu: układa kilka kopii obu stron na jednej "
                  "kartce A4 albo Letter, automatycznie w siatkę, którą potem możesz poprzesuwać myszą. "
                  "Kliknięcie kopii prawym przyciskiem obraca ją o 90 stopni, co często pozwala zmieścić "
                  "jeszcze jedną."},
            {"fig": ("print", "Plik > Drukuj. Podgląd to fizyczna kartka.")},
            {"p": "Stąd możesz wysłać wszystko na prawdziwą drukarkę albo zapisać dokładnie to, co widać, "
                  "jako PDF lub PNG."},
            {"p": "**Multiprint...** z ekranu powitalnego robi to samo, ale w poprzek *różnych* projektów "
                  "— dorzuć grafiki z kilku zapisanych plików `.mdproj` na jedną kartkę, żeby stos płyt "
                  "był jednym wydrukiem zamiast sześcioma."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Przystawka MDRem",
        "blocks": [
            {"p": "MDRem to płytka Waveshare RP2040-Zero z diodą podczerwieni, z firmware'em emulującym "
                  "**Sony RM-D10P** — pilota-klawiaturę, którego Sony sprzedawało w połowie lat "
                  "dziewięćdziesiątych do wpisywania tytułów na MiniDisc. W komputerze widać go jako "
                  "zwykły port szeregowy."},
            {"h2": "Sprzęt"},
            {"table": {
                "head": ["Pin", "Rola"],
                "rows": [
                    ["GPIO12", "Wyjście podczerwieni, na rezystor bazy tranzystora."],
                    ["GPIO13", "Wejście, używane wyłącznie przez autotest `SELFTEST` firmware'u."],
                    ["GPIO16", "Wbudowana dioda statusu RGB płytki."],
                ],
            }},
            {"p": "Diodą steruje tranzystor NPN jako przełącznik dolnego poziomu, bo dziesiątek "
                  "miliamperów nie da się przepuścić wprost przez pin GPIO. Zasilanie idzie z VBUS, nie ze "
                  "stabilizatora 3,3 V."},
            {"fig": ("ir-circuit", "Stopień wyjściowy: S9014, Rb = 470 Ω, Rd = 47 Ω (około 72 mA).")},
            {"tip": "**Jeśli zasięg jest kiepski, popatrz najpierw na Rd.** Przy 100 Ω (około 34 mA) "
                    "trzeba było podejść na centymetr–dwa i celować co do milimetra; przy 47 Ω działa z "
                    "wygodnych 20–30 cm. Nie schodź poniżej mniej więcej 33 Ω — 100 mA to granica S9014."},
            {"h2": "Dioda statusu"},
            {"table": {
                "head": ["Kolor", "Znaczenie"],
                "rows": [
                    ["Biały", "Uruchamianie."],
                    ["Zielony", "Gotowy; ostatnia komenda się powiodła."],
                    ["Niebieski", "Trwa nadawanie podczerwieni."],
                    ["Czerwony", "Ostatnia komenda zawiodła. Świeci do następnego sukcesu."],
                    ["Fioletowy", "Nie udało się zainicjować sprzętu — przystawka nie działa."],
                ],
            }},
            {"h2": "Włączenie w xD-Tools"},
            {"p": "**Okno > Ustawienia...**, zaznacz **Włącz przystawkę MDRem (pilot na podczerwień)** i "
                  "wybierz port szeregowy."},
            {"fig": ("settings", "Okno > Ustawienia. Urządzenia wyjścia audio są niezależne od "
                                 "przystawki — do nagrywania potrzeba urządzenia, nie łącza na "
                                 "podczerwień.")},
            {"p": "Ustawienia to jedno okno z listą grup po lewej stronie. **Ogólne** to wszystko, co "
                  "opisano tutaj; **Telegram** to konto bota (osobny rozdział). Niezależnie od tego, "
                  "która grupa jest na ekranie, **OK** zapisuje je wszystkie."},
            {"p": "**Wykryj** pyta każdy port szeregowy w komputerze, czy odpowiada na nim MDRem. Musi tak "
                  "działać: płytka zgłasza identyfikator USB `2E8A:0003`, ten sam co jej własny bootloader "
                  "i inne płytki Waveshare, więc jedyną pewną identyfikacją jest odpowiedź urządzenia na "
                  "`PING`."},
            {"p": "Po zaznaczeniu pola pojawiają się trzy rzeczy: **Wyślij listę utworów** w oknie "
                  "Metadane..., **Pilot...** w menu Okno oraz właściwe MiniDiscowi pozycje menu "
                  "**Nagrywanie** — Nagraj folder na MiniDisc i Nagraj z folderu zgrywania/pobierania "
                  "na MiniDisc, bo obie potrzebują przystawki, żeby uzbroić magnetofon. **Źródło > "
                  "Zgraj płytę audio CD...** nie jest wśród nich: zgrywanie kończy się na plikach i w "
                  "ogóle nie dotyka magnetofonu."},
            {"note": "**Urządzenie wyjścia audio dla MiniDisc** i **Urządzenie wyjścia audio dla "
                     "kasety**, na tej samej stronie, celowo *nie* są powiązane z tym polem — kaseta "
                     "potrzebuje urządzenia wyjściowego niezależnie od tego, czy przystawka jest "
                     "włączona, bo nagrywanie na nią w ogóle nie przechodzi przez MDRem. Każde z nich "
                     "pamięta swój własny wybór, bo cyfrowe wyjście S/PDIF do jednego magnetofonu i "
                     "analogowe wyjście liniowe do drugiego to zwykle dwa różne fizyczne gniazda. "
                     "**Wzmocnienie nagrywania** (domyślnie -5 dB) trochę ścisza sygnał, zanim opuści "
                     "komputer, żeby głośne źródło cyfrowe nie miało szans na przesterowanie po drodze — "
                     "na odsłuch poniżej nie wpływa."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Programowy pilot",
        "blocks": [
            {"p": "Programowy pilot to zamiennik pilota magnetofonu, ułożony tak jak ten fizyczny. Otwiera "
                  "się go z **Pilot...** na ekranie powitalnym albo z **Okno > Pilot...** — to drugie "
                  "istnieje dlatego, że sięgnięcie po pilota nie powinno wymagać zamykania otwartego "
                  "projektu."},
            {"fig": ("remote", "Okno pilota. Linia stanu mówi, co wysłano, a nie co się stało.")},
            {"table": {
                "head": ["Grupa", "Klawisze"],
                "rows": [
                    ["Transport", "Poprzedni, Play, Następny, przewijanie wstecz, Pauza, przewijanie w "
                                  "przód, Stop, Zasilanie, Wysuń."],
                    ["Utwory", "Od 1 do 10, wybierane wprost — tyle, ile klawiszy ma fizyczny pilot. "
                               "Od 11 do 25 są w trybie rozszerzonym, niżej."],
                    ["Tryb odtwarzania", "Continuous, Shuffle, Program, Repeat, A-B, >25."],
                    ["Wyświetlacz", "Display, Scroll."],
                    ["Nazywanie", "Name, Enter, Delete, Cancel."],
                    ["Nagrywanie", "Record, Music Sync, T.Rec, D.Rec, A.Space, M.Scan."],
                ],
            }},
            {"p": "Grupa Nagrywanie jest celowo trzymana z dala od klawiszy transportu: na prawdziwym "
                  "pilocie Record wymaga świadomego sięgnięcia, a myszą o przypadkowe kliknięcie znacznie "
                  "łatwiej niż kciukiem."},
            {"warn": "Linia stanu mówi **Wysłano**, nigdy **Zrobione**. Magnetofon nie może się odezwać. "
                     "Jeżeli nic się nie dzieje, najczęstsze przyczyny to celowanie i odległość — patrz "
                     "rozdział o rozwiązywaniu problemów."},
            {"tip": "**Record naciśnięty w trakcie nagrywania stawia znacznik ścieżki.** Tak automatyczne "
                    "nagrywanie dzieli album bez przerw i tak samo można tego użyć ręcznie."},
            {"h2": "Tryb rozszerzony"},
            {"p": "Okno powyżej to fizyczny pilot, klawisz w klawisz. Zaznacz **Tryb rozszerzony**, a "
                  "dojdzie reszta tego, co przystawka umie wysłać — kody, które istnieją i zostały "
                  "sprawdzone na prawdziwym magnetofonie, ale do których żaden klawisz plastikowego "
                  "pilota nie sięga. Wybór jest zapamiętywany, więc okno otwiera się tak, jak je "
                  "zostawiłeś."},
            {"fig": ("remote-extended", "Tryb rozszerzony. Ścieżki do 25, własna metoda wpisywania znaków "
                                        "magnetofonu i dwa klawisze edytujące płytę.")},
            {"table": {
                "head": ["Co dochodzi", "Czym jest"],
                "rows": [
                    ["Ścieżki 11–25", "Każda ma własny kod, więc to jedno naciśnięcie, tak jak przy "
                                      "pierwszej dziesiątce. Powyżej 25 numer się wpisuje, a nie "
                                      "naciska — i tym zajmuje się już samo nadawanie tytułów."],
                    ["Char, Num", "Własna metoda wpisywania znaków magnetofonu — przełączanie zestawów "
                                  "znaków i wybór pokrętłem. Program omija ją, wysyłając kody znaków "
                                  "wprost, więc te klawisze są tu dla kompletu."],
                    ["Clear 2", "Jeden z trzech klawiszy, które tabela kodów magnetofonu nazywa Clear. "
                                "W trybie edycji nazwy nie robi nic, gdziekolwiek stoi kursor; "
                                "najpewniej kasuje program odtwarzania."],
                    ["D.Pre", "Magnetofon rozpoznaje go jako polecenie zapisu. Nigdy nie udało się "
                              "rozróżnić, który klawisz z tej grupy co robi."],
                    ["Erase Track, Divide", "Te edytują samą płytę — kasują bieżącą ścieżkę albo dzielą "
                                            "ją na dwie."],
                ],
            }},
            {"warn": "**Erase Track i Divide zmieniają zawartość płyty.** Magnetofon najpierw pyta na "
                     "własnym wyświetlaczu i nie robi nic do czasu Entera, więc Cancel się z tego "
                     "wycofuje — ale przeczytaj wyświetlacz, zanim naciśniesz Enter, bo nic tutaj tego "
                     "nie cofnie."},
            {"h2": "Pisanie z własnej klawiatury"},
            {"p": "RM-D10P, którego to okno zastępuje, jest klawiaturą — i w trybie rozszerzonym to okno "
                  "też nią jest: kiedy jest otwarte, każda wpisana litera, cyfra i znak idzie prosto do "
                  "magnetofonu. Nie ma tu ani pola tekstowego, ani klawiatury ekranowej, i to celowo — "
                  "pilot ma klawisze dlatego, że magnetofon ich nie ma, a komputer, na którym to działa, "
                  "ma lepsze."},
            {"p": "Najpierw wprowadź magnetofon w tryb edycji nazwy: naciśnij **Name** albo wybierz "
                  "ścieżkę i dopiero potem **Name**. Potem pisz. **Backspace** kasuje, **Enter** "
                  "zatwierdza tytuł, a **strzałki** przesuwają kursor po polu."},
            {"note": "Litery z ogonkami tracą po drodze znaki diakrytyczne, dokładnie tak samo jak przy "
                     "zapisywaniu tytułów z projektu — `ł` dociera jako `l`. Znak, który nie ma żadnego "
                     "łacińskiego odpowiednika, jest odrzucany i wypisany w linii stanu, a nie wysyłany "
                     "jako coś innego."},
            {"tip": "Pisanie jest dostosowane do tempa, jakie magnetofon przyjmuje — jakieś trzy, cztery "
                    "naciśnięcia na sekundę. Kiedy piszesz szybciej, program nadąża, czekając: dwa "
                    "naciśnięcia zbyt blisko siebie magnetofon czyta jako jeden przytrzymany klawisz."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Zapisywanie tytułów na płycie",
        "blocks": [
            {"p": "**Metadane... > Wyślij listę utworów** zapisuje tytuł płyty i nazwy "
                  "wszystkich utworów na samym MiniDisc. Tytuł płyty składa się jako "
                  "`Wykonawca - Album (Rok)`, z pominięciem tego, co niewypełnione."},
            {"fig": ("upload", "Wszystko widać, zanim cokolwiek zostanie zapisane.")},
            {"h2": "Zanim ruszy"},
            {"p": "Lista to dokładnie to, co zostanie zapisane, już po konwersji. Przeczytaj ją: to "
                  "jedyna okazja, żeby wychwycić źle wyglądający tytuł, bo potem nic nie powie ci, co "
                  "naprawdę wylądowało na płycie."},
            {"h2": "Jest wolno i to wina magnetofonu"},
            {"p": "Magnetofon przyjmuje około trzy i pół naciśnięcia na sekundę, a każdy znak to osobna "
                  "ramka podczerwieni. Cały album zajmuje trzy do czterech minut. Oryginalny pilot Sony "
                  "nie był szybszy — narzekano na to już w ówczesnych recenzjach. Rzecz w tym, że piszesz "
                  "na normalnej klawiaturze i odchodzisz."},
            {"table": {
                "head": ["Zadanie", "Mniej więcej"],
                "rows": [
                    ["Jeden tytuł ścieżki, na płycie ze starymi nazwami do skasowania", "około 25 s"],
                    ["Jeden tytuł ścieżki, na świeżo nagranej płycie", "około 12 s"],
                    ["Cały album, z kasowaniem", "3 do 4 minut"],
                ],
            }},
            {"h2": "Najpierw skasuj istniejące tytuły"},
            {"p": "Skasowanie starego tytułu to zdecydowanie najwolniejsza część zapisania nowego i "
                  "mniej więcej podwaja łączny czas. Jest włączone domyślnie, bo pozostawienie go "
                  "wyłączonym na istniejącym tytule zostawia stary tekst, w który wjeżdża nowy."},
            {"tip": "**Wyłącz je na świeżo nagranej płycie.** Nie ma tam czego kasować, a czas skraca się "
                    "prawie o połowę. Ścieżka nagrywania wyłącza je za ciebie."},
            {"p": "Ponieważ starego tytułu nie da się odczytać, kasowanie celowo przesadza: wysyła więcej "
                  "naciśnięć Delete, niż nowy tytuł mógłby potrzebować. Nadmiarowe kasowania na pustym "
                  "polu nic nie kosztują."},
            {"h2": "Tytuły są zamieniane na czyste ASCII"},
            {"p": "Magnetofony MiniDisc wyświetlają wyłącznie znaki 0x20–0x7E. Litery z ogonkami tracą "
                  "znaki diakrytyczne — `Zazolc gesla jazn` — a to, co nie ma odpowiednika łacińskiego, "
                  "wypada. Okno wypisuje pominięte znaki, zanim cokolwiek zapisze."},
            {"note": "**Tytuły po japońsku nie działają**, mimo że MiniDisc to japoński format. Katakana "
                     "magnetofonu jest dostępna wyłącznie jego własną metodą wpisywania — klawiszem CHAR "
                     "i pokrętłem — czyli zupełnie inną ścieżką, po dziesięć sekund na znak. Zamiast tego "
                     "transliteruj."},
            {"h2": "Na koniec wysuń płytę"},
            {"warn": "**Magnetofon trzyma zmienione tytuły w pamięci ulotnej aż do wysunięcia płyty.** "
                     "Odetnij wcześniej zasilanie, a wszystko, co właśnie zapisałeś, przepada. Po "
                     "skończeniu program proponuje wysunięcie — zgódź się."},
            {"h2": "Ścieżki powyżej 25"},
            {"p": "Sam pilot ma klawisze numeryczne tylko do 25, ale przystawka wyższy numer wpisuje, "
                  "zamiast naciskać jeden klawisz — ścieżki od 26 do 99 zapisują się więc tak samo jak "
                  "każda inna. Pole numeru w magnetofonie domyka się po drugiej cyfrze, więc ścieżki "
                  "powyżej 99 nie da się wybrać w ogóle; takie tytuły są wypisane jako pominięte, a nie "
                  "po cichu wyrzucone. Tak długa bywa tylko płyta nagrana w LP4."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Nagrywanie albumu na MiniDisc",
        "blocks": [
            {"p": "Nagrywanie na MiniDisc to jedno wspólne okno, do którego prowadzą dwoje drzwi — "
                  "**Nagraj folder na MiniDisc...**, gdy album sam wskazujesz, oraz **Nagraj z folderu "
                  "zgrywania/pobierania na MiniDisc...**, gdy chodzi o to, co zostawiło w folderze "
                  "audio zgrywanie płyty albo pobieranie z Telegrama. Ten rozdział opisuje, co dzieje "
                  "się dalej, którymi drzwiami by się nie weszło: magnetofon zostaje uzbrojony, album odtwarza własny silnik audio xD-Tools, "
                  "program pilnuje go do końca, zapisuje tytuły i układa obie etykiety z okładki albumu."},
            {"note": "**To wymaga przystawki MDRem, a pozycje w menu pojawiają się dopiero po jej "
                     "włączeniu w Okno > Ustawienia...** To przystawka wprowadza magnetofon w nagrywanie "
                     "i to ona stawia znaczniki ścieżek. Bez niej nagrywanie oznacza samodzielne "
                     "wciśnięcie Record na magnetofonie i pozostawienie podziału na ścieżki jego "
                     "własnemu LEVEL-SYNC — xD-Tools nie ma w tym udziału."},
            {"h2": "Przygotowanie"},
            {"ol": [
                "Połącz wyjście **S/PDIF** komputera — optyczne albo koncentryczne — z wejściem cyfrowym "
                "magnetofonu. To ono niesie dźwięk; USB niesie wyłącznie komendy.",
                "Wybierz to wyjście w **Okno > Ustawienia... > Urządzenie wyjścia audio dla MiniDisc** — "
                "patrz rozdział o MDRem. Same pliki źródłowe nie wymagają żadnej konfiguracji.",
                "Włóż czystą albo kasowalną płytę z zamkniętym suwakiem i ustaw tryb nagrywania (SP albo "
                "LP2) **na magnetofonie** — xD-Tools nie potrafi go odczytać ani zmienić.",
                "**Wyłącz LEVEL-SYNC** na magnetofonie. Patrz niżej.",
                "Wyceluj przystawkę w czujnik magnetofonu i zostaw ją tak.",
            ]},
            {"h2": "Format wchodzący do magnetofonu"},
            {"p": "MiniDisc to 44,1 kHz, 16 bitów, stereo, i wejście cyfrowe magnetofonu oczekuje, że "
                  "dokładnie tym zostanie nakarmione. xD-Tools konwertuje każdy plik automatycznie, "
                  "niezależnie od jego własnej częstotliwości czy głębi bitowej — łącznie z pobranym "
                  "plikiem 96 kHz albo 24-bitowym — więc po stronie źródła nie trzeba nic ustawiać. To "
                  "też nie jest zwykłe obcięcie do 16 bitów: resampling idzie tym samym resamplerem, co "
                  "przy wypalaniu CD-R, a dogranie do 16 bitów odbywa się przez dither z kształtowaniem "
                  "szumu — zamiast zostawiać to zaokrąglenie czemuś, co akurat siedzi za kartą dźwiękową."},
            {"h2": "Analogowo, jeśli trzeba"},
            {"p": "Wejścia **analogowe** magnetofonu też działają, a xD-Tools prowadzi nagranie dokładnie "
                  "tak samo — naciska klawisze magnetofonu, co nie zależy od tego, jak dochodzi dźwięk. "
                  "**Jakość jest jednak znacznie słabsza**, i to nieuchronnie: dźwięk wychodzi z karty "
                  "jako analogowy i zostaje ponownie scyfrowany przez magnetofon, więc łapie dwie "
                  "dodatkowe konwersje i cały szum, jaki dorzuci stopień wyjściowy karty — a to wszystko "
                  "przed ATRAC-iem. Jeśli magnetofon ma S/PDIF, używaj S/PDIF."},
            {"p": "Analogowo trzeba też ustawić selektor wejścia magnetofonu na analogowe i poziom "
                  "nagrywania ręcznie — przy wejściu cyfrowym nie ma ani jednego, ani drugiego."},
            {"fig": ("record", "Playlista w kolejności, w jakiej trafi na płytę.")},
            {"h2": "Co widać w oknie"},
            {"p": "Album, wykonawca i rok, którymi płyta zostanie zatytułowana, okładka, którą "
                  "dostanie etykieta, i lista utworów — wszystko do edycji. **To ostatnie miejsce, "
                  "gdzie można to poprawić**: po nagraniu tytuły są już na płycie. Z tego samego "
                  "powodu okładka szukana jest przy otwarciu okna, a nie po skończeniu albumu. W "
                  "chwili startu nagrywania wszystko zamarza."},
            {"p": "Kolumnę **Wykonawca** wypełniaj tylko wtedy, gdy utwory są różnych artystów. Na "
                  "zwykłym albumie zostaje pusta; przy składance to właśnie ona mówi xD-Tools, że "
                  "płyta nią jest."},
            {"h2": "Odsłuch przed nagraniem"},
            {"p": "Zaznacz ścieżkę, a mały pasek transportu pod listą pozwala ją **odtworzyć/zatrzymać** "
                  "przez domyślne wyjście dźwięku komputera — nie przez wyjście do nagrywania powyżej, "
                  "więc działa nawet wtedy, gdy to drugie jest cyfrowym łączem, którego nikt inny nie "
                  "słucha. Suwak pozwala sprawdzić konkretny fragment, a **Wstecz/Dalej** przechodzą "
                  "między utworami bez wracania do listy. To narzędzie do złapania złego pliku albo "
                  "kiepskiej edycji, zanim czterdzieści minut trafi na płytę — nie do odsłuchania całego "
                  "albumu od deski do deski."},
            {"h2": "Co się dzieje"},
            {"ol": [
                "xD-Tools pokazuje playlistę i jej łączny czas, i ostrzega, jeśli nie zmieści się na "
                "80-minutowej płycie w SP.",
                "Dekoduje, resampluje i ditheruje całą płytę z góry — patrz wyżej — stosując ustawienie "
                "**Wzmocnienie nagrywania**, żeby zostawić magnetofonowi zapas.",
                "Każe magnetofonowi zacząć nagrywanie, po czym **prosi o potwierdzenie, że magnetofon "
                "naprawdę jest w pauzie nagrywania**. Nie może tego sprawdzić, a pomyłka oznacza "
                "odegranie całego albumu do magnetofonu, który nie nagrywa, i odkrycie tego czterdzieści "
                "minut później.",
                "Zwalnia pauzę, a chwilę później rusza z odtwarzaniem — w tej kolejności, żeby magnetofon "
                "już pracował, gdy przyjdzie pierwszy dźwięk.",
                "Nagrywanie trwa. Widać, która ścieżka idzie i ile zostało. Zatrzymanie zatrzymuje oba "
                "końce.",
                "Po zakończeniu albumu program proponuje zapisanie tytułów, wziętych z samej playlisty.",
                "Na koniec album, wykonawca, rok i lista utworów stają się metadanymi projektu, okładka "
                "zostaje wyszukana, a **strony projektu układają się same**, każda na szablonie, który "
                "już ma.",
            ]},
            {"warn": "Ten ostatni krok **zastępuje wszystko na obu stronach**. Po nagraniu nie pyta — "
                     "właśnie przeszedłeś przez kilka potwierdzeń i przesiedziałeś album w czasie "
                     "rzeczywistym, a jeszcze jedno pytanie byłoby szumem."},
            {"h2": "Znaczniki ścieżek: rzecz najważniejsza"},
            {"p": "Odtwarzacz CD mówi magnetofonowi, gdzie są granice ścieżek, w podkodzie S/PDIF. "
                  "**Komputer tego nie robi.** Zostawiony sam sobie magnetofon opiera się na LEVEL-SYNC: "
                  "zaczyna nową ścieżkę, gdy dźwięk zamilknie i wróci."},
            {"p": "To zawodzi na każdym albumie, w którym jeden utwór przechodzi w drugi. Dwa utwory bez "
                  "przerwy między nimi nagrają się jako jedna długa ścieżka i żadna późniejsza edycja "
                  "tego nie naprawi po dobroci."},
            {"p": "Dlatego xD-Tools sam wysyła znacznik dokładnie w tej próbce, w której własny odtwarzacz "
                  "przechodzi z jednej ścieżki w drugą — to pole **Znaczniki ścieżek przez przystawkę** "
                  "i powinno zostać zaznaczone."},
            {"warn": "**Wyłącz wtedy LEVEL-SYNC na magnetofonie.** Jedno i drugie naraz oznacza tę samą "
                     "granicę dwa razy, o ułamek sekundy obok siebie, i zostawia między nimi szczątkową "
                     "ścieżkę. One się kłócą, a nie uzupełniają."},
            {"h2": "Tryb nagrywania i długość"},
            {"p": "MD mieści 80 minut w SP. xD-Tools ostrzega, gdy playlista jest dłuższa, ale może "
                  "wyłącznie ostrzec — LP2 i LP4 trzeba ustawić na samym magnetofonie i nie da się "
                  "odczytać, w którym trybie jest."},
            {"h2": "Album, który nie mieści się na jednej płycie"},
            {"p": "Podwójny album nie zmieści się na MiniDysku, a MiniDysku nie da się odwrócić tak jak "
                  "kasety. **Nagraj na kilka płyt** nagrywa go płyta po płycie: jedna płyta, jej tytuły, "
                  "wysunięcie, kolejny czysty krążek i tak dalej."},
            {"p": "Po zaznaczeniu lista utworów dostaje kolumnę **Płyta** pokazującą, gdzie album jest "
                  "cięty, a pod nią linijkę z zapełnieniem każdej płyty. Decyduje o tym pole **Jedna "
                  "płyta mieści** - 80 minut w SP, 160 w LP2. xD-Tools nie potrafi odczytać trybu "
                  "magnetofonu, więc tę liczbę podajesz Ty."},
            {"ol": [
                "Każda płyta jest nagrywana dokładnie tak jak pojedyncza: uzbrojenie, potwierdzenie, "
                "odtwarzanie, znaczniki ścieżek.",
                "**Dwie sekundy po ostatnim utworze tej płyty tytuły idą same** - bez pytania, bez "
                "przycisku. Nikt nie siedzi przy komputerze przez czterdzieści minut albumu, a MiniDysk "
                "trzyma zmienione tytuły w pamięci tylko do wysunięcia płyty.",
                "Płyta jest wysuwana, a xD-Tools prosi o kolejny czysty krążek.",
                "Ostatnia płyta kończy się tak samo i na tym przebieg się zamyka.",
            ]},
            {"note": "Każda płyta dostaje nazwę albumu z dopiskiem **[1/2]**, **[2/2]**. Dwie płyty tego "
                     "samego albumu opisane identycznie to dwie płyty nie do odróżnienia na półce. "
                     "Ścieżki na każdej numerowane są od jedynki - i tak numeruje je sam magnetofon."},
            {"warn": "Podgląd, który normalnie pokazuje okno wysyłania tytułów, jest tu pominięty - nie "
                     "ma go komu przeczytać. Dlatego każdy tytuł i każdy znak, którego magnetofon nie "
                     "potrafi wyświetlić, widać w tym oknie **zanim** zabrzmi pierwsza nuta."},
            {"h2": "Gdzie album jest cięty i w jakiej kolejności"},
            {"p": "xD-Tools układa playlistę we własnej kolejności albumu już przy otwarciu okna: "
                  "najpierw numer płyty, potem numer ścieżki, jedno i drugie prosto z plików. Komplet "
                  "dwupłytowy trzymany jako jeden folder przychodzi przeplatany, bo obie płyty numerują "
                  "ścieżki od jedynki — to właśnie prostuje, zanim cokolwiek zacznie grać."},
            {"p": "Jeżeli pliki mówią, ile jest płyt, podziały stają tam, gdzie one wskazują, a opcja "
                  "zaznacza się sama. W przeciwnym razie album dzieli się możliwie równo, na najmniejszą "
                  "liczbę płyt, która wystarczy."},
            {"ul": [
                "**Przesuń w górę** / **Przesuń w dół** zmieniają kolejność nagrywania.",
                "**Zacznij tu nową płytę** czyni z zaznaczonej ścieżki pierwszą na nowej płycie; "
                "naciśnięty ponownie na tej samej ścieżce - zabiera ten podział.",
                "**Podziel automatycznie** odrzuca ręcznie ustawione podziały i wylicza je od nowa.",
            ]},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Zgrywanie płyty CD",
        "blocks": [
            {"p": "**Źródło > Zgraj płytę audio CD...** kopiuje płytę audio CD do plików. Odczytuje "
                  "płytę, ustala, co to za album, zgrywa każdą ścieżkę - i na tym kończy: proponuje "
                  "wprowadzić tytuł albumu i listę utworów do projektu, mówi, gdzie trafiły pliki, i to "
                  "wszystko."},
            {"p": "Nagranie tych plików to osobny krok, który uruchamiasz sam: **Nagrywanie > Nagraj z "
                  "folderu zgrywania/pobierania na {medium}...** - zwykłe okno nagrywania opisane w "
                  "poprzednim rozdziale, z tym samym uzbrajaniem, tymi samymi znacznikami ścieżek i tym "
                  "samym nadawaniem tytułów. Kiedyś było to jedno nieprzerwane działanie, co znaczyło, "
                  "że kopię można było zdobyć tylko rozpoczynając nagrywanie; sama kopia jest coś warta, "
                  "a płyta jest w napędzie teraz - niezależnie od tego, czy magnetofon jest wolny."},
            {"note": "**Zgrywanie nie potrzebuje ani przystawki MDRem, ani konkretnego rodzaju "
                     "projektu**, dlatego siedzi w menu Źródło i nic w nim nie znika ani nie zmienia "
                     "nazwy wraz z nośnikiem. Przystawki potrzebuje dopiero nagrywanie, które może "
                     "nastąpić później, i tylko w projekcie MiniDisc."},
            {"h2": "Dlaczego najpierw kopia"},
            {"p": "Napęd potrafi odtwarzać płytę CD bezpośrednio, a pozwolenie mu na to byłoby "
                  "prostsze. Wtedy jednak rysa napotkana w 31. minucie ląduje wprost na MiniDysku, bez "
                  "żadnego zabezpieczenia - a nagrania na MiniDisc nie da się potem załatać."},
            {"p": "Wcześniejsza kopia przenosi każdy błąd odczytu w miejsce, gdzie kosztuje tylko "
                  "ponowną próbę. xD-Tools używa do tego **cdparanoi**, zbudowanej właśnie po to, by "
                  "męczyć uszkodzoną płytę aż do poprawnego odczytu, oraz **flac** do zapisu wyniku. "
                  "Oba narzędzia są dołączone do xD-Tools; nie trzeba niczego instalować."},
            {"fig": ("cd-rip", "Płyta odczytana, rozpoznana i gotowa do zgrania.")},
            {"h2": "Krok po kroku"},
            {"ol": [
                "Włóż płytę do napędu i wybierz napęd z listy. **Odśwież** szuka ponownie, jeśli "
                "podłączyłeś napęd już po otwarciu okna.",
                "Naciśnij **Odczytaj płytę**. xD-Tools czyta spis treści i wyszukuje płytę w "
                "MusicBrainz, który rozpoznaje ją po długościach ścieżek - sama płyta CD nie zawiera "
                "żadnego tekstu.",
                "Sprawdź, co wróciło. Jeśli pasuje kilka wydań, wybierz właściwe z pola **Wydanie**; "
                "tytuły ścieżek i okładka zmienią się razem z nim.",
                "Popraw to, co się nie zgadza. Tytuły są edytowalne i to one trafiają do plików, a "
                "później na MiniDisc.",
                "Naciśnij **Zgraj**. Po zakończeniu kopiowania xD-Tools nazywa folder, do którego "
                "trafiły pliki, i pyta, czy wprowadzić tytuł albumu i listę utworów do projektu.",
            ]},
            {"note": "Płyta, której nie ma w MusicBrainz - każda nagrana samodzielnie i sporo mniej "
                     "znanych wydań - wraca po prostu z numerowanymi tytułami zastępczymi do "
                     "nadpisania. Poza tym nic się nie zmienia."},
            {"h2": "Ile to trwa"},
            {"p": "Licz się z **około piętnastoma minutami na cały album**, czyli mniej więcej trzy "
                  "razy szybciej niż odtwarzanie. To cdparanoia pracująca starannie i jest to cena "
                  "korekcji błędów, dla której w ogóle warto było robić kopię. Samo nagrywanie trwa "
                  "potem tyle, ile album, bo odbywa się w czasie rzeczywistym."},
            {"h2": "Kiedy płyta jest składanką"},
            {"p": "Składanka to nie album, a traktowanie jej jak albumu psuje się w widoczny sposób: "
                  "płyta dostaje nazwę od tego utworu, który akurat był pierwszy, J-card przypisuje "
                  "dwanaście utworów jednemu wykonawcy, a wyszukiwanie okładki zwraca okładkę zupełnie "
                  "innej płyty."},
            {"p": "Dlatego xD-Tools to sprawdza. Jeśli większości ścieżek nie da się przypisać jednemu "
                  "wykonawcy, podpisuje płytę jako **Various Artists**, nazywa ją `Mixtape` (chyba że "
                  "wydanie ma własną nazwę), wypisuje wykonawcę przy każdym utworze na J-card i "
                  "**rysuje okładkę na podstawie listy utworów** zamiast jej szukać."},
            {"p": "Wypełnij kolumnę **Wykonawca** samodzielnie, gdy wiesz, że płyta jest składanką, a "
                  "MusicBrainz tego nie podał - to właśnie ta kolumna jest sprawdzana."},
            {"note": "Album z gościnnym udziałem w jednym utworze **nie jest** składanką i nie jest tak "
                     "traktowany. Sprawdzane jest to, czy większość utworów należy do tego samego "
                     "wykonawcy, a nie to, czy podpisy się w ogóle różnią."},
            {"p": "To samo dotyczy folderu nagrywanego bezpośrednio (rozdział „Nagrywanie z folderu "
                  "plików”): folder złożony z niepowiązanych utworów jest rozpoznawany tak samo i z "
                  "tym samym skutkiem."},
            {"h2": "Gdzie trafiają zgrane pliki"},
            {"p": "Domyślnie do **Dokumenty\\XDProjects\\Audio**, po jednym folderze na album - tego "
                  "samego, do którego trafiają pliki pobrane botem Telegrama (własny rozdział), bo oba "
                  "to półprodukt do nagrania, a nie kolekcja muzyki. Jeśli folderu nie ma, zostanie "
                  "utworzony, a **Okno > Ustawienia... > Folder zgrywania CD** pozwala wskazać inne "
                  "miejsce."},
            {"p": "Zgrane pliki **nigdy nie są kasowane automatycznie** — ani przez to okno, ani przez "
                  "nic innego w xD-Tools — nie po zakończeniu nagrywania, nie po to, by zrobić miejsce "
                  "na kolejne zgranie. To, co się tam nazbiera, sprzątasz sam, kiedy i jak chcesz."},
            {"h2": "Wydanie na kilku płytach CD"},
            {"p": "**Zgraj kilka płyt jako jeden album** przenosi komplet jako jeden album, a nie jako "
                  "dwa niezwiązane. Każda płyta jest osobno odczytywana, identyfikowana i zgrywana, po "
                  "czym xD-Tools prosi o następną."},
            {"ul": [
                "Wszystkie trafiają do **jednego folderu** - tego, który utworzyła pierwsza płyta. "
                "Kolejna bywa identyfikowana pod własnym tytułem - \"... [Disc 2]\" - a folder na "
                "płytę to byłyby dwa albumy.",
                "Album, wykonawca i rok zostają te z pierwszej płyty. **Tytuły** są własne każdej płyty "
                "i po to właśnie jest to sprawdzanie.",
                "Każdy plik dostaje tag z numerem swojej płyty i numer ten w nazwie. To dzięki temu "
                "wszystko dalej - playlista, nagrywanie, wypalanie - potrafi ułożyć komplet po jego "
                "własnemu.",
                "Kiedy przestaniesz dokładać płyty, następujące po tym nagranie obejmuje od razu cały "
                "komplet.",
            ]},
            {"note": "Możesz zakończyć po dowolnej płycie: pytanie proponuje kontynuować albo "
                     "zachować to, co zostało już zgrane."},
        ],
    },
    {
        "title": "Wypalanie płyty audio CD",
        "blocks": [
            {"p": "W projekcie CD **Nagrywanie > Nagraj folder na CD...** — ta sama pozycja, którą "
                  "rozdział „Nagrywanie z folderu plików” opisuje dla MiniDisc i kasety — zapisuje "
                  "zamiast tego prawdziwą płytę audio CD-R w standardzie Red Book: taką, jaką odtworzy "
                  "każdy odtwarzacz CD, z folderu plików, które już masz. Podczerwień nie bierze w tym "
                  "udziału: to robota napędu, więc ta pozycja zostaje dostępna nawet przy wyłączonym "
                  "MDRem."},
            {"fig": ("burn", "Okno wypalania: co zostanie zapisane i jak będzie się nazywać.")},
            {"h2": "Co pokazuje okno"},
            {"p": "Nazwę albumu, wykonawcę i rok, edytowalny tytuł i wykonawcę przy każdej ścieżce oraz "
                  "okładkę, którą można kliknąć i podmienić — to samo okno co przy nagrywaniu i ta sama "
                  "zasada: **to, co jest na ekranie w chwili naciśnięcia Wypal, trafia na płytę**, "
                  "zarówno jako CD-Text, jak i do projektu, z którego zaprojektujesz etykietę."},
            {"p": "Linia pod listą podaje długość albumu wobec pojemności płyty. Kolumna **Status** to "
                  "ta część, którą warto przeczytać, zanim cokolwiek naciśniesz."},
            {"p": "Zaznacz ścieżkę, a pasek transportu pod listą odtworzy ją przez domyślne wyjście "
                  "dźwięku komputera, z suwakiem i przyciskami Wstecz/Dalej — ten sam odsłuch, co w "
                  "oknach nagrywania na MiniDisc i kasetę. Warto go użyć, zanim płyta, której nie da "
                  "się już poprawić, zostanie zapisana."},
            {"h2": "Dlaczego ścieżka może zostać odrzucona"},
            {"p": "Płyta CD przyjmuje wyłącznie dźwięk 44,1 kHz, 16-bitowy, stereo. Dwie reguły Red "
                  "Booka mogą zatrzymać wypalanie i okno mówi o nich przy konkretnej ścieżce, zamiast "
                  "pozwolić Ci odkryć to przy odtwarzaniu:"},
            {"ul": [
                "ścieżka krótsza niż **cztery sekundy**, której część odtwarzaczy nie zagra;",
                "więcej niż **99 ścieżek** albo album dłuższy niż płyta.",
            ]},
            {"note": "Plik o innej częstotliwości to nie jest odmowa. Pobrany album 48 kHz / 24 bity — "
                     "czyli to, czym zwykle jest — dostaje wpis „zostanie przekonwertowane na 44100 Hz / "
                     "16 bitów” i po drodze na płytę zostaje przeresamplowany i zditherowany przez "
                     "własny silnik audio xD-Tools. Konwersja idzie do folderu roboczego; Twoje własne "
                     "pliki nie są ruszane."},
            {"h2": "Tytuły na płycie: CD-Text"},
            {"p": "Nazwa albumu i nazwy ścieżek są zapisywane na płycie jako CD-Text, który pokażą "
                  "odtwarzacze go obsługujące. Niesie czyste ASCII, więc polskie znaki tracą ogonki tak "
                  "samo jak w tytułach na MiniDiscu — a to, co nie ma żadnego odpowiednika, okno wypisuje "
                  "**przed** wypaleniem, zamiast po cichu pominąć."},
            {"h2": "Najpierw symulacja, jeśli chcesz"},
            {"p": "**Tylko symulacja** przechodzi całą procedurę z wyłączonym laserem. Trwa tyle co "
                  "prawdziwe wypalanie i sprawdza napęd, prędkość oraz pliki, nie zużywając płyty. Warto "
                  "zrobić to raz na nowym napędzie."},
            {"warn": "Płyty CD-R nie da się nadpisać. Gdy zapis ruszy, płyta będzie albo gotowa, albo "
                     "zmarnowana — dlatego okno pyta przed startem i pyta drugi raz, jeśli naciśniesz "
                     "Zatrzymaj przy pracującym laserze. Przerwanie na wcześniejszym etapie "
                     "„Przygotowywanie dźwięku” nie kosztuje nic."},
            {"h2": "Etykieta, potem"},
            {"p": "Po wypaleniu dane albumu są proponowane otwartemu projektowi, jeśli jest to projekt "
                  "CD. Zgódź się, a automatyczny układ z panelu Narzędzia ma wszystko, czego potrzebuje: "
                  "okładkę, wykonawcę, rok i listę utworów."},
            {"fig": ("cd-label", "Etykieta płyty: rozjaśniona okładka na całym pierścieniu, wycięty "
                                 "otwór na trzpień i znak Digital Audio u dołu.")},
            {"fig": ("cd-insert", "Składana wkładka do slima: okładka na prawym panelu, spis utworów na "
                                  "lewym. Po złożeniu na pół lewa połowa widoczna jest przez tył "
                                  "pudełka.")},
            {"h2": "Czego potrzebujesz"},
            {"ul": [
                "Nagrywarki CD. Jest wykrywana przez zapytanie cdrecorda, nie zgadywana — jeśli pole "
                "**Nagrywarka** jest puste, sprawdź podłączenie napędu i naciśnij **Odśwież**.",
                "Czystej płyty CD-R. Płyta, na której już coś jest, nie przyjmie nowego zapisu.",
                "Niczego więcej: cdrecord jest dołączony w wersji na Windows, a resampling to własny "
                "silnik xD-Tools.",
            ]},
            {"h2": "Album, który nie mieści się na jednej płycie"},
            {"p": "**Wypal na kilka płyt** zapisuje długi album na tylu krążkach CD-R, ilu potrzeba. "
                  "Zależy to od pola **Jedna płyta mieści**: 80 minut na zwykłym krążku, 74 na "
                  "starszym."},
            {"p": "Lista utworów dostaje kolumnę **Płyta** pokazującą miejsce cięcia, a podsumowanie "
                  "podaje długość każdej płyty osobno. Każda mierzona jest względem krążka, na który "
                  "pójdzie - to, że album się nie mieści, jest przecież założeniem - więc przycisk Wypal "
                  "pozostaje wyłączony, dopóki nie zmieszczą się wszystkie."},
            {"ol": [
                "Każda płyta jest nagrywana i wysuwana niezależnie od pola **Wysuń po zakończeniu**: "
                "taca musi się otworzyć, żeby włożyć następny krążek.",
                "xD-Tools prosi o ten krążek i wypala kolejną płytę.",
                "Przy każdym z tych pytań można zakończyć; płyty już nagrane są gotowe.",
            ]},
            {"note": "CD-Text każdej płyty niesie nazwę albumu z dopiskiem **[1/2]**, **[2/2]** - z tego "
                     "samego powodu co tytuły na MiniDysku."},
            {"p": "Miejsce cięcia bierze się z plików, kiedy te je znają - zgrany komplet niesie numery "
                  "swoich płyt i są one respektowane, a nie zastępowane wyrównywaniem po czasie. Są tu "
                  "też te same cztery przyciski co w oknie nagrywania: **Przesuń w górę**, **Przesuń w "
                  "dół**, **Zacznij tu nową płytę** i **Podziel automatycznie**."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Nagrywanie z folderu",
        "blocks": [
            {"p": "**Nagrywanie > Nagraj folder na {medium}...** nagrywa album, który masz już na "
                  "dysku — na MiniDisc, na kasetę, na CD-R, zależnie od tego, do czego jest otwarty "
                  "projekt. Wskaż folder, w którym leży, a xD-Tools odczyta znaczniki wprost z plików i "
                  "przekaże sterowanie do okna nagrywania, które już znasz z poprzednich rozdziałów — to "
                  "samo uzbrajanie, te same znaczniki utworów, to samo nadawanie tytułów (albo, w "
                  "projekcie CD, od razu wypalanie)."},
            {"note": "**Nagrywanie w projekcie MiniDisc wymaga przystawki MDRem** — pozycja pojawia się "
                     "dopiero po jej włączeniu. Samo wczytanie folderu jej nie potrzebuje; kaseta i "
                     "CD-R nie potrzebują jej wcale, ani tu, ani nigdzie indziej."},
            {"fig": ("folder-record", "Odczytany folder i to, co xD-Tools wyczytał wprost ze znaczników "
                                      "plików.")},
            {"h2": "Krok po kroku"},
            {"ol": [
                "Naciśnij **Przeglądaj...** i wskaż folder z albumem. Jego pliki są odczytywane od "
                "razu — wybór folderu jest decyzją, więc nie ma czego dodatkowo potwierdzać. FLAC i "
                "WAV zostaną rozpoznane; co nie jest jednym z nich — okładki, plik cue, log — jest "
                "pomijane.",
                "Sprawdź kolejność. Bierze się z nazw plików, porównywanych tak, że `10` idzie po "
                "`9`, a nie po `1`. Jeśli jest zła, poprawiać trzeba nazwy plików.",
                "Sprawdź album i wykonawcę. Na początek są zgadywane z nazwy samego folderu, a to, co "
                "jest w znacznikach plików, zastępuje ten domysł, gdy tylko ścieżki zostaną odczytane. "
                "Jeżeli jedno i drugie jest nie tak, po prostu wpisz swoje.",
                "Obejrzyj, co wyszło: tytuły odczytane wprost ze znaczników plików oraz okładkę — "
                "najpierw szukaną w sieci, a gdy nic sensownego nie znajdzie, braną z wnętrza "
                "samego pliku FLAC.",
                "Naciśnij **Nagraj**.",
            ]},
            {"h2": "Skąd biorą się tytuły"},
            {"p": "Wprost ze znaczników plików — tym samym czytnikiem, którym nagrywanie potem je "
                  "dekoduje, więc nic tutaj nie może rozjechać się z tym, co realnie zagra. Plik bez "
                  "znacznika tytułu zostanie nagrany pod nazwą swojego pliku. To uczciwa odpowiedź i "
                  "zwykle wystarczająca."},
            {"p": "Album i wykonawca widoczni w tym oknie trafią na płytę i na etykietę, więc poprawkę "
                  "warto zrobić przed naciśnięciem przycisku. Do Twoich plików nic nigdy nie jest "
                  "zapisywane."},
            {"h2": "Podfolder na płytę"},
            {"p": "Folder, w którym leżą utwory, *jest* albumem, a jego podfoldery są pomijane — "
                  "katalog ze skanami czy bonusami nie dołącza do listy. Dopiero gdy w samym folderze "
                  "nie ma żadnego dźwięku, xD-Tools zagląda głębiej — i dzięki temu album dwupłytowy "
                  "trzymany jako `CD1` i `CD2` wychodzi w kolejności płyt."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Nagrywanie kasety",
        "blocks": [
            {"p": "**Nagraj folder na kasetę...** i **Nagraj z folderu zgrywania/pobierania na "
                  "kasetę...** — te same drzwi, co w rozdziale o MiniDysku — w projekcie "
                  "kasetowym prowadzą tutaj i nagrywają album na kasetę magnetofonową, strona po "
                  "stronie. To wyjątek wśród sposobów nagrywania — i wyjątek, który przesądza o "
                  "wszystkim: **magnetofon obsługujesz ty**. Do magnetofonu nie ma adaptera ani kabla, "
                  "który wciskałby klawisze, więc xD-Tools odtwarza właściwe utwory we właściwym "
                  "momencie i mówi wprost, co i kiedy nacisnąć."},
            {"note": "Do tego **nie jest potrzebny żaden adapter MDRem** — wystarczy urządzenie "
                     "wybrane w Okno > Ustawienia... > Urządzenie wyjścia audio dla kasety (własne, "
                     "niezależne od tego dla MiniDisc). Pozycje są widoczne zawsze, gdy otwarty projekt "
                     "jest kasetowy, niezależnie od tego, czy adapter jest włączony."},
            {"fig": ("tape-record", "Podział, kaseta, pod którą go policzono, i czekająca instrukcja.")},
            {"h2": "Wybór kasety"},
            {"p": "Podana długość dotyczy obu stron razem: C60 to trzydzieści minut na stronę, nie "
                  "sześćdziesiąt. Wybierz w polu **Kaseta** tę, którą naprawdę masz — album dzieli się "
                  "od razu: kolumna Strona na liście utworów i podsumowanie pod nią zmieniają się "
                  "natychmiast."},
            {"p": "Po otwarciu okna zaznaczona jest najkrótsza kaseta, na której album się mieści. To "
                  "podpowiedź o albumie, a nie o twojej półce: zmień ją na to, co masz w pudełku."},
            {"h2": "Gdzie przewracasz taśmę"},
            {"p": "xD-Tools nigdy nie zmienia kolejności utworów. Do wyboru jest tylko to, po którym "
                  "utworze wypada przerwa, i sprawdzane są wszystkie możliwości: wygrywa ta, po której "
                  "obie strony wychodzą najbardziej równe — spośród tych, które się mieszczą. "
                  "Wypełnienie strony A po brzegi i zostawienie połowy strony B niczego nie oszczędza — "
                  "taśma jest tak samo długa w obu przypadkach."},
            {"p": "Jeśli nie mieści się nic, i tak brany jest podział z najmniejszym przekroczeniem, a "
                  "okno mówi o ile. To, czy ostatni utwór wejdzie w wybieg taśmy, jest twoją decyzją — "
                  "dokładnie tak jak przy albumie dłuższym niż osiemdziesiąt minut MiniDisca."},
            {"warn": "Utworów bez czasu trwania nie da się zważyć, więc album dzielony jest po połowie "
                     "według liczby utworów, o czym okno informuje. Sprawdź to względem taśmy, zanim "
                     "zaczniesz."},
            {"h2": "Dziesięć sekund ciszy"},
            {"p": "Każda strona kasety zaczyna się rozbiegówką — kilkoma centymetrami zwykłego "
                  "tworzywa, doklejonego po to, by to ono znosiło nawijanie na szpulę. Nie jest "
                  "magnetyczna, więc nic, co się na nią nagra, nie przetrwa. Dlatego xD-Tools nagrywa "
                  "na początku każdej strony **dziesięć sekund ciszy**, zanim ruszy muzyka — i te "
                  "dziesięć sekund odlicza od tego, co strona mieści."},
            {"h2": "Krok po kroku, dla każdej strony"},
            {"ol": [
                "Sprawdź album, wykonawcę, rok i okładkę — to z nich zostaną wydrukowane etykiety, i "
                "zostają zamrożone z chwilą rozpoczęcia nagrywania.",
                "Włóż kasetę przewiniętą na początek strony. Naciśnij razem **RECORD i PAUSE** — pauzę "
                "nagrywania, magnetofon uzbrojony, ale jeszcze nieruszający się — ustaw jego wejście na "
                "linię, którą karmi go xD-Tools, i ustaw poziom.",
                "Naciśnij przycisk pod listą utworów. xD-Tools dekoduje z góry całą stronę, z linijką "
                "statusu pokazującą, że pracuje, a nie że się zawiesił.",
                "Okno mówi, żeby **zwolnić teraz Pauzę** — magnetofon powinien zacząć się kręcić. To "
                "kliknięcie jest jedynym potwierdzeniem, że naprawdę ruszył — nic tutaj tego nie widzi "
                "— i to też moment, od którego liczy się dziesięć sekund ciszy poniżej, więc szybkie "
                "zwolnienie Pauzy to właśnie to, co utrzymuje ciszę i rozbiegówkę w zgodzie.",
                "Odlicza dziesięć sekund ciszy, w czasie których przechodzi rozbiegówka, a potem gra "
                "strona. Własny odtwarzacz xD-Tools zatrzymuje się dokładnie w chwili, gdy kończy się "
                "ostatni utwór tej strony, zamiast być złapanym po fakcie — dzięki temu pierwsza "
                "sekunda kolejnej strony nie trafia na koniec tej.",
                "Zatrzymaj magnetofon, wyjmij kasetę i odwróć ją, naciśnij ponownie **RECORD i PAUSE** "
                "i naciśnij przycisk dla strony B — to samo okno z prośbą o zwolnienie Pauzy czeka i "
                "tam.",
            ]},
            {"tip": "**Zatrzymaj** zatrzymuje własne odtwarzanie xD-Tools i mówi o tym — magnetofonu "
                    "zatrzymać nie może, a ten spokojnie nagrywałby dalej ciszę. To jedyna rzecz, którą "
                    "możesz zrobić tylko ty."},
            {"h2": "Odsłuch przed nagraniem"},
            {"p": "Ten sam odsłuch, co w oknach MiniDisc i wypalania CD, siedzi pod listą utworów też "
                  "tutaj: zaznacz ścieżkę, **odtwórz/zatrzymaj** ją przez domyślne wyjście dźwięku "
                  "komputera, przeciągnij suwak, żeby sprawdzić fragment, **Wstecz/Dalej**, żeby "
                  "przejść przez album. Strony kasety nie da się potem poprawić tak samo, jak nagrania "
                  "na MiniDisc — warto więc jej posłuchać wcześniej."},
            {"h2": "Droga dźwięku"},
            {"p": "Z komputera na wejścia liniowe magnetofonu, zwyczajnie analogowo. Nic w tym oknie "
                  "nie zależy od tego, jak dźwięk tam dociera: przełącznik wejść, poziom nagrywania i "
                  "redukcja szumów są twoje do ustawienia, a xD-Tools o żadnym z nich nie wie i nie "
                  "pyta."},
            {"p": "Poziom ustaw na najgłośniejszym fragmencie albumu, a nie na pierwszych dziesięciu "
                  "sekundach. Taśma zniekształca stopniowo, a nie nagle, więc odrobinę za gorąco to "
                  "cieplejsze nagranie, a mocno za gorąco to zamulone."},
            {"h2": "Potem"},
            {"p": "Gdy obie strony są nagrane, album przechodzi do otwartego projektu i rozmieszczane "
                  "są jego trzy strony — wkładka i etykieta na każdą stronę kasety, podzielone dokładnie "
                  "tam, gdzie podzieliło się nagranie. Wybrana kaseta zapisuje się w projekcie, więc "
                  "etykiety i nagranie nie mogą się różnić co do tego, gdzie zaczyna się strona B."},
            {"fig": ("tape-jcard", "Wkładka: okładka, grzbiet i spis utworów na zakładce, pod "
                                   "nagłówkiem każdej strony.")},
            {"p": "Pozostałe dwie strony to **etykiety na kasetę**, wycinane z okrągłym otworem na "
                  "każdą szpulę — wchodzą w nie trzpienie magnetofonu, więc etykieta bez nich zakleiłaby "
                  "napęd. Okładka idzie na całą naklejkę, rozjaśniona tak, by tekst na niej pozostał "
                  "czytelny, a otwory są przez nią wybite. Litera strony stoi między nimi, a utwory tej "
                  "strony biegną wzdłuż dołu, numerowane od jedynki — tak jak liczy je magnetofon."},
            {"fig": ("tape-label", "Etykieta kasety: okładka, otwory, w których obracają się szpule, "
                                   "i utwory tej strony.")},
            {"p": "W **Plik > Drukuj...** obie etykiety idą na jedną kartkę — to ta sama naklejka "
                  "wydrukowana dwa razy, wycinana za jednym razem i naklejana na dwie strony tej samej "
                  "kasety — a wkładka, cztery razy większa, na następną."},
            {"fig": ("tape-print", "Obie naklejki na jednej kartce, wkładka na kolejnej.")},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Kasowanie płyty",
        "blocks": [
            {"p": "**Skasuj MiniDisc...**, przycisk w oknie nagrywania na MiniDisc, a nie osobna "
                  "pozycja menu, czyści płytę w magnetofonie — skasowanie niewłaściwej płyty najczęściej "
                  "wychodzi na jaw tuż przed nagraniem na nią, więc tam właśnie ten przycisk teraz "
                  "mieszka."},
            {"warn": "Nie da się tego cofnąć, a xD-Tools nie widzi wyniku. Upewnij się, że w "
                     "magnetofonie jest ta płyta, o którą Ci chodzi, i że jej suwak zabezpieczający "
                     "jest zamknięty."},
            {"h2": "Stała sekwencja, za jednym potwierdzeniem"},
            {"p": "**Skasuj płytę** wysyła przez podczerwień **Stop, Erase, Enter, Enter, Eject**, "
                  "każdy klawisz z ćwierćsekundowym odstępem od poprzedniego, żeby magnetofon zdążył "
                  "faktycznie zareagować, zanim przyjdzie następny — bez dalszych pytań po Twoim "
                  "jednym potwierdzeniu. Ta dokładna sekwencja — dwa Entery, a potem bezwarunkowe "
                  "Eject — jest tym, co potwierdzono jako działające na jednym rzeczywistym "
                  "magnetofonie; xD-Tools nie potrafi odczytać wyświetlacza, żeby sprawdzić, ilu chce "
                  "inny model, więc jeśli Twój potrzebuje czegoś innego, skasuj płytę bezpośrednio z "
                  "jego panelu."},
            {"fig": ("erase", "Jedno potwierdzenie, a potem sekwencja leci sama.")},
            {"note": "Tak jak przy tytułach, skasowanie żyje w pamięci magnetofonu do chwili "
                     "wysunięcia płyty — dlatego Eject jest ostatnim klawiszem sekwencji, a nie "
                     "osobnym krokiem do zapamiętania."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Eksperymentalne: pobieranie z bota Telegrama",
        "blocks": [
            {"warn": "Wszystko w tym rozdziale jest **eksperymentalne** i ukryte, dopóki samemu się o to "
                     "nie poprosi. Działa, ale jest nowsze i mniej sprawdzone niż reszta programu, a sposób "
                     "podania może się jeszcze zmienić."},
            {"p": "xD-Tools potrafi rozmawiać z botem Telegrama, **którego prowadzisz sam**, pobrać "
                  "przysłane pliki i przekazać wynik do Nagrywania z folderu — dzięki czemu pobranie staje "
                  "się nagraną i zatytułowaną płytą bez wychodzenia z programu."},
            {"warn": "To jest do bota, którego kontrolujesz. Pobieranie albumów z publicznego bota, który "
                     "rozpowszechnia muzykę bez zgody uprawnionych, nie jest tym, do czego to służy — a "
                     "posiadanie płyty CD tego nie legalizuje: to obejmuje kopiowanie własnej płyty, a nie "
                     "wzięcie kopii od obcej osoby."},
            {"h2": "Włączanie"},
            {"p": "W **Okno > Ustawienia > Ogólne** jest pole **Pokaż funkcje eksperymentalne**. To "
                  "ono sprawia, że pozycja bota pojawia się w menu **Źródło**; dopóki jest wyłączone, "
                  "nic za nim nie działa."},
            {"fig": ("settings-telegram", "Okno > Ustawienia, grupa Telegram. Konto bota mieszka razem "
                                          "z resztą ustawień, a nie w osobnym oknie."),},
            {"p": "**Okno > Ustawienia > Telegram** to miejsce bota. **Nazwa użytkownika bota** to bot, "
                  "z którym chcesz rozmawiać, `@coś`. Pobrane pliki trafiają do **Ogólne > Folder "
                  "zgrywania CD** — tego samego folderu, którego używa zgrywanie CD, bo oba są "
                  "półproduktem do nagrania, a nie kolekcją muzyki; osobnego ustawienia folderu dla "
                  "Telegrama już nie ma."},
            {"note": "Nie ma tu żadnego API ID ani API Hash do wpisania. xD-Tools nosi własne, więc "
                     "jedynym krokiem jest zalogowanie. Gdyby jakaś wersja programu została zbudowana bez "
                     "nich, powie to wprost, zamiast nie umieć się połączyć."},
            {"h2": "Logowanie"},
            {"p": "xD-Tools loguje się na **Twoje własne konto Telegrama**, nie jako bot. Nie jest to "
                  "kwestia gustu: Bot API Telegrama zabrania botowi pisać do innego bota, więc jedynym "
                  "sposobem rozmawiania z własnym botem tak jak człowiek jest być człowiekiem."},
            {"fig": ("telegram-login", "Logowanie do Telegrama. Numer telefonu, potem kod przysłany przez "
                                       "Telegram, potem hasło, jeśli używasz weryfikacji dwuetapowej."),},
            {"p": "**Zaloguj się do Telegrama...** pyta o numer telefonu, potem o kod, który Telegram przysyła "
                  "na Twoje pozostałe urządzenia, a potem — jeśli masz włączoną weryfikację dwuetapową — o "
                  "hasło. Dokładnie ta sama kolejność co w samej aplikacji Telegrama."},
            {"warn": "Zalogowanie jest zapisywane lokalnie, w pliku `telegram.session` obok ustawień "
                     "xD-Tools. Ten plik jest równoważny byciu zalogowanym na Twoje konto: nie jest "
                     "zaszyfrowany i nie jest czymś, co należy kopiować na inny komputer albo komukolwiek "
                     "wysyłać."},
            {"p": "**Wyloguj**, obok Zaloguj, kasuje ten zapisany sesyjny plik — ta sama grupa "
                  "Telegram jest więc też miejscem, gdzie wylogować się z konta, na które się "
                  "zalogowałeś."},
            {"h2": "Rozmowa"},
            {"p": "**Źródło > Pobierz album z bota Telegram...** otwiera zwykły czat. Pojawia się "
                  "dopiero wtedy, gdy zalogowanie zostało zapisane i włączone jest pole funkcji "
                  "eksperymentalnych — a stoi obok Zgraj płytę audio CD, bo pobranie jest źródłem "
                  "dźwięku dokładnie tak samo jak płyta."},
            {"fig": ("telegram-chat", "Czat, z kolejką pobierań po prawej."),},
            {"p": "Celowo zwykły czat, a nie pole wyszukiwania: komendy Twojego bota są Twoje i xD-Tools nie "
                  "może ich znać. Pokazuje więc to, co bot przysyła, i pozwala go obsługiwać — tekst, jego "
                  "przyciski inline i każdy dołączony plik. **Szybkie komendy** wysyłają `/start` albo "
                  "`/help` jednym kliknięciem, bo rozumie je niemal każdy bot."},
            {"p": "Dwie wygody warte uwagi. To, co pisze bot, jest **tłumaczone pod oryginałem**, na język "
                  "ustawiony w xD-Tools — oryginał zostaje, bo tłumaczenie może być błędne, a dokładną "
                  "komendę czy nazwę pliku lepiej czytać tak, jak przyszła. A bot, który buduje menu, "
                  "podmieniając własną wiadomość zamiast wysyłać nową, jest obsługiwany poprawnie: "
                  "wiadomość zmienia się na miejscu, tak jak na telefonie."},
            {"p": "**Zdjęcie przysłane przez bota** — okładka, zrzut ekranu, cokolwiek, co nie jest "
                  "plikiem do pobrania — można kliknąć po załadowaniu, żeby zapisać je na dysk. Nic z "
                  "tego nie trafia do kolejki pobierań poniżej — to jest dla pojedynczego obrazka, nie "
                  "dla całego albumu plików."},
            {"h2": "Kolejka pobierań"},
            {"p": "Pliki nigdy nie pojawiają się w rozmowie — idą do **kolejki po prawej**, która jest "
                  "jedynym miejscem, gdzie widać nazwę pliku, rozmiar, postęp i prędkość. Cały album "
                  "przychodzący jako dwadzieścia załączników zasypałby inaczej rozmowę dwudziestoma niemal "
                  "identycznymi wierszami."},
            {"p": "Pobieranie startuje samo, a naraz pobierają się najwyżej trzy pliki. Ten, który się nie "
                  "udał, dostaje przycisk **Ponów**, a nie znika. Linijka podsumowania nad kolejką trzyma "
                  "bieżący bilans, gdy kilka plików leci naraz — ile gotowych, w kolejce i pobieranych, "
                  "łączny procent i sumaryczna prędkość — więc stan dwudziestoplikowego albumu to jedna "
                  "linijka do rzucenia okiem, a nie dwadzieścia wierszy do zsumowania w głowie."},
            {"h2": "Od pobrania do płyty"},
            {"p": "**Plik FLAC jest odkładany na miejsce już przy odbiorze**: po zakończeniu "
                  "pobierania jego tagi zostają odczytane, a plik trafia wprost do własnego podfolderu "
                  "`Wykonawca - Album`. Album pobrany teraz jest więc gotowym folderem albumu, zanim "
                  "jeszcze wyląduje ostatnia ścieżka — nie ma czego sprzątać."},
            {"p": "To, czego tagi nie potrafią umiejscowić, zostaje luzem w folderze pobierań: MP3 albo "
                  "Ogg (ich tagi nie są jeszcze czytane), FLAC bez tagów albo plik, który w ogóle nie "
                  "jest muzyką. Tym zajmuje się **Posortuj na foldery albumów** — i tym, co zostawiły "
                  "wcześniejsze sesje: jeden podfolder na album, nazwany na podstawie tagów, a to, co "
                  "bez tagów, grupowane według czasu przyjścia."},
            {"note": "Sortowanie rusza wyłącznie pliki audio. Okładka przysłana przez bota razem z "
                     "utworami — i cokolwiek innego, co już leży w tym folderze — zostaje dokładnie tam, "
                     "gdzie było. Nic też nigdy nie jest nadpisywane: zajęta nazwa dostaje `(2)`."},
            {"p": "**Nagraj pobrane albumy...** przechodzi dalej do nagrywania. Najpierw sortuje, żeby "
                  "nie dało się przypadkiem nagrać dwóch albumów na jednej płycie, i pyta który album, "
                  "jeśli jest więcej niż jeden. Dalej jest to zwykłe okno nagrywania opisane w rozdziale "
                  "„Nagrywanie z folderu” — dlatego w projekcie MiniDisc to wymaga przystawki MDRem, choć "
                  "samo pobieranie nie."},
            {"p": "**Otwórz folder pobierania** otwiera go w menedżerze plików, żeby zajrzeć przed nagraniem."},
            {"p": "Obie operacje istnieją też poza czatem, dla plików pobranych wcześniej: **Źródło > "
                  "Posortuj folder zgrywania/pobierania na albumy...** i **Nagrywanie > Nagraj z "
                  "folderu zgrywania/pobierania na {medium}...** — nazwane od folderu, na którym "
                  "działają (tego samego, co przy zgrywaniu CD), a nie od Telegrama konkretnie, bo "
                  "folder nagrywany w ten sposób wcale nie musi pochodzić z bota."},
            {"tip": "Oba przyciski milkną, dopóki cokolwiek się pobiera — sortowanie albo nagrywanie "
                    "niedopisanych plików byłoby gorsze niż poczekanie."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Rozwiązywanie problemów",
        "blocks": [
            {"h2": "Magnetofon nie reaguje na nic"},
            {"ol": [
                "**Sprawdź, czy przystawka żyje.** Dioda statusu powinna być zielona. Fioletowa oznacza, "
                "że firmware w ogóle nie wystartował ze sprzętem.",
                "**Sprawdź, czy nadaje.** Skieruj diodę na aparat w telefonie — podczerwień widać jako "
                "fioletowo-biały punkt. Komenda `BEAM` zapala ją na dwie sekundy, czyli dość długo, żeby "
                "zobaczyć; pojedyncza komenda trwa 45 ms i jest niewidoczna.",
                "**Sprawdź celowanie i odległość.** Zasięg roboczy to mniej więcej 20–30 cm, prosto w "
                "czujnik magnetofonu. Jeżeli musisz podchodzić bliżej, prąd diody jest za mały — patrz "
                "uwaga o Rd w rozdziale o MDRem.",
                "**Sprawdź port.** Okno > Ustawienia... > Wykryj. Jeżeli nic nie odpowiada, przystawka "
                "się nie enumeruje — spróbuj innego kabla.",
            ]},
            {"h2": "„Nie połączono” w oknie pilota"},
            {"p": "Coś innego trzyma już otwarty port szeregowy. Naraz może go mieć tylko jeden program — "
                  "zamknij drugie okno xD-Tools, okno dialogowe albo terminal, który go używa."},
            {"h2": "Nowy tytuł ma doklejony ogon starego"},
            {"p": "Pole **Najpierw skasuj istniejące tytuły** było odznaczone albo stary tytuł był dłuższy, "
                  "niż przewidywało kasowanie. Uruchom wysyłkę jeszcze raz z zaznaczonym polem."},
            {"h2": "Dwa utwory wylądowały na jednej ścieżce"},
            {"p": "Przechodzą jeden w drugi bez ciszy między nimi, a LEVEL-SYNC nie miał czego usłyszeć. "
                  "Nagraj ponownie z zaznaczonym **Znaczniki ścieżek przez przystawkę** i wyłączonym "
                  "LEVEL-SYNC na magnetofonie."},
            {"h2": "Wszystkie ścieżki dostały ten sam tytuł"},
            {"p": "To był prawdziwy błąd i jest naprawiony, ale warto znać zachowanie magnetofonu, które "
                  "za nim stało: to maszyna stanowa, której nie da się o nic zapytać, a numer ścieżki "
                  "wysłany na pauzie nie przechodzi. Dlatego sekwencja nadawania tytułów zaczyna się od "
                  "**Stop** — doprowadza magnetofon do znanego stanu, zamiast go zakładać."},
            {"h2": "Nic nie zapisało się na płycie"},
            {"p": "Tytuły żyją w pamięci magnetofonu aż do wysunięcia płyty. Wysuń ją."},
            {"h2": "Brak dźwięku przy nagrywaniu albo odsłuchu"},
            {"p": "**Nagrywanie**: sprawdź, czy **Okno > Ustawienia...** ma wybrane właściwe urządzenie "
                  "dla nośnika, na który nagrywasz — MiniDisc i kaseta mają osobne, a urządzenie, które "
                  "zostało od tamtej pory odłączone, pokazuje się jako **(niepodłączone)** zamiast po "
                  "cichu zamienić się na inne. **Odsłuch**: pasek odsłuchu zawsze odtwarza przez to, co "
                  "system operacyjny aktualnie uznaje za swoje domyślne wyjście, niezależnie od "
                  "ustawienia urządzenia do nagrywania powyżej — sprawdź, czy to właśnie głośniki albo "
                  "słuchawki, których się spodziewasz."},
            {"h2": "Wydrukowana etykieta ma zły rozmiar"},
            {"p": "Sprawdź, czy drukarka nie skaluje do strony — musi drukować w 100%. Jeżeli to sam "
                  "obszar roboczy wygląda na ekranie na zły rozmiar fizyczny, odpowiada za to **DPI "
                  "ekranu** w Okno > Ustawienia..., które wpływa wyłącznie na wyświetlanie, nie na "
                  "eksport."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Dodatek: zestaw komend MDRem",
        "blocks": [
            {"p": "Przystawka mówi zwykłym tekstem przez swój wirtualny port szeregowy, 115200 bodów. "
                  "Każda komenda kończy się jedną linią — `OK`, `PONG` albo `ERR <powód>` — więc program "
                  "może parsować odpowiedź, nie znając komendy. Linie zaczynające się od `;` to "
                  "diagnostyka."},
            {"p": "xD-Tools obsługuje to wszystko za ciebie. Opis jest tu dla kogoś, kto chce rozmawiać z "
                  "przystawką wprost — z terminala albo z własnego skryptu."},
            {"table": {
                "head": ["Komenda", "Działanie"],
                "rows": [
                    ["`PING`", "Odpowiada `PONG`. Tak rozpoznaje się przystawkę."],
                    ["`HELP`", "Wypisuje komendy."],
                    ["`KEY <nazwa>`", "Podaje kod klawisza i liczbę bitów. Nic nie wysyła."],
                    ["`SEND <nazwa>`", "Wysyła nazwany klawisz albo pojedynczy znak."],
                    ["`RAW <hex> [bity]`", "Wysyła dowolny kod. `bity` domyślnie 20."],
                    ["`DUMP <hex> [bity]`", "Drukuje czasy mark/space. Nic nie wysyła."],
                    ["`TITLEDISC <tekst>`", "Zapisuje tytuł płyty."],
                    ["`TITLETRACK <n> <tekst>`", "Zapisuje tytuł ścieżki n."],
                    ["`TIMING ...`", "Stroi czasy — w tym `TIMING COUNT`, liczbę naciśnięć Delete "
                                     "używanych do czyszczenia tytułu."],
                    ["`SELFTEST`", "Sprawdza nośną. Wymaga zworki GPIO12–GPIO13."],
                    ["`GPIOTEST`", "Sam test ciągłości tej zworki."],
                    ["`BEAM [ms]`", "Ciągła nośna, domyślnie 2000 ms — widoczna w aparacie telefonu."],
                    ["`BLINK [cykle]`", "To samo, ale migające, co łatwiej wychwycić."],
                ],
            }},
            {"note": "`SEND A` i `SEND a` to **różne kody**. Pojedyncze znaki są celowo wrażliwe na "
                     "wielkość liter; nazwy klawiszy już nie."},
            {"h2": "Jak działa protokół"},
            {"p": "Sony SIRC: nośna 40 kHz o wypełnieniu około jednej trzeciej, bity wysyłane od "
                  "najmłodszego, znacznik startu 2400 mikrosekund i ramka powtarzana co 45 ms. Jedynka to "
                  "mark 1200 mikrosekund, zero — 600. Jak prawdziwy pilot, każde naciśnięcie wysyłamy "
                  "trzy razy."},
            {"p": "Kody znaków są 20-bitowe, `0x61D00` z wartością ASCII w młodszym bajcie — to własny "
                  "protokół klawiaturowy RM-D10P. Klawisze funkcyjne magnetofonu (Play, Stop, Record, "
                  "Enter) to **12-bitowe** kody z innego bloku. Wysłanie ich jako 20-bitowych daje "
                  "zupełnie inną ramkę i magnetofon je ignoruje."},
            {"h2": "Rzeczy sprawdzone, które nie działają"},
            {"ul": [
                "**Katakana.** Nasuwająca się hipoteza — że kody znaków to `0x61D00` plus bajt JIS "
                "X 0201, co umieściłoby katakanę półszerokościową w nieużywanej górnej połowie — została "
                "sprawdzona na prawdziwym magnetofonie i odrzucona. Kontrolne „A” się pojawiło, żaden z "
                "kodów katakany nie zrobił nic.",
                "**Delete poza trybem edycji nazwy.** Na zapauzowanej ścieżce nie robi zupełnie nic. "
                "Tytuły da się czyścić wyłącznie po Name.",
                "**Przytrzymanie klawisza, żeby kasować szybciej.** Autopowtarzanie magnetofonu kasuje "
                "cztery znaki w 1,09 s — po 272 ms — wobec 285 ms przy pojedynczych naciśnięciach. Około "
                "trzech i pół operacji edycyjnych na sekundę to twardy sufit.",
            ]},
        ],
    },
]
