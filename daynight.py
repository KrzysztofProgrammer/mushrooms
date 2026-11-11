"""Zegar gry i pora dnia: jedna minuta rzeczywista = jedna godzina w grze.

Noc trwa od 21:00 do 05:00. Godzinę przed nią (20-21) świat łagodnie szarzeje i ciemnieje,
a godzinę po niej (05-06) wraca do kolorów. W nocy cały obraz jest szaro-ciemny, więc nie da się
rozróżnić kolorów grzybów (po nazwie i kształcie też trudno).
"""

import math

import pygame

from settings import SCREEN_W, SCREEN_H
from world import opaque_surface

START_HOUR = 20.0            # godzina startu rozgrywki
SECONDS_PER_HOUR = 60.0      # 1 min rzeczywista = 1 h w grze
DUSK_START = 20.0            # od tej godziny zaczyna się ściemniać
NIGHT_START = 21.0           # pełna noc
NIGHT_END = 5.0              # koniec pełnej nocy
DAWN_END = 6.0               # pełny dzień
GRAY_MAX = 0.94              # jak mocno obraz traci kolory w pełnej nocy (0..1)
DARK_ALPHA = 150             # przyciemnienie w pełnej nocy (0..255)
DARK_COLOR = (10, 14, 26)
BLUR_DOWNSCALE = 7           # nocna mgła: obraz pomniejszony tyle razy i powiększony z powrotem (rozmycie)
BLUR_ALPHA = 0.85            # jak mocno rozmyty obraz przykrywa ostry w pełnej nocy (0..1)
FOG_COLOR = (70, 76, 86)     # szara mgła spłaszczająca kontrast
FOG_ALPHA = 135               # siła mgły w pełnej nocy (0..255)
NIGHT_EXTRA_DIM = 0.10       # w pełnej nocy obraz jest dodatkowo o 10% ciemniejszy


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Clock:
    def __init__(self, start_hour=START_HOUR):
        self.t = start_hour * SECONDS_PER_HOUR      # sekundy od północy dnia 1
        self.gray = opaque_surface((SCREEN_W, SCREEN_H))
        self.dark = opaque_surface((SCREEN_W, SCREEN_H))
        self.dark.fill(DARK_COLOR)
        self.fog = opaque_surface((SCREEN_W, SCREEN_H))
        self.fog.fill(FOG_COLOR)
        self.small = opaque_surface((SCREEN_W // BLUR_DOWNSCALE, SCREEN_H // BLUR_DOWNSCALE))
        self.blurred = opaque_surface((SCREEN_W, SCREEN_H))

    def update(self, dt):
        self.t += dt

    @property
    def hour_float(self):
        return (self.t / SECONDS_PER_HOUR) % 24.0

    @property
    def day(self):
        return int(self.t // (24 * SECONDS_PER_HOUR)) + 1

    @property
    def hour(self):
        return int(self.hour_float)

    @property
    def minute(self):
        return int((self.hour_float % 1.0) * 60)

    def text(self):
        return f"{self.hour:02d}:{self.minute:02d}"

    def night_level(self):
        """0 = dzień, 1 = pełna noc; płynne przejścia 20-21 i 05-06."""
        h = self.hour_float
        if h >= NIGHT_START or h < NIGHT_END:
            return 1.0
        if h >= DUSK_START:
            return _smooth(h - DUSK_START)
        if h < DAWN_END:
            return _smooth(DAWN_END - h)
        return 0.0

    def is_night(self):
        return self.night_level() >= 1.0

    def phase_label(self):
        n = self.night_level()
        h = self.hour_float
        if n >= 1.0:
            return "noc"
        if n > 0:
            return "zmierzch" if h >= DUSK_START else "świt"
        return "dzień"

    def apply(self, screen):
        """Zamienia obraz na szaro-ciemny proporcjonalnie do poziomu nocy."""
        n = self.night_level()
        if n <= 0.005:
            return
        pygame.transform.grayscale(screen, self.gray)
        # mgła: rozmycie (pomniejszenie i powiększenie) + szary welon zacierają kształty i jasność grzybów
        pygame.transform.smoothscale(self.gray, self.small.get_size(), self.small)
        pygame.transform.smoothscale(self.small, (SCREEN_W, SCREEN_H), self.blurred)
        self.gray.set_alpha(int(255 * GRAY_MAX * n))
        screen.blit(self.gray, (0, 0))
        self.blurred.set_alpha(int(255 * BLUR_ALPHA * n))
        screen.blit(self.blurred, (0, 0))
        self.fog.set_alpha(int(FOG_ALPHA * n))
        screen.blit(self.fog, (0, 0))
        self.dark.set_alpha(int(DARK_ALPHA * n))
        screen.blit(self.dark, (0, 0))
        dim = int(255 * (1.0 - NIGHT_EXTRA_DIM * n))
        screen.fill((dim, dim, dim), special_flags=pygame.BLEND_MULT)

    def draw_widget(self, screen, x, y, font_big, font_small, w=206, h=62):
        """Panel z zegarem analogowym i cyfrowym oraz porą dnia."""
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (20, 26, 16, 200), panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, (180, 160, 110, 230), panel.get_rect(), 2, border_radius=8)
        screen.blit(panel, (x, y))

        cx, cy, r = x + 30, y + h // 2, 20
        night = self.night_level()
        face = tuple(int(a + (b - a) * night) for a, b in zip((236, 232, 210), (60, 70, 100)))
        pygame.draw.circle(screen, (40, 30, 20), (cx, cy), r + 2)
        pygame.draw.circle(screen, face, (cx, cy), r)
        for i in range(12):
            a = i * math.tau / 12
            ln = 4 if i % 3 == 0 else 2
            pygame.draw.line(screen, (60, 50, 40), (cx + math.cos(a) * (r - ln), cy + math.sin(a) * (r - ln)),
                             (cx + math.cos(a) * (r - 1), cy + math.sin(a) * (r - 1)), 1)
        hh = (self.hour_float % 12) / 12 * math.tau - math.pi / 2
        mm = (self.hour_float % 1.0) * math.tau - math.pi / 2
        hand = (30, 24, 16) if night < 0.5 else (240, 236, 220)
        pygame.draw.line(screen, hand, (cx, cy), (cx + math.cos(hh) * r * 0.5, cy + math.sin(hh) * r * 0.5), 3)
        pygame.draw.line(screen, hand, (cx, cy), (cx + math.cos(mm) * r * 0.82, cy + math.sin(mm) * r * 0.82), 2)
        pygame.draw.circle(screen, (200, 60, 50), (cx, cy), 2)

        col = (150, 170, 230) if night >= 0.5 else (255, 240, 180)
        txt = font_big.render(self.text(), True, col)
        screen.blit(txt, (x + 60, y + 8))
        sub = font_small.render(f"Dzień {self.day}  -  {self.phase_label()}", True, (200, 200, 180))
        screen.blit(sub, (x + 60, y + 38))
