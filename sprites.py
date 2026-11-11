"""Proceduralnie rysowane grafiki (widok z góry, rzut ortogonalny).

Światło pada z lewej-góry, więc rozjaśnienia są przesunięte w tamtą stronę,
a cienie w prawo-dół.
"""

import math
import random

import pygame


def _shade(color, k):
    return tuple(max(0, min(255, int(c * k))) for c in color)


# --------------------------------------------------------------------------- drzewa

def make_deciduous(radius, rng):
    """Korona drzewa liściastego: kępy liści z rozjaśnieniem od światła."""
    size = int(radius * 2 + 6)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    hue = rng.uniform(0.85, 1.15)
    dark = _shade((34, 82, 34), hue)
    mid = _shade((52, 110, 44), hue)
    light = _shade((80, 142, 58), hue)
    high = _shade((116, 172, 76), hue)

    # sylwetka - pierścień kęp + środek
    clumps = rng.randint(7, 10)
    base_ang = rng.uniform(0, math.tau)
    pygame.draw.circle(surf, dark, (c, c), radius * 0.72)
    for i in range(clumps):
        a = base_ang + i * math.tau / clumps + rng.uniform(-0.2, 0.2)
        rr = radius * rng.uniform(0.36, 0.46)
        d = radius - rr
        pygame.draw.circle(surf, dark, (c + math.cos(a) * d, c + math.sin(a) * d), rr)

    # warstwa środkowa przesunięta ku światłu
    off = -radius * 0.08
    for i in range(clumps):
        a = base_ang + (i + 0.5) * math.tau / clumps
        rr = radius * rng.uniform(0.30, 0.38)
        d = radius * 0.78 - rr
        pygame.draw.circle(surf, mid, (c + off + math.cos(a) * d, c + off + math.sin(a) * d), rr)
    pygame.draw.circle(surf, mid, (c + off, c + off), radius * 0.5)

    # rozjaśnienia od lewej-góry
    for _ in range(5):
        a = rng.uniform(math.pi * 1.0, math.pi * 1.5)
        d = rng.uniform(0.15, 0.45) * radius
        rr = radius * rng.uniform(0.16, 0.26)
        pygame.draw.circle(surf, light, (c + math.cos(a) * d, c + math.sin(a) * d), rr)
    for _ in range(3):
        a = rng.uniform(math.pi * 1.05, math.pi * 1.45)
        d = rng.uniform(0.25, 0.5) * radius
        pygame.draw.circle(surf, high, (c + math.cos(a) * d, c + math.sin(a) * d), radius * 0.09)

    # faktura liści
    for _ in range(int(radius * 2.2)):
        a = rng.uniform(0, math.tau)
        d = math.sqrt(rng.random()) * radius * 0.88
        x, y = c + math.cos(a) * d, c + math.sin(a) * d
        lit = (math.cos(a) * -1 + math.sin(a) * -1) * d / radius  # >0 bliżej światła
        col = high if lit > 0.35 else (light if lit > -0.1 else dark)
        if surf.get_at((int(x), int(y))).a > 0:
            pygame.draw.circle(surf, col, (x, y), rng.uniform(1.0, 2.2))
    return surf


def make_pine(radius, rng):
    """Korona świerka/sosny: gwiaździste warstwy igieł."""
    size = int(radius * 2 + 6)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    hue = rng.uniform(0.85, 1.12)
    layers = [
        (1.00, _shade((24, 62, 40), hue)),
        (0.80, _shade((34, 84, 50), hue)),
        (0.58, _shade((50, 108, 62), hue)),
        (0.36, _shade((74, 134, 78), hue)),
    ]
    spikes = rng.randint(11, 15)
    for scale, col in layers:
        r_out = radius * scale
        r_in = r_out * 0.70
        shift = -(1 - scale) * radius * 0.18
        rot = rng.uniform(0, math.tau)
        pts = []
        for i in range(spikes * 2):
            a = rot + i * math.pi / spikes
            r = (r_out if i % 2 == 0 else r_in) * rng.uniform(0.94, 1.0)
            pts.append((c + shift + math.cos(a) * r, c + shift + math.sin(a) * r))
        pygame.draw.polygon(surf, col, pts)
    # czubek
    pygame.draw.circle(surf, (92, 70, 44), (c - radius * 0.14, c - radius * 0.14), max(2, radius * 0.07))
    return surf


def faded(surface, alpha=95):
    s = surface.copy()
    s.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return s


class TreeSprites:
    """Pula wariantów koron drzew; drzewa w świecie wskazują indeks wariantu."""

    DECIDUOUS_R = (28, 44)
    PINE_R = (22, 36)
    VARIANTS = 10

    def __init__(self, seed):
        rng = random.Random(seed * 31 + 7)
        self.kinds = {}
        for kind, maker, (lo, hi) in (("oak", make_deciduous, self.DECIDUOUS_R),
                                      ("pine", make_pine, self.PINE_R)):
            items = []
            for i in range(self.VARIANTS):
                r = lo + (hi - lo) * i / (self.VARIANTS - 1)
                spr = maker(r, rng).convert_alpha()
                items.append((r, spr, faded(spr)))
            self.kinds[kind] = items

    def radius(self, kind, variant):
        return self.kinds[kind][variant][0]

    def get(self, kind, variant, transparent=False):
        r, spr, fad = self.kinds[kind][variant]
        return fad if transparent else spr


# --------------------------------------------------------------------------- postać

SKIN = (234, 192, 152)
HAIR = (92, 58, 30)
JACKET = (196, 66, 52)
JACKET_DARK = (150, 44, 36)
PANTS = (58, 64, 92)
BOOTS = (60, 42, 28)
PACK = (104, 84, 46)
PACK_DARK = (78, 60, 32)


def draw_player(phase, moving):
    """Postać widziana z góry, zwrócona w górę ekranu (-y). Obracana później."""
    size = 48
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    swing = math.sin(phase) * 6 if moving else 0.0

    # nogi / buty (wysuwają się naprzemiennie)
    pygame.draw.ellipse(s, PANTS, (c - 9, c - 5 - swing * 0.6, 7, 11))
    pygame.draw.ellipse(s, PANTS, (c + 2, c - 5 + swing * 0.6, 7, 11))
    pygame.draw.ellipse(s, BOOTS, (c - 9, c - 8 - swing, 7, 8))
    pygame.draw.ellipse(s, BOOTS, (c + 2, c - 8 + swing, 7, 8))

    # ręce (kołyszą się przeciwnie do nóg)
    for side, sw in ((-1, swing), (1, -swing)):
        hx, hy = c + side * 14, c + 1 + sw * 0.8
        pygame.draw.line(s, JACKET_DARK, (c + side * 11, c), (hx, hy), 6)
        pygame.draw.circle(s, SKIN, (hx, hy - 2 * (1 if sw < 0 else 0)), 3)

    # tułów (barki)
    pygame.draw.ellipse(s, JACKET_DARK, (c - 14, c - 7, 28, 16))
    pygame.draw.ellipse(s, JACKET, (c - 13, c - 7, 26, 14))

    # plecak (z tyłu, czyli +y)
    pygame.draw.rect(s, PACK_DARK, (c - 8, c + 1, 16, 10), border_radius=4)
    pygame.draw.rect(s, PACK, (c - 7, c + 1, 14, 8), border_radius=4)
    pygame.draw.line(s, PACK_DARK, (c - 7, c + 5), (c + 6, c + 5), 1)

    # głowa: twarz z przodu, włosy na czubku
    pygame.draw.circle(s, SKIN, (c, c - 3), 7)
    pygame.draw.circle(s, HAIR, (c, c - 1), 6.5)
    pygame.draw.circle(s, (120, 80, 44), (c - 2, c - 3), 2)
    return s


def make_vignette(w, h, strength=150, color=(10, 20, 10)):
    small_w, small_h = 64, 36
    small = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
    for y in range(small_h):
        for x in range(small_w):
            dx = (x + 0.5) / small_w * 2 - 1
            dy = (y + 0.5) / small_h * 2 - 1
            d = math.sqrt(dx * dx + dy * dy) / math.sqrt(2)
            a = max(0.0, (d - 0.45) / 0.55) ** 1.8
            small.set_at((x, y), (*color, int(a * strength)))
    return pygame.transform.smoothscale(small, (w, h))
