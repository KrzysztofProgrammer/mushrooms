"""Stragan: ceny grzybów (losowe wahania + podaż/popyt), portfel i ulepszenia.

Cena = cena bazowa * wahanie losowe * czynnik popytu.

* Wahanie losowe: proces z powrotem do średniej (Ornstein-Uhlenbeck) - cena sama błądzi
  wokół ceny bazowej, osobno dla każdego gatunku.
* Podaż/popyt: każdy sprzedany grzyb danego gatunku to "nacisk podaży". Przez HOLD_TIME s
  działa w pełni (cena obniżona), potem słabnie liniowo przez RECOVER_TIME s - cena
  powoli rośnie z powrotem. Czynnik popytu = FLOOR + (1 - FLOOR) * exp(-DEMAND_K * nacisk),
  więc kolejne grzyby tego samego gatunku zbija się coraz taniej (malejący efekt).
"""

import math
import random
from collections import deque

from mushrooms import KINDS

BASE_PRICE = {"borowik": 26, "podgrzybek": 15, "kurka": 9}   # zł

HOLD_TIME = 60.0         # s - tyle jeden sprzedany grzyb w pełni obniża cenę
RECOVER_TIME = 360.0     # s - potem cena bardzo powoli wraca (nacisk słabnie do zera przez 6 minut)
DEMAND_K = 0.14          # siła spadku ceny na jeden sprzedany grzyb
FLOOR = 0.25             # cena nigdy nie spadnie poniżej 25% (przy wahaniu = 1)

NOISE_REVERT = 1 / 40    # 1/s - jak szybko wahanie wraca do 1.0
NOISE_VOL = 0.035        # zmienność wahania
NOISE_RANGE = (0.7, 1.4)

HIST_EVERY = 3.0         # s - co tyle zapisujemy cenę do wykresu
HIST_LEN = 160           # punktów (8 minut)
TREND_LAG = 6            # punktów wstecz do oceny trendu
TREND_EPS = 0.03

CAPACITIES = (10, 20, 35, 55, 80)          # pojemność plecaka na kolejnych poziomach
CAPACITY_COSTS = (80, 200, 420, 800)       # koszt przejścia na następny poziom
# ulepszenia mapy kupowane po kolei (jak plecak): minimapa, potem grzyby, potem niedźwiedzie
MAP_UPGRADES = (
    ("Minimapa", 60),
    ("Grzyby na minimapie", 150),
    ("Niedźwiedzie na minimapie", 220),
)


class Market:
    def __init__(self, seed):
        self.rng = random.Random(seed * 29 + 5)
        self.t = 0.0
        self.noise = {k: self.rng.uniform(0.9, 1.1) for k in KINDS}
        self.sales = {k: [] for k in KINDS}       # chwile sprzedaży (czas rynku)
        self.history = {k: deque(maxlen=HIST_LEN) for k in KINDS}
        self.hist_t = 0.0

        self.money = 0
        self.total_earned = 0
        self.sold = 0
        self.cap_level = 0
        self.map_level = 0          # 0 = brak minimapy, 1 = minimapa, 2 = + grzyby, 3 = + niedźwiedzie
        for _ in range(HIST_LEN):                 # wstępna historia, żeby wykres nie był pusty
            self._step_noise(HIST_EVERY)
            self._record()
        self.t = 0.0

    # ------------------------------------------------------------ ceny

    def _step_noise(self, dt):
        for k in KINDS:
            n = self.noise[k]
            n += (1.0 - n) * NOISE_REVERT * dt + self.rng.gauss(0, NOISE_VOL) * math.sqrt(dt)
            self.noise[k] = max(NOISE_RANGE[0], min(NOISE_RANGE[1], n))

    def _record(self):
        for k in KINDS:
            self.history[k].append(self.price(k))

    def update(self, dt):
        self.t += dt
        self._step_noise(dt)
        for k in KINDS:                           # zapomnij sprzedaże, które już nic nie znaczą
            s = self.sales[k]
            while s and self.t - s[0] > HOLD_TIME + RECOVER_TIME:
                s.pop(0)
        self.hist_t += dt
        if self.hist_t >= HIST_EVERY:
            self.hist_t = 0.0
            self._record()

    def pressure(self, kind):
        """Nacisk podaży: suma wag sprzedanych grzybów (1 przez HOLD_TIME, potem słabnie do 0)."""
        total = 0.0
        for ts in self.sales[kind]:
            age = self.t - ts
            if age <= HOLD_TIME:
                total += 1.0
            elif age < HOLD_TIME + RECOVER_TIME:
                total += 1.0 - (age - HOLD_TIME) / RECOVER_TIME
        return total

    def demand_factor(self, kind):
        return FLOOR + (1.0 - FLOOR) * math.exp(-DEMAND_K * self.pressure(kind))

    def price(self, kind):
        return BASE_PRICE[kind] * self.noise[kind] * self.demand_factor(kind)

    def price_int(self, kind):
        return max(1, int(round(self.price(kind))))

    def recent_sales(self, kind):
        """Ile sztuk sprzedano w ciągu ostatnich HOLD_TIME s (pełny efekt podaży)."""
        return sum(1 for ts in self.sales[kind] if self.t - ts <= HOLD_TIME)

    def trend(self, kind):
        """+1 gdy cena rośnie, -1 gdy spada, 0 gdy stoi (w ciągu ostatnich ~18 s)."""
        h = self.history[kind]
        if len(h) <= TREND_LAG:
            return 0
        ref = h[-1 - TREND_LAG]
        cur = self.price(kind)
        if cur > ref * (1 + TREND_EPS):
            return 1
        if cur < ref * (1 - TREND_EPS):
            return -1
        return 0

    # ------------------------------------------------------------ sprzedaż

    def sell(self, kind, backpack, count=1):
        """Sprzedaje do `count` sztuk. Każda następna jest tańsza (rośnie podaż).
        Zwraca (liczba sprzedanych, utarg)."""
        n = min(count, backpack[kind])
        total = 0
        for _ in range(n):
            total += self.price_int(kind)
            self.sales[kind].append(self.t)
        backpack[kind] -= n
        self.money += total
        self.total_earned += total
        self.sold += n
        return n, total

    # ------------------------------------------------------------ ulepszenia

    @property
    def capacity(self):
        return CAPACITIES[self.cap_level]

    def next_capacity(self):
        """(nowa pojemność, koszt) albo None na najwyższym poziomie."""
        if self.cap_level >= len(CAPACITIES) - 1:
            return None
        return CAPACITIES[self.cap_level + 1], CAPACITY_COSTS[self.cap_level]

    def spend(self, amount):
        """Zapłać za przedmiot (np. latarkę). False, gdy brakuje monet."""
        if self.money < amount:
            return False
        self.money -= amount
        return True

    def buy_capacity(self):
        nxt = self.next_capacity()
        if nxt is None or self.money < nxt[1]:
            return False
        self.money -= nxt[1]
        self.cap_level += 1
        return True

    @property
    def has_minimap(self):
        return self.map_level >= 1

    @property
    def mushroom_map(self):
        return self.map_level >= 2

    @property
    def radar(self):
        return self.map_level >= 3

    def next_map_upgrade(self):
        """(opis, koszt) kolejnego ulepszenia minimapy albo None, gdy wszystkie kupione."""
        if self.map_level >= len(MAP_UPGRADES):
            return None
        return MAP_UPGRADES[self.map_level]

    def buy_map_upgrade(self):
        nxt = self.next_map_upgrade()
        if nxt is None or self.money < nxt[1]:
            return False
        self.money -= nxt[1]
        self.map_level += 1
        return True
