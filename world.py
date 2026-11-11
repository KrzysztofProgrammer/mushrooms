"""Proceduralny świat: las, droga przez las, boczna ścieżka do polany ze stawem."""

import math
import random
from collections import OrderedDict

import pygame

from noise import ValueNoise
from settings import (
    TILE, CHUNK, WORLD_W, WORLD_H, MAX_CACHED_CHUNKS,
    GRASS_LIGHT, GRASS_DRY, FOREST_FLOOR, SHORE, WATER_SHALLOW, WATER_DEEP,
    ROAD_SHOULDER, ROAD_CORE, ROAD_RUT, TRAIL_SHOULDER, TRAIL_CORE,
)
from sprites import TreeSprites

GRASS, ROAD, WATER = 0, 1, 2

MUD_SLOW_PLAYER = 0.35   # na całkiem mokrej ziemi gracz traci 35% prędkości
MUD_SLOW_BEAR = 0.2      # niedźwiedź radzi sobie w błocie lepiej


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def opaque_surface(size):
    """Powierzchnia 32-bit BEZ kanału alfa.

    Na macOS ekran ma format ARGB i convert() przenosi go na tło; wtedy nałożenie
    przezroczystej warstwy (np. cieni) zeruje alfę, a kolejne blity z alfą
    (winieta) nadpisują kolor. Jawne maski XRGB eliminują ten problem.
    """
    return pygame.Surface(size, 0, 32, (0xFF0000, 0x00FF00, 0x0000FF, 0))


def wrap_angle(a):
    return (a + math.pi) % math.tau - math.pi


# --------------------------------------------------------------------------- obiekty

class Tree:
    __slots__ = ("x", "y", "r", "canopy_r", "kind", "variant", "phase")

    def __init__(self, x, y, kind, variant, canopy_r, phase):
        self.x, self.y = x, y
        self.kind, self.variant = kind, variant
        self.canopy_r = canopy_r
        self.r = max(6.0, canopy_r * 0.22)      # promień pnia = kolizja
        self.phase = phase


class Rock:
    __slots__ = ("x", "y", "r", "collide", "stretch")

    def __init__(self, x, y, r, stretch):
        self.x, self.y, self.r = x, y, r
        self.collide = r >= 8
        self.stretch = stretch


class Bush:
    __slots__ = ("x", "y", "r", "blobs", "berries")

    def __init__(self, x, y, r, rng):
        self.x, self.y, self.r = x, y, r
        self.blobs = []
        for _ in range(rng.randint(4, 7)):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(0, r * 0.5)
            self.blobs.append((math.cos(a) * d, math.sin(a) * d, r * rng.uniform(0.45, 0.65)))
        self.berries = rng.random() < 0.25


class Path:
    def __init__(self, points, radius, kind):
        self.points = points          # w kaflach (float)
        self.radius = radius          # półszerokość w kaflach
        self.kind = kind              # "road" | "trail"


class Solid:
    """Niewidoczna, okrągła przeszkoda (kolizja stoiska). Nie jest rysowana w tle."""
    __slots__ = ("x", "y", "r")

    def __init__(self, x, y, r):
        self.x, self.y, self.r = x, y, r


STALL_REACH = 2.6        # w kaflach od końca ścieżki
STALL_CLEAR = 150        # px - w tym promieniu od straganu nie rosną drzewa, krzaki ani kamienie


class SpatialHash:
    def __init__(self, cell):
        self.cell = cell
        self.buckets = {}

    def add(self, obj):
        key = (int(obj.x // self.cell), int(obj.y // self.cell))
        self.buckets.setdefault(key, []).append(obj)

    def remove(self, obj):
        key = (int(obj.x // self.cell), int(obj.y // self.cell))
        b = self.buckets.get(key)
        if b and obj in b:
            b.remove(obj)

    def query(self, x0, y0, x1, y1):
        c = self.cell
        out = []
        for cy in range(int(y0 // c), int(y1 // c) + 1):
            for cx in range(int(x0 // c), int(x1 // c) + 1):
                b = self.buckets.get((cx, cy))
                if b:
                    out.extend(b)
        return out


# --------------------------------------------------------------------------- świat

class World:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.w, self.h = WORLD_W, WORLD_H
        self.pw, self.ph = WORLD_W * TILE, WORLD_H * TILE

        self.tree_sprites = TreeSprites(seed)
        self.paths = []
        self.clearings = []            # (cx, cy, r) w kaflach
        self.trees = []
        self.rocks = []
        self.bushes = []
        self.tree_hash = SpatialHash(TILE * 2)
        self.rock_hash = SpatialHash(TILE * 2)
        self.bush_hash = SpatialHash(TILE * 2)
        self.solids = SpatialHash(TILE * 2)     # kolizje straganu
        self.stall = None                       # (x, y) w pikselach - środek straganu
        self.chunks = OrderedDict()
        self.wetness = 0.0             # 0..1, ustawiane przez pogodę
        self.clouds = []               # obłoki purchawek (lista z Game)

        self._gen_fields()
        self._gen_paths()
        self._gen_water()
        self._gen_ground_colors()
        self._gen_trees()
        self._gen_small_objects()

        sx, sy = next((p for p in self.paths[0].points if p[0] >= 4), self.paths[0].points[0])
        self.spawn = (sx * TILE, sy * TILE)

    # ------------------------------------------------------------ generowanie

    def _gen_fields(self):
        W, H = self.w, self.h
        dn, mn, wn, vn = (ValueNoise(self.seed + k) for k in (11, 23, 37, 41))
        self.forest = [[0.0] * W for _ in range(H)]
        self.mix = [[0.0] * W for _ in range(H)]
        self.wet = [[0.0] * W for _ in range(H)]
        self.var = [[0.0] * W for _ in range(H)]
        for ty in range(H):
            frow, mrow, wrow, vrow = self.forest[ty], self.mix[ty], self.wet[ty], self.var[ty]
            for tx in range(W):
                frow[tx] = smoothstep(0.34, 0.58, dn.fbm(tx / 26.0, ty / 26.0, 4))
                mrow[tx] = mn.fbm(tx / 34.0, ty / 34.0, 3)
                wrow[tx] = wn.fbm(tx / 18.0, ty / 18.0, 3)
                vrow[tx] = vn.fbm(tx / 4.0, ty / 4.0, 2)
        self.tiles = [[GRASS] * W for _ in range(H)]
        self.path_norm = [[99.0] * W for _ in range(H)]   # odległość od osi drogi / promień

    def _walk(self, x, y, heading, target, steps, wander, pull, margin, free_x, max_dev):
        """Losowy, gładki spacer - z niego powstaje oś drogi."""
        rng, W, H = self.rng, self.w, self.h
        step = 0.5
        pts, turn = [], 0.0
        for _ in range(steps):
            pts.append((x, y))
            vx, vy = math.cos(target), math.sin(target)
            if y < margin:
                vy += (margin - y) / margin * 2.0
            elif y > H - margin:
                vy -= (y - (H - margin)) / margin * 2.0
            if not free_x:
                if x < margin:
                    vx += (margin - x) / margin * 2.0
                elif x > W - margin:
                    vx -= (x - (W - margin)) / margin * 2.0
            desired = math.atan2(vy, vx)
            turn = turn * 0.9 + rng.gauss(0, wander)
            heading += turn + wrap_angle(desired - heading) * pull
            # bez pętli: kierunek nie odbiega za bardzo od docelowego
            dev = wrap_angle(heading - target)
            if abs(dev) > max_dev:
                heading = target + math.copysign(max_dev, dev)
                turn *= -0.5
            x += math.cos(heading) * step
            y += math.sin(heading) * step
            if x < -3 or x > W + 3 or y < -3 or y > H + 3:
                pts.append((x, y))
                break
        return pts

    def _stamp_path(self, path):
        r = path.radius
        reach = r * 4 + 2
        W, H = self.w, self.h
        norm = self.path_norm
        for px, py in path.points:
            for ty in range(max(0, int(py - reach)), min(H, int(py + reach) + 1)):
                row = norm[ty]
                dy = ty + 0.5 - py
                for tx in range(max(0, int(px - reach)), min(W, int(px + reach) + 1)):
                    dx = tx + 0.5 - px
                    d = math.sqrt(dx * dx + dy * dy) / r
                    if d < row[tx]:
                        row[tx] = d

    def _gen_paths(self):
        rng, W, H = self.rng, self.w, self.h
        # główna droga z zachodu na wschód
        y0 = rng.uniform(0.35, 0.65) * H
        main = self._walk(-3.0, y0, 0.0, 0.0, W * 6, wander=0.02, pull=0.02, margin=22, free_x=True,
                          max_dev=1.15)
        self.paths.append(Path(main, 1.6, "road"))

        # boczna ścieżka do polany
        idx = int(len(main) * rng.uniform(0.38, 0.55))
        sx, sy = main[idx]
        target = -math.pi / 2 if sy > H / 2 else math.pi / 2
        trail = self._walk(sx, sy, target, target, int(44 / 0.5), wander=0.035, pull=0.05,
                           margin=12, free_x=False, max_dev=1.1)
        self.paths.append(Path(trail, 0.85, "trail"))
        ex, ey = trail[-1]
        self._place_stall(trail, target)
        cx = max(12, min(W - 12, ex + math.cos(target) * 5))
        cy = max(12, min(H - 12, ey + math.sin(target) * 5))
        self.clearings.append((cx, cy, 8.5))

        for p in self.paths:
            self._stamp_path(p)
        for ty in range(H):
            for tx in range(W):
                if self.path_norm[ty][tx] <= 1.0:
                    self.tiles[ty][tx] = ROAD

    def _place_stall(self, trail, target):
        """Stragan stoi na końcu ścieżki. Ścieżka jest przedłużona do niego i kończy się placykiem."""
        ex, ey = trail[-1]
        bx, by = trail[max(0, len(trail) - 7)]
        dx, dy = ex - bx, ey - by
        ln = math.hypot(dx, dy)
        dx, dy = (dx / ln, dy / ln) if ln > 1e-6 else (math.cos(target), math.sin(target))
        sx = max(5.0, min(self.w - 5.0, ex + dx * STALL_REACH))
        sy = max(5.0, min(self.h - 5.0, ey + dy * STALL_REACH))
        steps = max(1, int(math.hypot(sx - ex, sy - ey) / 0.5))
        for i in range(1, steps + 1):
            trail.append((ex + (sx - ex) * i / steps, ey + (sy - ey) * i / steps))
        for i in range(-3, 4):                     # placyk pod straganem
            for j in range(-3, 4):
                if math.hypot(i, j) * 0.5 <= 1.5:
                    trail.append((sx + i * 0.5, sy + j * 0.5))
        self.stall = (sx * TILE, sy * TILE)
        for k in range(-2, 3):
            self.solids.add(Solid(self.stall[0] + k * 20, self.stall[1], 26))

    def near_stall(self, x, y, r=STALL_CLEAR):
        return self.stall is not None and math.hypot(x - self.stall[0], y - self.stall[1]) < r

    def clearing_factor(self, tx, ty):
        """0 w środku polany, 1 poza nią."""
        f = 1.0
        for cx, cy, r in self.clearings:
            d = math.hypot(tx + 0.5 - cx, ty + 0.5 - cy) / r
            f = min(f, smoothstep(0.75, 1.15, d))
        return f

    def _gen_water(self):
        W, H, rng = self.w, self.h, self.rng
        # staw na polanie
        cx, cy, r = self.clearings[0]
        a = rng.uniform(0, math.tau)
        pcx, pcy = cx + math.cos(a) * 2.4, cy + math.sin(a) * 2.4
        for ty in range(H):
            for tx in range(W):
                if self.path_norm[ty][tx] < 2.2:
                    continue
                d = math.hypot(tx + 0.5 - pcx, ty + 0.5 - pcy) + (self.var[ty][tx] - 0.5) * 2.0
                lake = self.wet[ty][tx] > 0.745 and self.path_norm[ty][tx] > 4.0 and self.clearing_factor(tx, ty) > 0.99
                if d < 2.9 or lake:
                    self.tiles[ty][tx] = WATER
        # wokół straganu nie ma wody
        for ty in range(H):
            for tx in range(W):
                if self.tiles[ty][tx] == WATER and self.near_stall((tx + 0.5) * TILE, (ty + 0.5) * TILE, 3.6 * TILE):
                    self.tiles[ty][tx] = GRASS

    def _gen_ground_colors(self):
        W, H = self.w, self.h
        self.ground = [[None] * W for _ in range(H)]
        for ty in range(H):
            for tx in range(W):
                f = self.forest[ty][tx] * self.clearing_factor(tx, ty)
                col = lerp_color(GRASS_LIGHT, FOREST_FLOOR, 0.25 + 0.75 * f)
                n = self.path_norm[ty][tx]
                if n < 2.6:
                    col = lerp_color(col, GRASS_DRY, (2.6 - n) / 2.6 * 0.55)
                v = (self.var[ty][tx] - 0.5) * 34
                col = tuple(max(0, min(255, int(c + v))) for c in col)
                if self.tiles[ty][tx] == WATER:
                    col = SHORE
                self.ground[ty][tx] = col

    def _gen_trees(self):
        rng, W, H = self.rng, self.w, self.h
        ts = self.tree_sprites
        for ty in range(H):
            for tx in range(W):
                if self.tiles[ty][tx] != GRASS:
                    continue
                n = self.path_norm[ty][tx]
                if n < 1.55:
                    continue
                f = self.forest[ty][tx]
                p = 0.07 + 0.45 * f
                if n < 3.3:
                    p *= (n - 1.55) / 1.75 * 0.8
                p *= self.clearing_factor(tx, ty)
                if rng.random() >= p:
                    continue
                x = (tx + rng.uniform(0.15, 0.85)) * TILE
                y = (ty + rng.uniform(0.15, 0.85)) * TILE
                if self._near_water(x, y, 0.6 * TILE) or self.near_stall(x, y, STALL_CLEAR + 30):
                    continue
                pine_chance = smoothstep(0.38, 0.62, self.mix[ty][tx]) * 0.85 + 0.08
                kind = "pine" if rng.random() < pine_chance else "oak"
                variant = rng.randrange(ts.VARIANTS)
                tree = Tree(x, y, kind, variant, ts.radius(kind, variant), rng.uniform(0, math.tau))
                min_d = max(26.0, tree.canopy_r * 0.8)
                ok = True
                for o in self.tree_hash.query(x - 50, y - 50, x + 50, y + 50):
                    if (o.x - x) ** 2 + (o.y - y) ** 2 < max(min_d, o.canopy_r * 0.8) ** 2:
                        ok = False
                        break
                if ok:
                    self.trees.append(tree)
                    self.tree_hash.add(tree)

    def _near_water(self, x, y, r):
        for ox, oy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)):
            if self.tile_at_px(x + ox, y + oy) == WATER:
                return True
        return False

    def _gen_small_objects(self):
        rng, W, H = self.rng, self.w, self.h
        for ty in range(H):
            for tx in range(W):
                if self.tiles[ty][tx] != GRASS:
                    continue
                n = self.path_norm[ty][tx]
                f = self.forest[ty][tx]
                x = (tx + rng.random()) * TILE
                y = (ty + rng.random()) * TILE
                if self.near_stall(x, y):
                    continue
                if n > 1.35 and rng.random() < 0.009 and not self._near_water(x, y, 14):
                    rock = Rock(x, y, rng.uniform(5, 15), rng.uniform(0.75, 1.0))
                    self.rocks.append(rock)
                    self.rock_hash.add(rock)
                    continue
                pb = 0.02 + 0.04 * f
                if 1.2 < n < 3.0:
                    pb += 0.07
                if n > 1.15 and rng.random() < pb and not self._near_water(x, y, 14):
                    bush = Bush(x, y, rng.uniform(9, 16), rng)
                    self.bushes.append(bush)
                    self.bush_hash.add(bush)

    # ------------------------------------------------------------ zapytania

    def tile_at_px(self, x, y):
        tx, ty = int(x // TILE), int(y // TILE)
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.tiles[ty][tx]
        return None

    def blocked(self, x, y, r):
        """Czy okrąg (x, y, r) wchodzi w wodę lub poza świat."""
        if x - r < 0 or y - r < 0 or x + r > self.pw or y + r > self.ph:
            return True
        k = r * 0.7071
        for ox, oy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r), (k, k), (-k, k), (k, -k), (-k, -k)):
            if self.tile_at_px(x + ox, y + oy) == WATER:
                return True
        return False

    def colliders_near(self, x, y, reach):
        out = self.tree_hash.query(x - reach, y - reach, x + reach, y + reach)
        out += [r for r in self.rock_hash.query(x - reach, y - reach, x + reach, y + reach) if r.collide]
        out += self.solids.query(x - reach, y - reach, x + reach, y + reach)
        return out

    def move_circle(self, x, y, r, dx, dy):
        """Ruch okręgu z kolizjami: woda/granice blokują osiami, z pni i głazów wypycha."""
        nx = x + dx
        if not self.blocked(nx, y, r):
            x = nx
        ny = y + dy
        if not self.blocked(x, ny, r):
            y = ny
        for _ in range(2):
            for o in self.colliders_near(x, y, r + 40):
                ox, oy = x - o.x, y - o.y
                d = math.hypot(ox, oy)
                min_d = r + o.r
                if 0 < d < min_d:
                    px = x + ox / d * (min_d - d)
                    py = y + oy / d * (min_d - d)
                    if not self.blocked(px, py, r):
                        x, y = px, py
        return x, y

    def line_of_sight(self, x0, y0, x1, y1):
        """Czy z (x0,y0) widać (x1,y1)? Zasłaniają pnie, głazy i krzaki."""
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy
        if l2 < 1:
            return True
        bx0, bx1 = min(x0, x1) - 30, max(x0, x1) + 30
        by0, by1 = min(y0, y1) - 30, max(y0, y1) + 30

        def hits(ox, oy, rad):
            t = max(0.0, min(1.0, ((ox - x0) * dx + (oy - y0) * dy) / l2))
            px, py = x0 + t * dx, y0 + t * dy
            return (ox - px) ** 2 + (oy - py) ** 2 < rad * rad

        for t in self.tree_hash.query(bx0, by0, bx1, by1):
            if hits(t.x, t.y, t.r + 7):
                return False
        for rk in self.rock_hash.query(bx0, by0, bx1, by1):
            if rk.collide and hits(rk.x, rk.y, rk.r):
                return False
        for b in self.bush_hash.query(bx0, by0, bx1, by1):
            if hits(b.x, b.y, b.r * 0.7):
                return False
        return True

    def in_bush(self, x, y):
        for b in self.bush_hash.query(x - 20, y - 20, x + 20, y + 20):
            if (b.x - x) ** 2 + (b.y - y) ** 2 < (b.r * 0.7) ** 2:
                return True
        return False

    def is_open(self, x, y, r):
        if self.blocked(x, y, r):
            return False
        for o in self.colliders_near(x, y, r + 30):
            if (o.x - x) ** 2 + (o.y - y) ** 2 < (o.r + r) ** 2:
                return False
        return True

    def random_open_point(self, rng, r, center=None, radius=None, avoid=None, min_dist=0, attempts=80):
        for _ in range(attempts):
            if center is not None:
                x = center[0] + rng.uniform(-radius, radius)
                y = center[1] + rng.uniform(-radius, radius)
            else:
                x, y = rng.uniform(0, self.pw), rng.uniform(0, self.ph)
            x = max(r + 8, min(self.pw - r - 8, x))
            y = max(r + 8, min(self.ph - r - 8, y))
            if avoid is not None and math.hypot(x - avoid[0], y - avoid[1]) < min_dist:
                continue
            if self.is_open(x, y, r):
                return x, y
        return None

    def mud_factor(self, slow):
        """Spowolnienie na mokrej ziemi (slow = maksymalny ubytek prędkości)."""
        return 1.0 - slow * self.wetness

    def speed_factor(self, x, y):
        return self._ground_speed(x, y) * self.mud_factor(MUD_SLOW_PLAYER)

    def _ground_speed(self, x, y):
        tx, ty = int(x // TILE), int(y // TILE)
        if not (0 <= tx < self.w and 0 <= ty < self.h):
            return 1.0
        if self.tiles[ty][tx] == ROAD:
            return 1.15
        k = 1.0 - 0.15 * self.forest[ty][tx] * self.clearing_factor(tx, ty)
        for b in self.bush_hash.query(x - 20, y - 20, x + 20, y + 20):
            if (b.x - x) ** 2 + (b.y - y) ** 2 < b.r ** 2:
                k *= 0.6
                break
        return k

    def visible_trees(self, x0, y0, x1, y1):
        return self.tree_hash.query(x0 - 50, y0 - 50, x1 + 50, y1 + 50)

    # ------------------------------------------------------------ renderowanie tła

    def chunk_count(self):
        return math.ceil(self.w / CHUNK), math.ceil(self.h / CHUNK)

    def get_chunk(self, cx, cy):
        key = (cx, cy)
        surf = self.chunks.get(key)
        if surf is not None:
            self.chunks.move_to_end(key)
            return surf
        surf = self._render_chunk(cx, cy)
        self.chunks[key] = surf
        if len(self.chunks) > MAX_CACHED_CHUNKS:
            self.chunks.popitem(last=False)
        return surf

    def has_chunk(self, cx, cy):
        return (cx, cy) in self.chunks

    def _render_chunk(self, cx, cy):
        T = TILE
        size = CHUNK * T
        tx0, ty0 = cx * CHUNK, cy * CHUNK
        ox, oy = tx0 * T, ty0 * T

        # gładko interpolowane podłoże (kolor kafla w jego środku)
        # smoothscale mapuje piksel docelowy x na źródłowy x*(N-1)/W, więc przy
        # W=(N-1)*T środek kafla i trafia dokładnie w piksel i*T - bez szwów.
        n = CHUNK + 3
        small = opaque_surface((n, n))
        for j in range(n):
            ty = min(max(ty0 + j - 1, 0), self.h - 1)
            row = self.ground[ty]
            for i in range(n):
                tx = min(max(tx0 + i - 1, 0), self.w - 1)
                small.set_at((i, j), row[tx])
        big = pygame.transform.smoothscale(small, ((n - 1) * T, (n - 1) * T))
        surf = opaque_surface((size, size))
        surf.blit(big, (-T // 2, -T // 2))

        rng = random.Random((self.seed * 1000003) ^ (cx * 92821) ^ (cy * 689287))
        self._draw_ground_decor(surf, rng, tx0, ty0, size)
        self._draw_water(surf, tx0, ty0, ox, oy)
        self._draw_paths(surf, rng, tx0, ty0, ox, oy, size)

        margin = 90
        x0, y0, x1, y1 = ox - margin, oy - margin, ox + size + margin, oy + size + margin
        trees = self.tree_hash.query(x0, y0, x1, y1)
        rocks = self.rock_hash.query(x0, y0, x1, y1)
        bushes = self.bush_hash.query(x0, y0, x1, y1)

        # cienie (rysowane na osobnej warstwie, więc się nie kumulują)
        shadow = pygame.Surface((size, size), pygame.SRCALPHA)
        sc = (8, 22, 6, 85)
        for t in trees:
            r = t.canopy_r
            pygame.draw.ellipse(shadow, sc, (t.x + r * 0.35 - r - ox, t.y + r * 0.4 - r * 0.9 - oy, 2 * r, 1.8 * r))
        for b in bushes:
            pygame.draw.ellipse(shadow, sc, (b.x + 3 - b.r - ox, b.y + 4 - b.r * 0.85 - oy, 2 * b.r, 1.7 * b.r))
        for rk in rocks:
            pygame.draw.ellipse(shadow, sc, (rk.x + 2 - rk.r - ox, rk.y + 3 - rk.r * rk.stretch - oy,
                                             2 * rk.r, 2 * rk.r * rk.stretch))
        surf.blit(shadow, (0, 0))

        # pnie - widoczne gdy korona robi się przezroczysta
        for t in trees:
            x, y = t.x - ox, t.y - oy
            for k in range(4):
                a = t.phase + k * math.pi / 2
                pygame.draw.line(surf, (70, 50, 30), (x, y),
                                 (x + math.cos(a) * t.r * 1.8, y + math.sin(a) * t.r * 1.8), 3)
            pygame.draw.circle(surf, (66, 46, 28), (x, y), t.r + 1)
            pygame.draw.circle(surf, (104, 76, 46), (x - 1, y - 1), t.r - 1)
            pygame.draw.circle(surf, (128, 98, 62), (x - 1, y - 1), max(1, t.r * 0.45), 1)

        for rk in rocks:
            x, y, r = rk.x - ox, rk.y - oy, rk.r
            rect = pygame.Rect(0, 0, 2 * r, 2 * r * rk.stretch)
            rect.center = (x, y)
            pygame.draw.ellipse(surf, (92, 92, 88), rect)
            inner = rect.inflate(-3, -3).move(-1, -1)
            pygame.draw.ellipse(surf, (132, 132, 124), inner)
            hl = pygame.Rect(0, 0, r * 0.8, r * 0.6 * rk.stretch)
            hl.center = (x - r * 0.3, y - r * 0.3)
            pygame.draw.ellipse(surf, (168, 166, 156), hl)

        for b in bushes:
            x, y = b.x - ox, b.y - oy
            for dx, dy, rr in b.blobs:
                pygame.draw.circle(surf, (34, 78, 34), (x + dx, y + dy), rr)
            for dx, dy, rr in b.blobs:
                pygame.draw.circle(surf, (58, 112, 46), (x + dx - rr * 0.2, y + dy - rr * 0.2), rr * 0.6)
            if b.berries:
                for k, (dx, dy, rr) in enumerate(b.blobs):
                    pygame.draw.circle(surf, (190, 30, 50), (x + dx + rr * 0.3, y + dy + (k % 2) * 2), 1.6)
        return surf

    def _draw_ground_decor(self, surf, rng, tx0, ty0, size):
        T = TILE
        for _ in range(1100):
            px, py = rng.uniform(0, size), rng.uniform(0, size)
            tx, ty = tx0 + int(px // T), ty0 + int(py // T)
            if tx >= self.w or ty >= self.h or self.tiles[ty][tx] != GRASS:
                continue
            if self.path_norm[ty][tx] < 1.15:
                continue
            cf = self.clearing_factor(tx, ty)
            f = self.forest[ty][tx] * cf
            r = rng.random()
            base = self.ground[ty][tx]
            if r < 0.55 - 0.3 * f:                       # kępka trawy
                col = lerp_color(base, (150, 190, 90) if rng.random() < 0.5 else (30, 60, 25), 0.35)
                for k in (-1, 0, 1):
                    pygame.draw.line(surf, col, (px, py), (px + k * 2 + rng.uniform(-1, 1), py - rng.uniform(3, 6)))
            elif r < 0.85 and f > 0.35:                  # liście / igliwie
                col = rng.choice(((96, 78, 40), (110, 92, 48), (70, 66, 34), (124, 98, 52)))
                pygame.draw.ellipse(surf, col, (px, py, rng.randint(2, 4), 2))
            elif f < 0.45 and rng.random() < 0.7 - f:    # kwiaty na łąkach i polanie
                col = rng.choice(((240, 240, 230), (250, 220, 70), (180, 120, 220), (230, 90, 90)))
                for k in range(5):
                    a = k * math.tau / 5
                    pygame.draw.circle(surf, col, (px + math.cos(a) * 2, py + math.sin(a) * 2), 1.3)
                pygame.draw.circle(surf, (250, 200, 40), (px, py), 1)

    def _draw_water(self, surf, tx0, ty0, ox, oy):
        T = TILE
        tiles = []
        for ty in range(max(0, ty0 - 1), min(self.h, ty0 + CHUNK + 1)):
            for tx in range(max(0, tx0 - 1), min(self.w, tx0 + CHUNK + 1)):
                if self.tiles[ty][tx] == WATER:
                    tiles.append((tx, ty))
        if not tiles:
            return
        for tx, ty in tiles:
            pygame.draw.circle(surf, SHORE, ((tx + 0.5) * T - ox, (ty + 0.5) * T - oy), T * 0.95)
        for tx, ty in tiles:
            pygame.draw.circle(surf, WATER_SHALLOW, ((tx + 0.5) * T - ox, (ty + 0.5) * T - oy), T * 0.8)
        for tx, ty in tiles:
            deep = all(self.tile_at_px((tx + 0.5 + dx) * T, (ty + 0.5 + dy) * T) == WATER
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if deep:
                pygame.draw.circle(surf, WATER_DEEP, ((tx + 0.5) * T - ox, (ty + 0.5) * T - oy), T * 0.75)
        rng = random.Random(tx0 * 31 + ty0 * 17 + self.seed)
        for tx, ty in tiles:
            if rng.random() < 0.3:
                x, y = (tx + rng.random()) * T - ox, (ty + rng.random()) * T - oy
                pygame.draw.line(surf, (150, 196, 220), (x, y), (x + rng.randint(4, 9), y), 1)

    def _draw_paths(self, surf, rng, tx0, ty0, ox, oy, size):
        T = TILE
        styles = {"road": (ROAD_SHOULDER, ROAD_CORE), "trail": (TRAIL_SHOULDER, TRAIL_CORE)}
        visible = []
        for p in self.paths:
            pad = p.radius * T + 12
            pts = [(x * T - ox, y * T - oy) for x, y in p.points]
            near = [i for i, (x, y) in enumerate(pts) if -pad < x < size + pad and -pad < y < size + pad]
            if near:
                visible.append((p, pts, near))
        if not visible:
            return
        for p, pts, near in visible:                     # pobocza
            for i in near:
                pygame.draw.circle(surf, styles[p.kind][0], pts[i], p.radius * T + 6)
        for p, pts, near in visible:                     # nawierzchnia
            for i in near:
                pygame.draw.circle(surf, styles[p.kind][1], pts[i], p.radius * T)
        for p, pts, near in visible:                     # koleiny na drodze
            if p.kind != "road":
                continue
            off = p.radius * T * 0.45
            for i in near:
                if i + 1 >= len(pts):
                    continue
                (x0, y0), (x1, y1) = pts[i], pts[i + 1]
                dx, dy = x1 - x0, y1 - y0
                ln = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / ln * off, dx / ln * off
                for s in (-1, 1):
                    pygame.draw.line(surf, ROAD_RUT, (x0 + nx * s, y0 + ny * s), (x1 + nx * s, y1 + ny * s), 7)
        # żwir / grudki ziemi
        for _ in range(2200):
            px, py = rng.uniform(0, size), rng.uniform(0, size)
            tx, ty = tx0 + int(px // T), ty0 + int(py // T)
            if tx >= self.w or ty >= self.h or self.path_norm[ty][tx] > 0.95:
                continue
            col = rng.choice(((120, 100, 70), (186, 164, 120), (146, 124, 88), (104, 96, 84)))
            pygame.draw.circle(surf, col, (px, py), rng.choice((1, 1, 1.5, 2)))

    # ------------------------------------------------------------ minimapa

    def build_minimap(self):
        surf = opaque_surface((self.w, self.h))
        for ty in range(self.h):
            for tx in range(self.w):
                t = self.tiles[ty][tx]
                if t == WATER:
                    col = WATER_SHALLOW
                elif t == ROAD:
                    col = ROAD_CORE
                else:
                    col = self.ground[ty][tx]
                surf.set_at((tx, ty), col)
        for tr in self.trees:
            col = (26, 66, 30) if tr.kind == "pine" else (40, 92, 38)
            surf.set_at((int(tr.x // TILE), int(tr.y // TILE)), col)
        return surf
