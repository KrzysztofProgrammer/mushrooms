"""Pogoda: deszcz pojawiający się w losowych momentach i wilgotność gruntu.

intensity - siła opadu 0..1 (narasta i słabnie płynnie)
wetness   - wilgotność gruntu 0..1 (rośnie w czasie deszczu, potem powoli schnie)
"""

import math
import random

import pygame

from settings import SCREEN_W, SCREEN_H, TILE
from world import opaque_surface

FIRST_RAIN = (40, 80)        # s do pierwszego deszczu
BETWEEN_RAINS = (60, 120)    # s przerwy między opadami
RAIN_DURATION = (25, 45)     # s trwania opadu
RAMP = 4.0                   # s narastania / słabnięcia
WET_TIME = 12.0              # s deszczu do pełnego przemoczenia
DRY_TIME = 75.0              # s schnięcia od pełnej wilgotności

MAX_DROPS = 520
WIND = 70.0                  # px/s - krople lecą lekko ukośnie


class Weather:
    def __init__(self, world, seed):
        self.rng = random.Random(seed * 17 + 11)
        self.raining = False
        self.intensity = 0.0
        self.target = 0.0
        self.wetness = 0.0
        self.timer = self.rng.uniform(*FIRST_RAIN)
        self.drops = []          # [x, y, długość, prędkość, jasna?]
        self.splashes = []       # [x, y, wiek]
        self.splash_acc = 0.0
        self.dark = opaque_surface((SCREEN_W, SCREEN_H))
        self.dark.fill((24, 34, 52))
        self.wet_tint = opaque_surface((SCREEN_W, SCREEN_H))
        self.wet_tint.fill((14, 22, 30))
        self._make_puddles(world)

    # ------------------------------------------------------------ logika

    def start_rain(self):
        self.raining = True
        self.target = self.rng.uniform(0.6, 1.0)
        self.timer = self.rng.uniform(*RAIN_DURATION)

    def stop_rain(self):
        self.raining = False
        self.target = 0.0
        self.timer = self.rng.uniform(*BETWEEN_RAINS)

    def update(self, dt):
        """Zwraca zdarzenie 'start' / 'stop' w chwili zmiany pogody, inaczej None."""
        event = None
        self.timer -= dt
        if self.timer <= 0:
            if self.raining:
                self.stop_rain()
                event = "stop"
            else:
                self.start_rain()
                event = "start"

        step = dt / RAMP
        if self.intensity < self.target:
            self.intensity = min(self.target, self.intensity + step)
        else:
            self.intensity = max(self.target, self.intensity - step)

        if self.intensity > 0.25:
            self.wetness = min(1.0, self.wetness + dt / WET_TIME * self.intensity)
        else:
            self.wetness = max(0.0, self.wetness - dt / DRY_TIME)

        self._update_particles(dt)
        return event

    def _update_particles(self, dt):
        rng = self.rng
        want = int(MAX_DROPS * self.intensity)
        alive = []
        for d in self.drops:
            d[0] += WIND * dt
            d[1] += d[3] * dt
            if d[1] < SCREEN_H + 20 and d[0] < SCREEN_W + 20:
                alive.append(d)
        self.drops = alive
        while len(self.drops) < want:
            self.drops.append([rng.uniform(-80, SCREEN_W), rng.uniform(-SCREEN_H * 0.3, -5),
                               rng.uniform(9, 18), rng.uniform(650, 900), rng.random() < 0.35])
        if len(self.drops) > want:                       # przy słabnięciu znikają stopniowo
            self.drops = self.drops[:max(want, len(self.drops) - 6)]

        self.splash_acc += dt * 90 * self.intensity
        while self.splash_acc >= 1:
            self.splash_acc -= 1
            self.splashes.append([rng.uniform(0, SCREEN_W), rng.uniform(0, SCREEN_H), 0.0])
        for s in self.splashes:
            s[2] += dt
        self.splashes = [s for s in self.splashes if s[2] < 0.35]

    # ------------------------------------------------------------ kałuże

    def _make_puddles(self, world):
        """Kałuże w zagłębieniach drogi i ścieżki - widoczne tylko na mokrej ziemi."""
        rng = random.Random(world.seed * 3 + 1)
        self.puddle_sprites = []
        for _ in range(6):
            w, h = rng.randint(26, 54), rng.randint(14, 26)
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(s, (70, 64, 48, 150), s.get_rect())
            pygame.draw.ellipse(s, (96, 116, 132, 210), s.get_rect().inflate(-4, -4))
            pygame.draw.ellipse(s, (150, 170, 186, 200), (w * 0.2, h * 0.25, w * 0.35, h * 0.25))
            self.puddle_sprites.append(s)
        self.puddles = []        # (x, y, wariant)
        for p in world.paths:
            pts = p.points
            for i in range(0, len(pts) - 1, 3):
                if rng.random() > (0.35 if p.kind == "road" else 0.2):
                    continue
                x0, y0 = pts[i]
                x1, y1 = pts[i + 1]
                dx, dy = x1 - x0, y1 - y0
                ln = math.hypot(dx, dy) or 1.0
                off = rng.uniform(-0.55, 0.55) * p.radius
                x = (x0 - dy / ln * off) * TILE
                y = (y0 + dx / ln * off) * TILE
                if 0 < x < world.pw and 0 < y < world.ph:
                    self.puddles.append((x, y, rng.randrange(len(self.puddle_sprites))))

    # ------------------------------------------------------------ rysowanie

    def draw_ground(self, screen, cam_x, cam_y):
        """Ciemniejsza, mokra ziemia i kałuże - rysowane zaraz po tle."""
        if self.wetness <= 0.01:
            return
        self.wet_tint.set_alpha(int(70 * self.wetness))
        screen.blit(self.wet_tint, (0, 0))
        alpha = int(255 * min(1.0, self.wetness * 1.4))
        for s in self.puddle_sprites:
            s.set_alpha(alpha)
        for x, y, v in self.puddles:
            sx, sy = x - cam_x, y - cam_y
            if -60 < sx < SCREEN_W + 60 and -40 < sy < SCREEN_H + 40:
                spr = self.puddle_sprites[v]
                screen.blit(spr, (sx - spr.get_width() / 2, sy - spr.get_height() / 2))

    def draw_sky(self, screen):
        """Przyciemnienie, krople i rozbryzgi - nad koronami drzew."""
        if self.intensity <= 0.01 and not self.drops:
            return
        self.dark.set_alpha(int(85 * self.intensity))
        screen.blit(self.dark, (0, 0))
        dx_per_len = WIND / 800.0
        for x, y, ln, sp, light in self.drops:
            col = (190, 205, 230) if light else (140, 160, 190)
            pygame.draw.line(screen, col, (x, y), (x - ln * dx_per_len, y - ln))
        for x, y, age in self.splashes:
            k = age / 0.35
            r = 2 + k * 7
            c = int(200 - 90 * k)
            pygame.draw.ellipse(screen, (c, c + 10, c + 30), (x - r, y - r * 0.4, 2 * r, r * 0.8), 1)

    def label(self):
        if self.intensity > 0.05 and self.raining:
            return "deszcz"
        if self.intensity > 0.05:
            return "przestaje padać"
        if self.wetness > 0.05:
            return f"mokro ({int(self.wetness * 100)}%)"
        return "sucho"
