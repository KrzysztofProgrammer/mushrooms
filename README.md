# Grzybobranie

Gra 2D w widoku z góry (rzut ortogonalny), napisana w Pythonie z użyciem biblioteki pygame-ce.
Chodzisz po losowo wygenerowanym lesie i zbierasz grzyby do plecaka. Uważaj na niedźwiedzie:
one też jedzą grzyby i gonią każdego, kogo zobaczą.

[Zrzut ekranu](screenshot.png)

Każde uruchomienie tworzy nowy świat: las mieszany, krętą drogę przez las, boczną ścieżkę
prowadzącą na polanę ze stawem, jeziora, krzaki i kamienie. Gra nie używa żadnych plików
graficznych, wszystko jest rysowane w kodzie.

## Instalacja i uruchomienie

Potrzebny jest Python 3.10 lub nowszy.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Żeby zagrać w konkretnym lesie, podaj jego ziarno (liczbę). To samo ziarno zawsze daje ten sam las:

```bash
.venv/bin/python main.py 1234
```

Gra nie wyświetla ziarna na ekranie, więc żeby wrócić do konkretnego lasu, uruchom grę z wybraną liczbą.

Żeby wczytać zapisaną grę (patrz „Zapis gry”), podaj zamiast liczby plik z zapisem:

```bash
.venv/bin/python main.py zapisy/grzybobranie_20261111_153000.json
```

Plik z katalogu `zapisy/` możesz też podać samą nazwą, bez ścieżki.

## Cel gry

Zbieraj grzyby, sprzedawaj je na straganie na końcu leśnej ścieżki i zarób jak najwięcej monet,
zanim dopadnie cię niedźwiedź. Kiedy niedźwiedź cię złapie albo zjesz trzy muchomory, gra się kończy
(GAME OVER). Twój wynik to suma monet zarobionych na sprzedaży grzybów (to, co wydasz na ulepszenia,
go nie zmniejsza). Grzyby, których nie zdążysz sprzedać, przepadają. Najlepszy wynik jest zapamiętywany
jako rekord.

## Sterowanie

| Klawisz | Działanie |
|---|---|
| WASD lub strzałki | ruch |
| Shift | bieg (szybszy, ale głośny i męczący, patrz „Wytrzymałość”) |
| E lub Esc | w sklepie: zamknij stragan (otwiera się sam po podejściu) |
| Z | w sklepie: zapisz grę |
| L | włącz lub wyłącz latarkę (po kupieniu na straganie) |
| P | pauza |
| M | pokaż lub ukryj minimapę (po jej kupieniu na straganie) |
| H | pokaż lub ukryj pełną pomoc (domyślnie widać tylko napis „H - pomoc”) |
| R | nowy, losowy las |
| Enter | po GAME OVER: zagraj jeszcze raz w tym samym lesie |
| Esc | wyjście z gry |

## Wytrzymałość

Na dole ekranu jest pasek wytrzymałości. Bieg go zużywa: pełny pasek wystarcza na **10 sekund biegu**.
Gdy nie biegniesz (idziesz albo stoisz), pasek powoli się odnawia, od zera do pełna w około 8 sekund.

Jeśli wytrzymałość spadnie do zera, postać **się męczy**: przez 2 sekundy stoi w miejscu i łapie oddech
(widać krople potu i obłoczki oddechu, a pasek miga na czerwono). Po zmęczeniu znów pobiegniesz dopiero,
gdy pasek odnowi się do około 30%, choć chodzić możesz od razu. Zmęczenie w trakcie ucieczki przed
niedźwiedziem bywa zgubne, więc pilnuj paska.

## Plecak

Na początku plecak mieści tylko **10 grzybów**. Gdy jest pełny, nie podniesiesz kolejnych jadalnych
grzybów (zostają na ziemi). Purchawki i muchomory są nadal aktywne, bo nie trafiają do plecaka.
Pojemność można zwiększyć na straganie.

**Ciężar.** Do 30 grzybów w plecaku idziesz normalnie. Każdy grzyb ponad 30 zabiera 1% prędkości
(spowolnienie nie przekroczy 45%, czyli przy pełnym plecaku na 80 miejsc idziesz o 45% wolniej).
Dotyczy to także biegu. Gra nie pokazuje ciężaru, poczujesz go tylko po wolniejszym ruchu. Ciężki plecak utrudnia
ucieczkę przed niedźwiedziem, więc nie warto nosić więcej, niż trzeba.

## Stragan

Na końcu bocznej ścieżki, na polanie, stoi stragan z czerwono-białym daszkiem. Na początku gry nie masz
minimapy, więc żeby go znaleźć, skręć z głównej drogi w boczną, węższą ścieżkę i idź nią do końca.
Po kupieniu minimapy stragan jest na niej zawsze oznaczony żółtym kwadratem. Wystarczy do niego podejść, a sklep otworzy się sam. Podczas handlu świat stoi
w miejscu (niedźwiedzie nie ruszają się), ale ceny nadal się zmieniają.

**Sprzedaż.** Klawisze **1**, **2**, **3** sprzedają jednego borowika, podgrzybka lub kurkę.
**Shift + 1/2/3** sprzedaje wszystkie sztuki danego gatunku.

**Ceny.** Bazowo borowik kosztuje 26 zł, podgrzybek 15 zł, a kurka 9 zł, ale cena zależy od dwóch rzeczy:

- **Losowe wahania.** Cena każdego gatunku sama błądzi wokół wartości bazowej (mniej więcej od 70% do 140%).
  Strzałka przy cenie pokazuje, czy ostatnio rośnie, czy spada, a wykres obok pokazuje ostatnie 8 minut.
- **Podaż i popyt.** Każdy sprzedany grzyb obniża cenę swojego gatunku. Przez minutę cena jest w pełni
  obniżona, a potem bardzo powoli (przez 6 minut) wraca do normalnego poziomu. Jeśli wrócisz na stragan
  po kilku minutach z tym samym gatunkiem, jego cena wciąż będzie wyraźnie niższa. Im więcej sprzedasz
  jednego gatunku naraz, tym tańsze stają się kolejne sztuki, a cena spada nawet do około 25% normalnej.
  Kolumna „Popyt” pokazuje, ile z normalnej ceny zostało. Opłaca się sprzedawać różne gatunki i rozkładać
  sprzedaż w czasie.

**Ulepszenia** (kupujesz za monety):

| Klawisz | Ulepszenie | Koszt |
|---|---|---|
| U | większy plecak: 10 → 20 → 35 → 55 → 80 miejsc | 80, 200, 420, 800 zł |
| B | ulepszenia mapy, kupowane po kolei: najpierw sama **minimapa**, potem **grzyby** na minimapie (wszystkie jako jednakowe białe kropki, bez rozróżnienia gatunków, także purchawki i muchomory), na końcu **niedźwiedzie** na minimapie | 60 zł, potem 150 zł, potem 220 zł |

**Latarka** (klawisz **L** w sklepie, 60 zł). Świeci przez **3 godziny gry** (3 minuty rzeczywiste),
ale bateria zużywa się tylko wtedy, gdy latarka jest włączona. Gdy się wyczerpie, trzeba kupić nową.
Nowej nie kupisz, dopóki obecna ma jeszcze baterię.

Ulepszenia obowiązują do końca rozgrywki. E lub Esc zamyka stragan. Żeby otworzyć go ponownie, odejdź kawałek od straganu i podejdź jeszcze raz.

### Zapis gry

Grę można zapisać tylko na straganie: w sklepie naciśnij **Z**. Zapis trafia do katalogu `zapisy/`
w folderze gry, do pliku z datą i godziną w nazwie (np. `zapisy/grzybobranie_20261111_153000.json`).
Nazwa pliku pojawia się na dole okna sklepu. Każdy zapis tworzy nowy plik, więc starsze zapisy zostają.

Zapis obejmuje cały stan rozgrywki: las, plecak, monety, ulepszenia, latarkę, ceny i historię sprzedaży,
grzyby w lesie, niedźwiedzie, godzinę, pogodę i zjedzone muchomory. W grze nie ma menu wczytywania:
zapis wczytuje się, podając plik przy uruchomieniu gry (patrz „Instalacja i uruchomienie”). Po
wczytaniu gra startuje w otwartym sklepie, tak jak w chwili zapisu.

## Grzyby

Grzyby zbierasz, przechodząc obok nich. Trafiają do plecaka, który widać w lewym dolnym rogu.

| Grzyb | Wygląd | Jak często |
|---|---|---|
| Borowik | duży brązowy kapelusz | rzadko |
| Podgrzybek | ciemnobrązowy kapelusz | średnio |
| Kurka | żółto-pomarańczowa kępka | często |

- Grzyby rosną w lesie, zwykle blisko drzew, w prześwitach między koronami.
- Zebrane grzyby odrastają z czasem w innych miejscach lasu.
- Po deszczu w lesie jest wysyp grzybów i przez chwilę rośnie ich więcej.

### Purchawka

Purchawka to biała, okrągła kulka z brodawkami. Nie trafia do plecaka. Kiedy na nią nadepniesz,
wybucha dużym obłokiem zarodników, który utrzymuje się przez 10 sekund.

- Niedźwiedź nie widzi cię, gdy stoisz w obłoku albo gdy obłok jest między wami. W ten sposób możesz zgubić pościg.
- Gdy sam stoisz w obłoku, prawie nic nie widzisz: ani drogi, ani niedźwiedzia.
- Niedźwiedź nie je purchawek, ale nadal może na ciebie wpaść, jeśli dojdzie do miejsca, gdzie cię widział.

### Muchomor

Muchomor to czerwony kapelusz z białymi kropkami. Jest trujący i nie trafia do plecaka.
Kiedy na niego nadepniesz:

- przez 10 sekund klawisze kierunków są pomieszane i co chwilę losowo zmieniają się na nowo,
- na cały ekran nakłada się pulsujący filtr, który zmienia kolor kolejno na czerwony, różowy, zielony i czarny.

Muchomory się sumują przez całą rozgrywkę:

- **drugi muchomor** (w dowolnym momencie, także długo po pierwszym): ekran robi się zupełnie czarny na 15 sekund,
  a minimapa znika,
- **trzeci muchomor**: GAME OVER, zatrułeś się.

Muchomory lepiej omijać. Niedźwiedzie też je jedzą (patrz niżej).

## Niedźwiedzie

- Niedźwiedź chodzi po lesie i wyczuwa grzyby z daleka. Kiedy jakiś znajdzie, podchodzi i go zjada.
- **Wzrok.** Niedźwiedź widzi to, co ma przed sobą. Pnie drzew, kamienie i krzaki zasłaniają mu widok.
  Z bardzo bliska wyczuje cię zawsze.
- **Słuch.** Jeśli biegniesz w pobliżu, niedźwiedź cię usłyszy i przyjdzie sprawdzić, co się dzieje.
  Nad jego głową pojawi się wtedy znak „?”.
- **Pościg.** Kiedy niedźwiedź cię zauważy, nad jego głową pojawia się „!”. Po krótkiej chwili rusza za tobą.
  Ekran pulsuje wtedy na czerwono, a strzałka przy krawędzi pokazuje, skąd biegnie.
- **Ucieczka.** Niedźwiedź biegnie szybciej, niż chodzisz, ale wolniej, niż biegniesz po drodze.
  Jeśli przez kilka sekund cię nie widzi, rezygnuje z pościgu, przeszukuje okolicę i wraca do swoich zajęć.
- **Rozmnażanie.** Niedźwiedź, który zje 10 grzybów, podwaja się: obok niego pojawia się drugi niedźwiedź.
  Im dłużej grasz, tym więcej niedźwiedzi jest w lesie.
- **Muchomory.** Niedźwiedź wywęszy i zje także muchomora. Przez następne 30 sekund porusza się
  o 35% szybciej, a wokół niego pulsuje czerwony pierścień. Pobudzony niedźwiedź w pościgu jest
  mniej więcej tak szybki jak ty, gdy biegniesz po drodze, więc trudno mu uciec. Zjedzony
  muchomor nie liczy się do 10 grzybów potrzebnych do podwojenia.

Na początku gry nie masz minimapy. Po jej kupieniu pojawia się w prawym górnym rogu, ale niedźwiedzi
na niej nie widać. Żeby je zobaczyć, kup na straganie trzecie ulepszenie mapy (klawisz B, po minimapie
i grzybach). Wtedy brązowa kropka to spokojny niedźwiedź, a migająca
pomarańczowo-czerwona to niedźwiedź, który cię goni. Do tego czasu ostrzegają cię tylko czerwona
poświata ekranu i strzałka przy krawędzi, gdy niedźwiedź już cię goni.

## Zegar i noc

W prawym górnym rogu jest zegar (pod minimapą, jeśli ją masz). **Jedna minuta rzeczywista to jedna godzina w grze**, więc doba trwa 24 minuty.
Rozgrywka zaczyna się o 15:00, więc do zmierzchu masz około 5 minut. Zegar stoi, gdy jesteś w sklepie albo masz włączoną pauzę.

- **Od 21:00 do 5:00 jest noc.** Świat jest wtedy ciemny, szary i spowity mgłą, która rozmywa kształty.
  Grzyby widać tylko jako niewyraźne plamy: nie rozróżnisz borowika, podgrzybka, kurki, purchawki ani
  muchomora (kurka i muchomor wyglądają w nocy tak samo). W nocy zbieranie to loteria, w której
  łatwo trafić na muchomora.
- W nocy świat jest dodatkowo o 10% ciemniejszy niż o zmierzchu.
- Od 20:00 do 21:00 (zmierzch) i od 5:00 do 6:00 (świt) świat łagodnie przechodzi między dniem a nocą.
- Czerwona poświata przy pościgu, napisy, plecak i minimapa zostają kolorowe.

### Latarka

W grze klawisz **L** włącza i wyłącza latarkę. Świeci snopem w kierunku, w którym patrzy postać, a wokół
niej jest mała poświata. W świetle latarki noc i mgła znikają: widać prawdziwe kolory, więc da się
odróżnić kurkę od muchomora. Stan baterii pokazuje panel pod zegarem. Latarka świeci także w dzień,
ale wtedy nic nie daje, a zużywa baterię, więc wyłączaj ją po świcie.

## Pogoda

W losowych momentach zaczyna padać deszcz.

- W czasie deszczu ziemia nasiąka wodą, a na drodze pojawiają się kałuże.
- Po mokrej ziemi idzie się wolniej. Ty tracisz więcej prędkości niż niedźwiedź.
- Po deszczu ziemia stopniowo wysycha.
- Zaraz po deszczu w lesie jest wysyp grzybów. Kiedy ziemia wyschnie, nadmiar grzybów powoli znika.

Gra nie wyświetla prognozy, deszcz poznasz po kroplach, a mokrą ziemię po kałużach i ciemniejszym gruncie.

## Wskazówki

- Na drodze poruszasz się najszybciej, ale tam niedźwiedź widzi cię najlepiej.
- W lesie pnie zasłaniają widok. W krzakach możesz się schować, choć poruszasz się w nich wolniej.
- Uciekając przed niedźwiedziem, nadepnij na purchawkę i zmień kierunek, gdy obłok cię zasłoni.
- Biegaj tylko wtedy, gdy musisz uciekać. Bieg przyciąga niedźwiedzie i męczy, a zmęczona postać na 2 sekundy staje w miejscu.
- Nie noś grzybów w nieskończoność: niesprzedane przepadają w GAME OVER. Wracaj na stragan, zanim plecak się zapełni.
- Sprzedawaj grzyby partiami i różnych gatunków. Cena gatunku wraca do normy dopiero około 7 minut po sprzedaży.
- Przed zmierzchem (20:00) zbierz i sprzedaj grzyby albo kup latarkę. Bez niej w nocy nie odróżnisz kurki od muchomora. Włączaj ją tylko przy zbieraniu, żeby bateria starczyła na dłużej.
- Minimapa (B) to tania i dobra pierwsza inwestycja. Kolejne ulepszenia mapy pomagają szybciej znajdować grzyby, a potem omijać niedźwiedzie.
- Zbieraj grzyby szybko, bo każdy zjedzony przez niedźwiedzia przybliża go do podwojenia.
- Po deszczu warto ruszyć na grzyby, ale pamiętaj, że w błocie trudniej uciec.

## Rekord

Najlepszy wynik (zarobione monety) zapisuje się w pliku `highscore.json` w folderze gry.
Żeby wyzerować rekord, usuń ten plik.
