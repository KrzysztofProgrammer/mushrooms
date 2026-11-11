"""Zatrucie muchomorem: zamienione kierunki sterowania, pulsujący kolorowy filtr, a po
drugim muchomorze (w dowolnym momencie) - całkowita ciemność, a trzeci kończy grę."""

import math
import random

from settings import SCREEN_W, SCREEN_H
from world import opaque_surface

POISON_TIME = 10.0          # s zamienionego sterowania i kolorowego filtra
BLACKOUT_TIME = 15.0        # s ciemności po drugim muchomorze
SHUFFLE_EVERY = (1.2, 2.5)  # s - co tyle losowo zmieniają się kierunki
COLOR_STEP = 0.8            # s na jeden kolor filtra
COLORS = ((220, 20, 30), (255, 110, 200), (40, 220, 60), (0, 0, 0))   # czerwony, różowy, zielony, czarny
DIRS = ("up", "down", "left", "right")


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Poisoning:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.poison_t = 0.0
        self.blackout_t = 0.0
        self.mapping = {d: d for d in DIRS}
        self.shuffle_t = 0.0
        self.age = 0.0
        self.overlay = opaque_surface((SCREEN_W, SCREEN_H))
        self.eaten = 0              # muchomory zjedzone w tej rozgrywce

    @property
    def poisoned(self):
        return self.poison_t > 0

    @property
    def blackout(self):
        return self.blackout_t > 0

    def eat_toadstool(self):
        """Pierwszy muchomor -> 'poison', drugi -> 'blackout', trzeci -> 'fatal'."""
        self.eaten += 1
        if self.eaten >= 3:
            return "fatal"
        if self.eaten == 2:
            self.blackout_t = BLACKOUT_TIME
            return "blackout"
        self.poison_t = POISON_TIME
        self.age = 0.0
        self._shuffle()
        return "poison"

    def _shuffle(self):
        targets = list(DIRS)
        while True:
            self.rng.shuffle(targets)
            if any(a != b for a, b in zip(DIRS, targets)):
                break
        self.mapping = dict(zip(DIRS, targets))
        self.shuffle_t = self.rng.uniform(*SHUFFLE_EVERY)

    def update(self, dt):
        self.blackout_t = max(0.0, self.blackout_t - dt)
        if not self.poisoned:
            return
        self.age += dt
        self.poison_t -= dt
        self.shuffle_t -= dt
        if self.poison_t <= 0:
            self.poison_t = 0.0
            self.mapping = {d: d for d in DIRS}
        elif self.shuffle_t <= 0:
            self._shuffle()

    def controls(self):
        return self.mapping if self.poisoned else None

    def draw(self, screen):
        if self.poisoned:
            pos = self.age / COLOR_STEP
            i = int(pos) % len(COLORS)
            col = _lerp(COLORS[i], COLORS[(i + 1) % len(COLORS)], pos - int(pos))
            fade = min(1.0, self.poison_t / 0.8, self.age / 0.3)
            pulse = 0.5 + 0.5 * math.sin(self.age * 7.0)
            self.overlay.fill(col)
            self.overlay.set_alpha(int((70 + 130 * pulse) * fade))
            screen.blit(self.overlay, (0, 0))
        if self.blackout:
            self.overlay.fill((0, 0, 0))
            self.overlay.set_alpha(int(255 * min(1.0, self.blackout_t / 1.0, (BLACKOUT_TIME - self.blackout_t) / 0.3)))
            screen.blit(self.overlay, (0, 0))
