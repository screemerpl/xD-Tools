"""Polska wersja instrukcji obsługi. Słownictwo bloków opisuje
build_manual.py ("p", "ul", "ol", "table", "fig", "note", "warn", "tip",
"h2").

Znaczniki w tekście: **pogrubienie**, `dosłownie`.

Nazwy poleceń muszą być dokładnie takie, jak w polskim interfejsie --
zrzuty ekranu w tej wersji też są polskie, więc rozjazd byłby widoczny od
razu. Źródłem prawdy jest src/mdtools/i18n/mdtools_pl.ts.
"""

TITLE = "MDTools"
SUBTITLE = "Studio MiniDisc — instrukcja obsługi"
TITLE_NOTE = "Projektowanie etykiet, nagrywanie płyt i nadawanie tytułów — z przystawką MDRem"
COVER_CAPTION = "Co z czym rozmawia: komendy przez USB, klawisze przez podczerwień, dźwięk przez S/PDIF."
VERSION_LINE = "Wersja 0.1.0"
AUTHOR_LINE = 'Artur "Screemer" Jakubowicz'
DATE_LINE = "Sierpień 2026"
TOC_TITLE = "Spis treści"
FOOTER_LEFT = "MDTools — Studio MiniDisc — instrukcja obsługi"

BOOK = [
    # ------------------------------------------------------------------
    {
        "title": "Czym to jest",
        "blocks": [
            {"p": "MDTools to warsztat do MiniDisc na komputer. Zaczęło się od projektanta etykiet, a "
                  "wyrosły z tego cztery narzędzia dzielące jeden plik projektu:"},
            {"ul": [
                "**Projektowanie** naklejki na płytę i wkładki J-card do pudełka, wraz z eksportem "
                "gotowym do druku i cięcia.",
                "**Nagrywanie** całego albumu z foobar2000 na MiniDisc, ze znacznikiem przy każdym "
                "utworze.",
                "**Nadawanie tytułów**: zapisanie nazwy albumu i wszystkich utworów na samej płycie, tak "
                "żeby pokazywał je wyświetlacz magnetofonu.",
                "**Sterowanie magnetofonem** z programowego pilota — transport, numery ścieżek, tryby "
                "odtwarzania.",
            ]},
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
                    ["Projektowanie i druk", "MDTools, drukarka, a do cięcia — ploter Cricut albo pewna "
                                             "ręka i nożyczki."],
                    ["Nadawanie tytułów", "Przystawka MDRem w porcie USB i magnetofon MiniDisc Sony, w "
                                          "który da się nią wycelować."],
                    ["Nagrywanie albumu", "Powyższe oraz foobar2000 z komponentem Beefweb i kabel "
                                          "cyfrowy (S/PDIF) z komputera do magnetofonu."],
                ],
            }},
            {"note": "Wszystko w tej instrukcji zostało ustalone na **Sony MDS-JE480**. Inne magnetofony "
                     "Sony obsługujące protokół klawiaturowy RM-D10P powinny zachowywać się tak samo, ale "
                     "zwłaszcza czasy zmierzono właśnie na tym modelu."},
            {"h2": "Jedna rzecz do zrozumienia na starcie"},
            {"p": "Magnetofon nie może odpowiedzieć. Podczerwień działa tylko w jedną stronę, a magistrala "
                  "Control A1 nie jest w tym modelu podłączona. MDTools może więc wysłać polecenie, ale "
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
            {"p": "Jeżeli masz gotową paczkę, uruchom `MDTools.exe`. Ze źródeł:"},
            {"ul": [
                "`python -m venv .venv`",
                "`.venv\\Scripts\\pip install -e \".[dev]\"`",
                "`.venv\\Scripts\\python -m mdtools.main`",
            ]},
            {"h2": "Wybór języka"},
            {"p": "**Pomoc > Język** daje English, Polski i japoński. Zmiana wymaga restartu, a program "
                  "sam proponuje, że go wykona."},
            {"h2": "Ekran powitalny"},
            {"p": "MDTools zaczyna od krótkiej listy tego, co możesz chcieć zrobić: wrócić do jednego z "
                  "ostatnich projektów, wskazać inny albo zacząć nowy."},
            {"fig": ("startup", "Ekran powitalny. Przycisk Pilot... pojawia się dopiero po włączeniu przystawki.")},
            {"ul": [
                "**Otwórz wybrany** albo dwuklik — powrót do ostatniego projektu.",
                "**Otwórz inny projekt...** — wskazanie pliku `.mdproj` w dowolnym miejscu.",
                "**Nowy projekt...** — wybór szablonu dla każdej z dwóch stron.",
                "**Multiprint...** — złożenie grafik z kilku różnych projektów na jednej kartce. To nie "
                "otwiera żadnego projektu; to samodzielne zadanie.",
                "**Pilot...** — programowy pilot. Też samodzielny, widoczny tylko przy włączonym MDRem.",
            ]},
            {"h2": "Projekt to dwie strony plus metadane"},
            {"p": "Każdy projekt zawiera dokładnie jeden projekt **Etykiety płyty** i jeden **Okładki / "
                  "J-Card**, przełączane listą w lewym górnym rogu okna. Obok nich trzyma tytuł albumu, "
                  "wykonawcę, rok i listę utworów — z których korzystają zarówno projekty etykiet, jak i "
                  "nadawanie tytułów oraz automatyczne układanie."},
            {"fig": ("new-project", "Plik > Nowy pyta o jeden szablon każdego rodzaju.")},
            {"p": "**Plik > Zapisz** (Ctrl+S) zapisuje to wszystko — oba projekty, metadane i wstawione "
                  "obrazy — do jednego pliku `.mdproj`. Obrazy są osadzone, a nie dowiązane, więc "
                  "przeniesienie projektu ani skasowanie oryginalnego zdjęcia niczego nie zepsuje."},
            {"h2": "Zamykanie projektu"},
            {"p": "**Plik > Zamknij projekt** (Ctrl+W) nie kończy programu, tylko przywraca ekran "
                  "powitalny — przejście do kolejnej płyty nie wymaga więc ponownego uruchamiania. "
                  "Krzyżyk okna robi to samo. Jeżeli są niezapisane zmiany, program najpierw o nie "
                  "zapyta."},
            {"p": "Żeby wyjść z MDTools na dobre, użyj **Plik > Zakończ** albo anuluj ekran powitalny, "
                  "kiedy się pojawi."},
            {"h2": "Gdzie zapisywane są projekty"},
            {"p": "Przy pierwszym zapisie MDTools proponuje **Dokumenty\\MiniDiscProjects** i nazwę pliku "
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
                  "MDTools ma sześć wbudowanych."},
            {"table": {
                "head": ["Szablon", "Co to jest"],
                "rows": [
                    ["MiniDisc Disc Label", "Klasyczna naklejka 37 × 52 mm na front płyty, ze ścięciem 3 "
                                            "mm w lewym górnym narożniku i zaokrągleniami w pozostałych."],
                    ["MiniDisc Disc Label (with Slider)", "To samo plus osobna mała naklejka na suwak "
                                                          "zabezpieczenia przed zapisem."],
                    ["Full disc label", "Etykieta na całą powierzchnię kasety, 71 × 68 mm pomniejszone o "
                                        "margines 0,8 mm."],
                    ["Full disc label (with Slider)", "Cała powierzchnia plus naklejka suwaka, wpasowana "
                                                      "we wcięcie, na którym leży. Tego używa "
                                                      "automatyczne układanie."],
                    ["MiniDisc Cover (J-Card)", "Trzypanelowa wkładka do pudełka: przód, grzbiet, tył."],
                    ["MiniDisc Cover (J-Card + Window)", "To samo z wyciętym okienkiem."],
                ],
            }},
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
            {"h2": "Zmiana szablonu później"},
            {"p": "**Szablony > Zmień szablon tej strony...** przełącza bieżącą stronę na inny szablon."},
            {"warn": "To **czyści stronę**: znikają wszystkie warstwy, a historia cofania jest zerowana. "
                     "Program pyta wcześniej. Druga strona i metadane pozostają nietknięte."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Metadane i okładka",
        "blocks": [
            {"p": "**Projekt > Metadane...** trzyma tytuł albumu, wykonawcę, rok i listę utworów. Warto je "
                  "wypełnić nawet przy samym projektowaniu etykiety: listę utworów można wrzucić na "
                  "grafikę jako tekst, a automatyczne układanie i nadawanie tytułów czytają właśnie stąd."},
            {"fig": ("metadata", "Projekt > Metadane, z pobraną okładką i wczytaną listą utworów.")},
            {"h2": "Trzy sposoby wypełnienia"},
            {"ol": [
                "**Ręcznie.** Dodaj utwór, wpisz, ustaw kolejność przyciskami Przesuń w górę / w dół. "
                "Czasy są opcjonalne i zapisuje się je jako mm:ss.",
                "**Wyszukaj listę utworów...** przeszukuje katalog iTunes po wpisanym albumie i "
                "wykonawcy, po czym uzupełnia listę utworów, rok i okładkę. Jeżeli pasuje więcej niż "
                "jedno wydanie, program pyta które.",
                "**Wczytaj z foobar2000** bierze wszystko z bieżącej playlisty foobara, a potem szuka do "
                "tego okładki.",
            ]},
            {"tip": "**Wczytaj z foobar2000 to zwykle lepsze źródło.** To są te konkretne pliki, które "
                    "zaraz nagrasz, z ich własnymi tagami i w ich własnej kolejności — wyszukiwanie może "
                    "zwrócić inne wydanie z inną kolejnością utworów."},
            {"h2": "Okładka"},
            {"p": "Pobrana okładka zapisuje się w dwóch miejscach: w projekcie, żeby była tam przy "
                  "następnym otwarciu, oraz w galerii użytkownika, żeby **Narzędzia > Wstaw zasób...** "
                  "mogło ją wstawić na stronę jak każdy inny obraz."},
            {"tip": "**Jeżeli pobrana okładka jest nie ta, kliknij ją.** Podgląd jest przyciskiem: "
                    "otwiera okno wyboru pliku, żebyś sam wskazał właściwą. Oba automatyczne źródła "
                    "zgadują i przy wznowieniu, składance albo zespole o popularnej nazwie regularnie "
                    "zgadują źle — wyszukiwarka nie ma jak wiedzieć, które tłoczenie trzymasz w ręku."},
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
            {"p": "**Różdżka** w panelu Narzędzia buduje obie strony z okładki i listy utworów albumu. To "
                  "najszybsza droga od „mam płytę” do „mam co wydrukować”."},
            {"p": "Najpierw wypełnij album i wykonawcę w Projekt > Metadane... — po tym program szuka. "
                  "Jeżeli nie ma jeszcze okładki, najpierw ją znajdzie."},
            {"warn": "To **zastępuje obie strony** i zeruje historię cofania, więc program prosi o "
                     "potwierdzenie. Same metadane zostają nietknięte."},
            {"h2": "Co powstaje"},
            {"p": "**Etykieta płyty**: szablon na całą powierzchnię, okładka rozciągnięta na nią i "
                  "przycięta do linii cięcia oraz logo MiniDisc na naklejce suwaka. Trójkąt kierunku "
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
            {"p": "Projekt opuszcza MDTools jako dwa pliki opisujące ten sam przedmiot na dwa sposoby."},
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
            {"h2": "Włączenie w MDTools"},
            {"p": "**Okno > Ustawienia...**, zaznacz **Włącz przystawkę MDRem (pilot na podczerwień)** i "
                  "wybierz port szeregowy."},
            {"fig": ("settings", "Okno > Ustawienia. Adres foobar2000 jest niezależny od przystawki.")},
            {"p": "**Wykryj** pyta każdy port szeregowy w komputerze, czy odpowiada na nim MDRem. Musi tak "
                  "działać: płytka zgłasza identyfikator USB `2E8A:0003`, ten sam co jej własny bootloader "
                  "i inne płytki Waveshare, więc jedyną pewną identyfikacją jest odpowiedź urządzenia na "
                  "`PING`."},
            {"p": "Po zaznaczeniu pola pojawiają się trzy rzeczy: **Wyślij listę utworów** w Projekt > "
                  "Metadane..., **Pilot...** na ekranie powitalnym oraz **Nagraj na MiniDisc z "
                  "foobar2000...** w menu Projekt."},
            {"note": "Adres foobar2000 na tej samej stronie celowo *nie* jest powiązany z tym polem — do "
                     "czytania playlisty potrzebny jest foobar2000, a nie przystawka na podczerwień."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Programowy pilot",
        "blocks": [
            {"p": "**Pilot...** na ekranie powitalnym otwiera zamiennik pilota magnetofonu, ułożony tak "
                  "jak ten fizyczny."},
            {"fig": ("remote", "Okno pilota. Linia stanu mówi, co wysłano, a nie co się stało.")},
            {"table": {
                "head": ["Grupa", "Klawisze"],
                "rows": [
                    ["Transport", "Poprzedni, Play, Następny, przewijanie wstecz, Pauza, przewijanie w "
                                  "przód, Stop, Zasilanie, Wysuń."],
                    ["Utwory", "Od 1 do 10, wybierane wprost. Wyższe numery są w firmwarze, ale nie mają "
                               "tu przycisku — użyj >25 na magnetofonie."],
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
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Zapisywanie tytułów na płycie",
        "blocks": [
            {"p": "**Projekt > Metadane... > Wyślij listę utworów** zapisuje tytuł płyty i nazwy "
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
            {"p": "Tablica klawiszy firmware'u kończy się na ścieżce 25, więc wyższej po prostu nie da się "
                  "wybrać na magnetofonie. Takie tytuły są wypisane jako pominięte, a nie po cichu "
                  "wyrzucone."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Nagrywanie albumu z foobar2000",
        "blocks": [
            {"p": "**Projekt > Nagraj na MiniDisc z foobar2000...** robi całą robotę za jednym razem: "
                  "uzbraja magnetofon, odtwarza album z foobar2000, pilnuje go do końca, zapisuje tytuły "
                  "i układa obie etykiety z okładki albumu."},
            {"note": "**To wymaga przystawki MDRem, a pozycja w menu pojawia się dopiero po jej włączeniu "
                     "w Okno > Ustawienia...** To przystawka wprowadza magnetofon w nagrywanie i to ona "
                     "stawia znaczniki ścieżek. Bez niej nagrywanie oznacza samodzielne wciśnięcie "
                     "Record na magnetofonie i pozostawienie podziału na ścieżki jego własnemu "
                     "LEVEL-SYNC — MDTools nie ma w tym udziału."},
            {"h2": "Przygotowanie"},
            {"ol": [
                "Zainstaluj w foobar2000 komponent **Beefweb Remote Control** (`foo_beefweb`). Tak "
                "MDTools czyta playlistę i śledzi, co gra. Domyślny adres `http://localhost:8880` jest "
                "tym, czego MDTools oczekuje; zmień go w Okno > Ustawienia..., jeżeli go przestawiłeś.",
                "Połącz wyjście **S/PDIF** komputera — optyczne albo koncentryczne — z wejściem cyfrowym "
                "magnetofonu. To ono niesie dźwięk; USB niesie wyłącznie komendy.",
                "Wczytaj album do bieżącej playlisty foobara, w kolejności, jaką chcesz mieć na płycie.",
                "Włóż czystą albo kasowalną płytę z zamkniętym suwakiem i ustaw tryb nagrywania (SP albo "
                "LP2) **na magnetofonie** — MDTools nie potrafi go odczytać ani zmienić.",
                "**Wyłącz LEVEL-SYNC** na magnetofonie. Patrz niżej.",
                "Wyceluj przystawkę w czujnik magnetofonu i zostaw ją tak.",
            ]},
            {"fig": ("record", "Playlista w kolejności, w jakiej trafi na płytę.")},
            {"h2": "Co się dzieje"},
            {"ol": [
                "MDTools pokazuje playlistę i jej łączny czas, i ostrzega, jeśli nie zmieści się na "
                "80-minutowej płycie w SP.",
                "Ustawia foobara na odtworzenie wszystkiego raz, po kolei — bez losowania i powtarzania — "
                "żeby płyta nie skończyła w innej kolejności niż tytuły.",
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
                "zostaje wyszukana, a **obie strony układają się same**.",
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
            {"p": "Dlatego MDTools sam wysyła znacznik dokładnie w chwili, gdy foobar zmienia utwór — to "
                  "pole **Znaczniki ścieżek przez przystawkę** i powinno zostać zaznaczone."},
            {"warn": "**Wyłącz wtedy LEVEL-SYNC na magnetofonie.** Jedno i drugie naraz oznacza tę samą "
                     "granicę dwa razy, o ułamek sekundy obok siebie, i zostawia między nimi szczątkową "
                     "ścieżkę. One się kłócą, a nie uzupełniają."},
            {"h2": "Tryb nagrywania i długość"},
            {"p": "MD mieści 80 minut w SP. MDTools ostrzega, gdy playlista jest dłuższa, ale może "
                  "wyłącznie ostrzec — LP2 i LP4 trzeba ustawić na samym magnetofonie i nie da się "
                  "odczytać, w którym trybie jest."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Nagrywanie z płyty CD",
        "blocks": [
            {"p": "**Projekt > Nagraj CD na MiniDisc...** przegrywa płytę audio CD na MiniDisc. "
                  "Odczytuje płytę, ustala, co to za album, zgrywa każdą ścieżkę do pliku, ładuje te "
                  "pliki do foobar2000 we właściwej kolejności i przekazuje sterowanie nagrywaniu, "
                  "które już znasz - to samo uzbrajanie, te same znaczniki ścieżek, to samo nadawanie "
                  "tytułów."},
            {"note": "**To również wymaga przystawki MDRem**, a pozycja w menu pojawia się dopiero po "
                     "jej włączeniu. Sam odczyt płyty przystawki nie potrzebuje, ale ta pozycja nie "
                     "kończy się na odczycie: przechodzi od razu do nagrywania tego, co odczytała."},
            {"h2": "Dlaczego najpierw kopia"},
            {"p": "foobar2000 potrafi odtwarzać płytę CD bezpośrednio i tak byłoby prościej. Wtedy "
                  "jednak płyta jest czytana na żywo, w trakcie nagrywania, bez żadnego zabezpieczenia "
                  "- napęd potykający się o rysę w 31. minucie zapisze to potknięcie na MiniDisc, a "
                  "nagrania na MiniDisc nie da się potem załatać."},
            {"p": "Wcześniejsza kopia przenosi każdy błąd odczytu w miejsce, gdzie kosztuje tylko "
                  "ponowną próbę. MDTools używa do tego **cdparanoi**, zbudowanej właśnie po to, by "
                  "męczyć uszkodzoną płytę aż do poprawnego odczytu, oraz **flac** do zapisu wyniku. "
                  "Oba narzędzia są dołączone do MDTools; nie trzeba niczego instalować."},
            {"fig": ("cd-rip", "Płyta odczytana, rozpoznana i gotowa do zgrania.")},
            {"h2": "Krok po kroku"},
            {"ol": [
                "Włóż płytę do napędu i wybierz napęd z listy. **Odśwież** szuka ponownie, jeśli "
                "podłączyłeś napęd już po otwarciu okna.",
                "Naciśnij **Odczytaj płytę**. MDTools czyta spis treści i wyszukuje płytę w "
                "MusicBrainz, który rozpoznaje ją po długościach ścieżek - sama płyta CD nie zawiera "
                "żadnego tekstu.",
                "Sprawdź, co wróciło. Jeśli pasuje kilka wydań, wybierz właściwe z pola **Wydanie**; "
                "tytuły ścieżek zmienią się razem z nim.",
                "Popraw to, co się nie zgadza. Tytuły są edytowalne i to one trafiają do plików, a "
                "później na MiniDisc.",
                "Naciśnij **Zgraj i nagraj**. Po zakończeniu kopiowania okno nagrywania otworzy się "
                "samo.",
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
            {"p": "Dlatego MDTools to sprawdza. Jeśli większości ścieżek nie da się przypisać jednemu "
                  "wykonawcy, podpisuje płytę jako **Various Artists**, nazywa ją `Mixtape` (chyba że "
                  "wydanie ma własną nazwę), wypisuje wykonawcę przy każdym utworze na J-card i "
                  "**rysuje okładkę na podstawie listy utworów** zamiast jej szukać."},
            {"p": "Wypełnij kolumnę **Wykonawca** samodzielnie, gdy wiesz, że płyta jest składanką, a "
                  "MusicBrainz tego nie podał - to właśnie ta kolumna jest sprawdzana."},
            {"note": "Album z gościnnym udziałem w jednym utworze **nie jest** składanką i nie jest tak "
                     "traktowany. Sprawdzane jest to, czy większość utworów należy do tego samego "
                     "wykonawcy, a nie to, czy podpisy się w ogóle różnią."},
            {"p": "To samo dotyczy nagrywania z foobar2000: playlista złożona z niepowiązanych utworów "
                  "jest rozpoznawana tak samo i z tym samym skutkiem."},
            {"h2": "Gdzie trafiają zgrane pliki"},
            {"p": "Domyślnie do folderu tymczasowego, do `MDTools CD Rip`, po jednym folderze na album. "
                  "To półprodukt do nagrania, a nie kolekcja muzyki - jeden album to kilkaset megabajtów "
                  "- a Okno > Ustawienia... pozwala wskazać inne miejsce."},
            {"p": "**Nie** są kasowane po zakończeniu nagrywania, bo foobar2000 wciąż ma je na "
                  "playliście i możesz chcieć ich posłuchać ponownie. Poprzednia kopia znika w chwili "
                  "rozpoczęcia następnej."},
            {"warn": "Załadowanie zgranych ścieżek do foobar2000 **czyści jego bieżącą playlistę**. To, "
                     "co miałeś tam przygotowane, przepadnie - przenieś to wcześniej gdzie indziej, "
                     "jeśli chcesz zachować."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Kasowanie płyty",
        "blocks": [
            {"p": "**Projekt > Skasuj MiniDisc...** czyści płytę w magnetofonie. Działa na tym, co "
                  "fizycznie jest w środku, więc nie ma znaczenia, który projekt jest otwarty ani czy "
                  "w ogóle jakiś jest."},
            {"warn": "Nie da się tego cofnąć, a MDTools nie widzi wyniku. Upewnij się, że w "
                     "magnetofonie jest ta płyta, o którą Ci chodzi, i że jej suwak zabezpieczający "
                     "jest zamknięty."},
            {"h2": "Dlaczego pyta, co widzisz"},
            {"p": "To jedyna operacja, przy której MDTools nie wie, co robi jego własna komenda. "
                  "Klawisz **Erase** jest rozpoznawany przez magnetofon jako polecenie zapisu - tyle "
                  "udało się potwierdzić - ale nie ustalono, które menu edycji otwiera, bo klawisze "
                  "zapisu dało się bezpiecznie testować tylko na płycie zabezpieczonej, gdzie "
                  "magnetofon odpowiada na każdy z nich tym samym komunikatem."},
            {"p": "Zamiast zgadywać Twoim nagraniem, MDTools wysyła Erase i pyta, co pokazuje "
                  "wyświetlacz. Potwierdzenie idzie dalej tylko wtedy, gdy potwierdzisz, że widzisz "
                  "pytanie w rodzaju **All Erase?**. Po odpowiedzi odmownej program wycofuje "
                  "magnetofon z menu, w którym akurat stoi."},
            {"fig": ("erase", "Wysyła komendę, a potem pyta, co pokazuje magnetofon.")},
            {"note": "Tak jak przy tytułach, skasowanie żyje w pamięci magnetofonu do chwili "
                     "wysunięcia płyty. MDTools proponuje potem wysunięcie - skorzystaj, bo inaczej "
                     "przy zaniku zasilania płyta zachowa starą zawartość."},
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
                  "zamknij drugie okno MDTools, okno dialogowe albo terminal, który go używa."},
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
            {"h2": "Nie można połączyć się z foobar2000"},
            {"ul": [
                "foobar2000 jest uruchomiony.",
                "Komponent **Beefweb Remote Control** jest zainstalowany *i włączony*.",
                "Adres w Okno > Ustawienia... zgadza się z portem Beefweb.",
            ]},
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
            {"p": "MDTools obsługuje to wszystko za ciebie. Opis jest tu dla kogoś, kto chce rozmawiać z "
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
