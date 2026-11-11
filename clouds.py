"""Obłok zarodników z purchawki: przez 10 s zasłania widok graczowi i niedźwiedziom."""

import math
import random

import pygame

from settings import SCREEN_W, SCREEN_H
from world import opaque_surface

DURATION = 10.0        # s
RADIUS = 230           # px - promień obłoku
GROW_TIME = 0.6        # s - wybuch obłoku
FADE_TIME = 2.0        # s - rozwiewanie na końcu
COLOR = (206, 198, 168)

_fog = None


def _fog_overlay():
    global _fog
    if _fog is None:
        _fog = opaque_surface((SCREEN_W, SCREEN_H))
        _fog.fill(COLOR)
    return _fog


def _make_sprite(rng):
    size = RADIUS * 2 + 40
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    blob = pygame.Surface((size, size), pygame.SRCALPHA)
    for _ in range(46):
        a = rng.uniform(0, math.tau)
        d = math.sqrt(rng.random()) * RADIUS * 0.72
        r = rng.uniform(0.28, 0.45) * RADIUS
        shade = rng.uniform(0.85, 1.05)
        col = tuple(min(255, int(v * shade)) for v in COLOR)
        blob.fill((0, 0, 0, 0))
        pygame.draw.circle(blob, (*col, rng.randint(70, 120)), (c + math.cos(a) * d, c + math.sin(a) * d), r)
        surf.blit(blob, (0, 0))
    return surf


class SporeCloud:
    def __init__(self, x, y, seed):
        self.x, self.y = x, y
        self.t = 0.0
        self.sprite = _make_sprite(random.Random(seed))

    @property
    def alive(self):
        return self.t < DURATION

    def strength(self):
        """0..1 - jak bardzo obłok zasłania (rośnie przy wybuchu, słabnie przy rozwiewaniu)."""
        if self.t < GROW_TIME:
            return self.t / GROW_TIME
        return max(0.0, min(1.0, (DURATION - self.t) / FADE_TIME))

    def radius(self):
        return RADIUS * (0.3 + 0.7 * min(1.0, self.t / GROW_TIME)) * (1 + 0.1 * self.t / DURATION)

    def contains(self, x, y, k=0.85):
        return self.strength() > 0.3 and (x - self.x) ** 2 + (y - self.y) ** 2 < (self.radius() * k) ** 2

    def blocks(self, x0, y0, x1, y1):
        """Czy odcinek przechodzi przez gęstą część obłoku."""
        if self.strength() <= 0.3:
            return False
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((self.x - x0) * dx + (self.y - y0) * dy) / l2))
        px, py = x0 + t * dx, y0 + t * dy
        return (self.x - px) ** 2 + (self.y - py) ** 2 < (self.radius() * 0.75) ** 2

    def update(self, dt):
        self.t += dt

    def draw(self, screen, cam_x, cam_y):
        r = self.radius()
        scale = r / RADIUS
        spr = self.sprite if abs(scale - 1) < 0.02 else pygame.transform.smoothscale_by(self.sprite, scale)
        # kłęby lekko falują
        wob = math.sin(self.t * 1.7) * 6
        spr.set_alpha(int(255 * self.strength()))
        for ox, oy in ((wob, 0), (-wob * 0.6, wob * 0.5)):
            screen.blit(spr, spr.get_rect(center=(self.x - cam_x + ox, self.y - cam_y + oy)))


def draw_fog_inside(screen, clouds, x, y):
    """Gdy gracz stoi w obłoku, prawie nic nie widać."""
    k = max((c.strength() for c in clouds if c.contains(x, y, 1.0)), default=0.0)
    if k > 0:
        fog = _fog_overlay()
        fog.set_alpha(int(225 * k))
        screen.blit(fog, (0, 0))


def sight_blocked(clouds, x0, y0, x1, y1):
    return any(c.contains(x1, y1) or c.contains(x0, y0) or c.blocks(x0, y0, x1, y1) for c in clouds)
