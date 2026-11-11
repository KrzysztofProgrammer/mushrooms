"""Niedźwiedź: włóczy się po lesie, zjada grzyby, a gdy zobaczy gracza - goni go.

Stany:
    wander  - spacer do losowego punktu albo do wywęszonego grzyba
    eat     - je grzyba (wtedy gorzej widzi)
    alert   - właśnie zauważył gracza, chwila na reakcję
    chase   - pościg
    search  - idzie tam, gdzie ostatnio widział/słyszał gracza i rozgląda się
"""

import math
import random

import pygame

from world import MUD_SLOW_BEAR
from clouds import sight_blocked
from mushrooms import PUFFBALL, TOADSTOOL

R = 18
WANDER_SPEED = 62
SEARCH_SPEED = 110
CHASE_SPEED = 200
CHASE_ACCEL = 260          # px/s^2
VIEW_DIST = 340
CLOSE_DIST = 80            # z tej odległości wyczuje gracza zawsze
FOV_HALF = math.radians(70)
HEAR_DIST = 230            # słyszy biegnącego gracza
SMELL_DIST = 320           # wyczuwa grzyby
EAT_TIME = 2.2
ALERT_TIME = 0.55
LOSE_TIME = 3.0            # po tylu sekundach bez kontaktu wzrokowego przestaje gonić
LOOK_AROUND_TIME = 2.5
SPLIT_AFTER = 10           # po tylu zjedzonych grzybach niedźwiedź się podwaja
TOADSTOOL_BOOST_TIME = 30.0   # s - po zjedzeniu muchomora niedźwiedź porusza się szybciej
TOADSTOOL_BOOST_MULT = 1.35   # mnożnik prędkości (spacer, szukanie i pościg)


def _angle_diff(a, b):
    return (a - b + math.pi) % math.tau - math.pi


class Bear:
    def __init__(self, x, y, seed):
        self.x, self.y = x, y
        self.r = R
        self.rng = random.Random(seed * 13 + 5)
        self.angle = self.rng.uniform(0, math.tau)
        self.state = "wander"
        self.t_state = 0.0
        self.target = None          # (x, y)
        self.food = None            # grzyb, do którego idzie
        self.speed = 0.0
        self.phase = 0.0
        self.moving = False
        self.stuck_t = 0.0
        self.target_t = 0.0         # czas dojścia do bieżącego celu
        self.target_limit = 0.0
        self.ignored = set()        # grzyby, do których nie dało się dojść
        self.detour = 0.0
        self.detour_t = 0.0
        self.lost_t = 0.0
        self.last_seen = None
        self.smell_t = 0.0
        self.eaten = 0
        self.meals = 0              # grzyby zjedzone od ostatniego podwojenia
        self.boost_t = 0.0          # pozostały czas przyspieszenia po muchomorze
        self.just_boosted = False   # ustawiane na jedną klatkę po zjedzeniu muchomora (dla komunikatu w grze)
        self.sees_player = False
        self.dir = (math.cos(self.angle), math.sin(self.angle))   # wygładzony kierunek ruchu
        self.check_t = 0.0          # kontrola postępu w stronę celu
        self.check_d = None
        self.check_target = None

    # ------------------------------------------------------------ percepcja

    def can_see(self, player, world):
        dx, dy = player.x - self.x, player.y - self.y
        d = math.hypot(dx, dy)
        if world.clouds and d > 40 and sight_blocked(world.clouds, self.x, self.y, player.x, player.y):
            return False                                   # obłok purchawki zasłania
        if d < CLOSE_DIST:
            return True
        view = VIEW_DIST * (0.55 if self.state == "eat" else 1.0)
        if d > view:
            return False
        if self.state != "chase" and abs(_angle_diff(math.atan2(dy, dx), self.angle)) > FOV_HALF:
            return False
        return world.line_of_sight(self.x, self.y, player.x, player.y)

    def _set(self, state):
        self.state = state
        self.t_state = 0.0

    # ------------------------------------------------------------ logika

    def update(self, dt, world, player, field):
        self.t_state += dt
        self.boost_t = max(0.0, self.boost_t - dt)
        self.just_boosted = False
        self.sees_player = self.can_see(player, world)
        d_player = math.hypot(player.x - self.x, player.y - self.y)

        if self.sees_player and self.state not in ("alert", "chase"):
            # w trakcie poszukiwań jest już czujny - rusza od razu
            self._set("chase" if self.state == "search" else "alert")
            self.food = None
        elif (self.state in ("wander", "eat") and player.running and d_player < HEAR_DIST):
            self._go_search((player.x, player.y))

        st = self.state
        if st == "alert":
            self._face(player.x, player.y, dt, 10)
            self.moving = False
            self.speed = 0.0
            if self.t_state >= ALERT_TIME:
                self._set("chase")
                self.last_seen = (player.x, player.y)

        elif st == "chase":
            if self.sees_player:
                self.last_seen = (player.x, player.y)
                self.lost_t = 0.0
            else:
                self.lost_t += dt
                if self.lost_t > LOSE_TIME:
                    self._go_search(self.last_seen)
                    return
            self.speed = min(CHASE_SPEED, self.speed + CHASE_ACCEL * dt)
            tx, ty = (player.x, player.y) if self.sees_player else self.last_seen
            self._move_toward(tx, ty, self.speed, dt, world)

        elif st == "search":
            if self.target is not None:
                self.target_t += dt
                if (self._move_toward(*self.target, SEARCH_SPEED, dt, world)
                        or self.target_t > self.target_limit):
                    self.target = None
                    self.t_state = 0.0
            else:
                self.moving = False
                self.angle += dt * 1.6 * (1 if int(self.t_state) % 2 == 0 else -1)  # rozgląda się
                if self.t_state > LOOK_AROUND_TIME:
                    self._set("wander")

        elif st == "eat":
            self.moving = False
            if self.food is None or not field.alive(self.food):
                self.food = None
                self._set("wander")
            elif self.t_state >= EAT_TIME:
                if field.remove(self.food):
                    if self.food.kind == TOADSTOOL:
                        # muchomor nie syci (nie liczy się do podwojenia), ale pobudza
                        self.boost_t = TOADSTOOL_BOOST_TIME
                        self.just_boosted = True
                    else:
                        self.eaten += 1
                        self.meals += 1
                self.food = None
                self._set("wander")

        else:  # wander
            self.smell_t -= dt
            if self.food is not None and not field.alive(self.food):
                self.food, self.target = None, None
            if self.food is None and self.smell_t <= 0:
                self.smell_t = 0.7
                m = field.nearest(self.x, self.y, SMELL_DIST, exclude=self.ignored, skip_kinds=(PUFFBALL,))
                if m is not None:
                    self.food = m
                    self._set_target((m.x, m.y), WANDER_SPEED)
            if self.target is not None:
                self.target_t += dt
                if self.target_t > self.target_limit:      # nie da się dojść - odpuść
                    if self.food is not None:
                        self.ignored.add(id(self.food))
                    self.food, self.target = None, None
            if self.target is None:
                self.food = None
                if len(self.ignored) > 30:
                    self.ignored.clear()
                self._set_target(world.random_open_point(self.rng, R, center=(self.x, self.y), radius=420),
                                 WANDER_SPEED)
            if self.target is not None:
                if self._move_toward(*self.target, WANDER_SPEED, dt, world, arrive=14 if self.food else 24):
                    self.target = None
                    if self.food is not None:
                        self._set("eat")

    def _set_target(self, pos, speed):
        self.target = pos
        self.target_t = 0.0
        if pos is not None:
            d = math.hypot(pos[0] - self.x, pos[1] - self.y)
            self.target_limit = d / speed * 2.0 + 2.5

    def _go_search(self, pos):
        self._set("search")
        self._set_target(pos, SEARCH_SPEED)
        self.food = None
        self.speed = SEARCH_SPEED

    def _face(self, x, y, dt, rate):
        a = math.atan2(y - self.y, x - self.x)
        self.angle += _angle_diff(a, self.angle) * min(1.0, dt * rate)

    def _move_toward(self, tx, ty, speed, dt, world, arrive=18):
        """Ruch ze sterowaniem omijającym pnie i wodę. Zwraca True po dotarciu."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < arrive:
            self.moving = False
            return True
        vx, vy = dx / d, dy / d

        # odpychanie od przeszkód leżących przed niedźwiedziem
        ax = ay = 0.0
        for o in world.colliders_near(self.x, self.y, 70):
            ox, oy = self.x - o.x, self.y - o.y
            od = math.hypot(ox, oy) or 1.0
            clearance = od - o.r - R
            if clearance < 36 and (o.x - self.x) * vx + (o.y - self.y) * vy > 0:
                w = 1.0 - max(0.0, clearance) / 36
                ax += ox / od * w
                ay += oy / od * w
        vx, vy = vx + ax * 0.9, vy + ay * 0.9

        # objazd po utknięciu
        if self.detour_t > 0:
            self.detour_t -= dt
            c, s = math.cos(self.detour), math.sin(self.detour)
            vx, vy = vx * c - vy * s, vx * s + vy * c
        ln = math.hypot(vx, vy) or 1.0
        vx, vy = vx / ln, vy / ln

        # wygładzanie kierunku - bez tego sterowanie potrafi oscylować przed pniem
        k = min(1.0, dt * 7)
        vx = self.dir[0] + (vx - self.dir[0]) * k
        vy = self.dir[1] + (vy - self.dir[1]) * k
        ln = math.hypot(vx, vy) or 1.0
        vx, vy = vx / ln, vy / ln

        # woda: wybierz najbliższy kierunek, który nie prowadzi do wody
        for rot in (0.0, 0.6, -0.6, 1.2, -1.2, 1.9, -1.9, 2.6, -2.6):
            c, s = math.cos(rot), math.sin(rot)
            cx, cy = vx * c - vy * s, vx * s + vy * c
            if not world.blocked(self.x + cx * 26, self.y + cy * 26, R):
                vx, vy = cx, cy
                break
        self.dir = (vx, vy)

        step = speed * dt * world.mud_factor(MUD_SLOW_BEAR) * self.speed_mult
        nx, ny = world.move_circle(self.x, self.y, R, vx * step, vy * step)
        moved = math.hypot(nx - self.x, ny - self.y)
        self.x, self.y = nx, ny
        self.moving = moved > 0.05
        self.phase += moved * 0.12
        if moved > 0.05:
            self._face(self.x + vx, self.y + vy, dt, 8)

        # utknięcie = brak postępu w stronę celu przez dłuższą chwilę
        if self.check_target != (tx, ty) and (self.check_target is None or
                                              math.hypot(tx - self.check_target[0], ty - self.check_target[1]) > 60):
            self.check_target, self.check_d, self.check_t = (tx, ty), d, 0.0
        self.check_t += dt
        if self.check_t >= 0.8:
            if self.check_d - d < speed * 0.8 * 0.3:
                self.stuck_t += self.check_t
                if self.detour_t <= 0:
                    self.detour = self.rng.choice((-1, 1)) * self.rng.uniform(0.9, 1.7)
                    self.detour_t = 1.0
            else:
                self.stuck_t = 0.0
            self.check_t, self.check_d = 0.0, d
        return False

    # ------------------------------------------------------------ rysowanie

    @property
    def boosted(self):
        return self.boost_t > 0

    @property
    def speed_mult(self):
        return TOADSTOOL_BOOST_MULT if self.boosted else 1.0

    def draw(self, screen, cam_x, cam_y, font, time):
        sx, sy = self.x - cam_x, self.y - cam_y
        if self.boosted:                       # pobudzony muchomorem: pulsująca czerwona poświata
            pulse = 0.5 + 0.5 * math.sin(time * 12)
            aura = pygame.Surface((90, 90), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 40, 30, int(60 + 70 * pulse)), (45, 45), 30 + 6 * pulse)
            pygame.draw.circle(aura, (255, 230, 220, int(90 + 80 * pulse)), (45, 45), 32 + 6 * pulse, 2)
            screen.blit(aura, (sx - 45, sy - 45))
        shadow = pygame.Surface((48, 60), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 85), shadow.get_rect())
        shadow = pygame.transform.rotate(shadow, -math.degrees(self.angle) - 90)
        screen.blit(shadow, shadow.get_rect(center=(sx + 5, sy + 6)))
        spr = draw_bear(self.phase, self.moving, self.state == "eat", time)
        spr = pygame.transform.rotate(spr, -math.degrees(self.angle) - 90)
        screen.blit(spr, spr.get_rect(center=(round(sx), round(sy))))

    def draw_marker(self, screen, cam_x, cam_y, font, time):
        """Wykrzyknik / znak zapytania nad niedźwiedziem (nad koronami drzew)."""
        if self.boosted:                       # pierścień pobudzenia widoczny także przez korony
            pulse = 0.5 + 0.5 * math.sin(time * 12)
            c = (self.x - cam_x, self.y - cam_y)
            pygame.draw.circle(screen, (255, 60, 40), c, 34 + 6 * pulse, 3)
            pygame.draw.circle(screen, (255, 200, 180), c, 38 + 6 * pulse, 1)
        mark = {"alert": ("!", (255, 70, 50)), "chase": ("!", (255, 70, 50)),
                "search": ("?", (255, 220, 80))}.get(self.state)
        if not mark:
            return
        sx, sy = self.x - cam_x, self.y - cam_y - 44 + math.sin(time * 8) * 3
        txt = font.render(mark[0], True, mark[1])
        out = font.render(mark[0], True, (0, 0, 0))
        r = txt.get_rect(center=(sx, sy))
        screen.blit(out, r.move(2, 2))
        screen.blit(txt, r)


FUR_DARK = (66, 42, 24)
FUR = (102, 66, 38)
FUR_LIGHT = (132, 90, 54)
MUZZLE = (176, 136, 96)


def draw_bear(phase, moving, eating, time):
    """Niedźwiedź z góry, zwrócony w górę (-y)."""
    size = 76
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    swing = math.sin(phase) * 5 if moving else 0.0
    # łapy (chód naprzemienny: lewa-przód z prawą-tył)
    for lx, ly, sgn in ((-14, -13, 1), (14, -13, -1), (-14, 15, -1), (14, 15, 1)):
        pygame.draw.ellipse(s, FUR_DARK, (c + lx - 6, c + ly - 7 + swing * sgn, 12, 14))
    # tułów
    pygame.draw.ellipse(s, FUR_DARK, (c - 18, c - 20, 36, 48))
    pygame.draw.ellipse(s, FUR, (c - 16, c - 19, 32, 44))
    pygame.draw.ellipse(s, FUR_LIGHT, (c - 9, c - 15, 16, 20))       # garb w świetle
    # głowa (przy jedzeniu pochylona i lekko się kiwa)
    hy = c - 25 + (2 + math.sin(time * 9) * 1.5 if eating else 0)
    for ex in (-8, 8):
        pygame.draw.circle(s, FUR_DARK, (c + ex, hy - 7), 4.5)
        pygame.draw.circle(s, MUZZLE, (c + ex, hy - 7), 2)
    pygame.draw.circle(s, FUR_DARK, (c, hy), 12)
    pygame.draw.circle(s, FUR, (c - 1, hy - 1), 10.5)
    pygame.draw.ellipse(s, MUZZLE, (c - 5, hy - 13, 10, 10))
    pygame.draw.circle(s, (20, 14, 10), (c, hy - 12), 2.6)          # nos
    for ex in (-4, 4):
        pygame.draw.circle(s, (16, 10, 8), (c + ex, hy - 4), 1.6)   # oczy
    return s
