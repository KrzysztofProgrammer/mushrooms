"""Grzyby: rosną w lesie w prześwitach między koronami, odrastają z czasem."""

import math
import random

import pygame

from settings import TILE
from world import GRASS, SpatialHash

# kolejność = kolejność w plecaku na HUD
KINDS = ("borowik", "podgrzybek", "kurka")
NAMES = {"borowik": "Borowik", "podgrzybek": "Podgrzybek", "kurka": "Kurka"}
WEIGHTS = {"borowik": 0.2, "podgrzybek": 0.35, "kurka": 0.45}
PUFFBALL = "purchawka"   # niejadalna; nadepnięta wybucha obłokiem zarodników (nie trafia do plecaka)
PUFFBALL_CHANCE = 0.07
TOADSTOOL = "muchomor"   # trujący; nadepnięty miesza sterowanie (nie trafia do plecaka)
TOADSTOOL_CHANCE = 0.07

START_COUNT = 140
MAX_COUNT = 160
RESPAWN_EVERY = 3.0      # s
RAIN_EXTRA_MAX = 45      # na mokrej ziemi w lesie może być tyle grzybów więcej
RAIN_GROWTH = 2.5        # na mokrej ziemi grzyby odrastają do (1 + RAIN_GROWTH) razy szybciej
RAIN_BURST = 20          # wysyp grzybów zaraz po deszczu
DECAY_EVERY = 1.5        # s - gdy wyschnie, nadmiar grzybów stopniowo znika (poza ekranem)
PICKUP_DIST = 20


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _cap(surf, c, r, color, rng):
    """Kapelusz widziany z góry: obrzeże, kapelusz, połysk od lewej-góry."""
    pygame.draw.circle(surf, _shade(color, 0.7), c, r + 1)
    pygame.draw.circle(surf, color, c, r)
    hl = pygame.Rect(0, 0, r * 1.1, r * 0.8)
    hl.center = (c[0] - r * 0.3, c[1] - r * 0.35)
    pygame.draw.ellipse(surf, _shade(color, 1.35), hl)
    pygame.draw.circle(surf, (255, 255, 240), (c[0] - r * 0.4, c[1] - r * 0.45), max(1, r * 0.15))


def make_mushroom_sprite(kind, rng):
    size = 26
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    pygame.draw.ellipse(s, (0, 0, 0, 80), (c - 7, c - 3, 16, 10))      # cień
    if kind == "borowik":
        pygame.draw.ellipse(s, (226, 214, 180), (c - 3, c + 1, 7, 6))  # trzon spod kapelusza
        _cap(s, (c - 1, c - 1), rng.uniform(6.5, 8), _shade((128, 78, 38), rng.uniform(0.9, 1.1)), rng)
    elif kind == "podgrzybek":
        pygame.draw.ellipse(s, (196, 170, 120), (c - 3, c + 1, 6, 6))
        _cap(s, (c - 1, c - 1), rng.uniform(5.5, 7), _shade((76, 52, 34), rng.uniform(0.9, 1.1)), rng)
    elif kind == TOADSTOOL:
        r = rng.uniform(7, 8.5)
        _cap(s, (c - 1, c - 1), r, (214, 32, 26), rng)
        for _ in range(8):                                            # białe kropki
            a, d = rng.uniform(0, math.tau), rng.uniform(r * 0.15, r * 0.8)
            pygame.draw.circle(s, (250, 246, 236), (c - 1 + math.cos(a) * d, c - 1 + math.sin(a) * d),
                               rng.uniform(1.0, 1.8))
    elif kind == PUFFBALL:
        r = rng.uniform(6.5, 8)
        pygame.draw.circle(s, (170, 160, 130), (c - 1, c - 1), r + 1)
        pygame.draw.circle(s, (236, 230, 208), (c - 1, c - 1), r)
        pygame.draw.circle(s, (252, 250, 238), (c - 3, c - 3), r * 0.45)
        for _ in range(9):                                            # brodawki
            a, d = rng.uniform(0, math.tau), rng.uniform(0, r * 0.8)
            pygame.draw.circle(s, (196, 186, 156), (c - 1 + math.cos(a) * d, c - 1 + math.sin(a) * d), 0.9)
    else:  # kurki rosną w kępkach
        for _ in range(rng.randint(2, 4)):
            p = (c + rng.uniform(-5, 5), c + rng.uniform(-5, 4))
            r = rng.uniform(2.8, 4.2)
            col = _shade((236, 170, 36), rng.uniform(0.92, 1.08))
            pygame.draw.circle(s, _shade(col, 0.75), p, r + 1)
            pygame.draw.circle(s, col, p, r)
            pygame.draw.circle(s, _shade(col, 0.82), p, r * 0.4)       # lejkowaty środek
    return s


class Mushroom:
    __slots__ = ("x", "y", "kind", "variant")

    def __init__(self, x, y, kind, variant):
        self.x, self.y, self.kind, self.variant = x, y, kind, variant


class MushroomField:
    VARIANTS = 4

    def __init__(self, world, seed):
        self.world = world
        self.rng = random.Random(seed * 7 + 3)
        self.items = []
        self.hash = SpatialHash(TILE * 2)
        self.sprites = {k: [make_mushroom_sprite(k, self.rng).convert_alpha() for _ in range(self.VARIANTS)]
                        for k in KINDS + (PUFFBALL, TOADSTOOL)}
        self.icons = {k: pygame.transform.smoothscale_by(v[0], 1.6) for k, v in self.sprites.items()}
        self.timer = 0.0
        self.decay_timer = 0.0
        for _ in range(START_COUNT):
            self.spawn()

    def _find_spot(self, avoid=None, min_dist=0.0):
        w, rng = self.world, self.rng
        for _ in range(80):
            tx, ty = rng.randrange(w.w), rng.randrange(w.h)
            if w.tiles[ty][tx] != GRASS or w.path_norm[ty][tx] < 1.4 or w.forest[ty][tx] < 0.3:
                continue
            x, y = (tx + rng.random()) * TILE, (ty + rng.random()) * TILE
            if avoid is not None and math.hypot(x - avoid[0], y - avoid[1]) < min_dist:
                continue
            if not w.is_open(x, y, 10):
                continue
            near_tree, hidden = False, False
            for t in w.tree_hash.query(x - 60, y - 60, x + 60, y + 60):
                d = math.hypot(t.x - x, t.y - y)
                if d < t.canopy_r * 0.85:          # pod koroną nie byłoby go widać
                    hidden = True
                    break
                if d < t.canopy_r + 34:
                    near_tree = True
            if hidden or (not near_tree and rng.random() < 0.85):
                continue
            if self.hash.query(x - 30, y - 30, x + 30, y + 30):
                continue
            return x, y
        return None

    def spawn(self, avoid=None, min_dist=0.0):
        spot = self._find_spot(avoid, min_dist)
        if spot is None:
            return
        r, acc = self.rng.random(), 0.0
        kind = KINDS[-1]
        for k in KINDS:
            acc += WEIGHTS[k]
            if r < acc:
                kind = k
                break
        r = self.rng.random()
        if r < PUFFBALL_CHANCE:
            kind = PUFFBALL
        elif r < PUFFBALL_CHANCE + TOADSTOOL_CHANCE:
            kind = TOADSTOOL
        m = Mushroom(spot[0], spot[1], kind, self.rng.randrange(self.VARIANTS))
        self.items.append(m)
        self.hash.add(m)

    def remove(self, m):
        if m in self.items:
            self.items.remove(m)
            self.hash.remove(m)
            return True
        return False

    def alive(self, m):
        return m in self.items

    def nearest(self, x, y, radius, exclude=None, edible=False, special_only=False, skip_kinds=()):
        best, best_d = None, radius * radius
        for m in self.hash.query(x - radius, y - radius, x + radius, y + radius):
            if exclude and id(m) in exclude:
                continue
            if edible and m.kind in (PUFFBALL, TOADSTOOL):
                continue
            if m.kind in skip_kinds:
                continue
            if special_only and m.kind in KINDS:      # pełny plecak: jadalne zostają na ziemi
                continue
            d = (m.x - x) ** 2 + (m.y - y) ** 2
            if d < best_d:
                best, best_d = m, d
        return best

    def burst(self, count, player_pos):
        """Wysyp grzybów po deszczu (poza ekranem gracza)."""
        for _ in range(count):
            self.spawn(avoid=player_pos, min_dist=750)

    def update(self, dt, player_pos, wetness=0.0):
        """Odrastanie grzybów - zawsze poza zasięgiem wzroku gracza; wilgoć przyspiesza."""
        self.timer += dt * (1.0 + RAIN_GROWTH * wetness)
        limit = MAX_COUNT + int(RAIN_EXTRA_MAX * wetness)
        while self.timer >= RESPAWN_EVERY:
            self.timer -= RESPAWN_EVERY
            if len(self.items) < limit:
                self.spawn(avoid=player_pos, min_dist=800)
        # po wyschnięciu nadmiar grzybów (z wysypu) powoli przepada
        if len(self.items) > limit:
            self.decay_timer += dt
            if self.decay_timer >= DECAY_EVERY:
                self.decay_timer = 0.0
                px, py = player_pos
                far = [m for m in self.items if (m.x - px) ** 2 + (m.y - py) ** 2 > 750 ** 2]
                if far:
                    self.remove(self.rng.choice(far))
        else:
            self.decay_timer = 0.0

    def pick(self, x, y, backpack_full=False):
        m = self.nearest(x, y, PICKUP_DIST, special_only=backpack_full)
        if m is not None:
            self.remove(m)
        return m

    def draw(self, screen, cam_x, cam_y, w, h):
        for m in self.hash.query(cam_x - 20, cam_y - 20, cam_x + w + 20, cam_y + h + 20):
            spr = self.sprites[m.kind][m.variant]
            screen.blit(spr, (m.x - spr.get_width() / 2 - cam_x, m.y - spr.get_height() / 2 - cam_y))
