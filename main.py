"""Grzybobranie - gra w PyGame, widok z góry (rzut ortogonalny).

Zbieraj grzyby do plecaka i uważaj na niedźwiedzia, który też je zjada.
Jeśli cię zobaczy - zacznie gonić. Gdy cię dopadnie - GAME OVER.

Sterowanie:
    WASD / strzałki - ruch (grzyby zbierasz, przechodząc obok)
    Shift           - bieg (niedźwiedź słyszy biegnącego gracza)
    P               - pauza
    M               - minimapa
    H               - pomoc
    Enter           - po GAME OVER: jeszcze raz w tym samym lesie
    R               - nowy, losowy las
    Esc             - wyjście

Uruchomienie:  python main.py [ziarno]
Wczytanie zapisu:  python main.py <plik_zapisu.json>   (zapis robi się na straganie klawiszem Z)
"""

import json
import math
import os
import random
import sys

import pygame

from settings import SCREEN_W, SCREEN_H, FPS, TITLE, TILE, CHUNK, LOAD_FREE, LOAD_SLOW_PER, LOAD_MAX_SLOW
from world import World
from player import Player
from bear import Bear, SPLIT_AFTER
from mushrooms import MushroomField, KINDS, NAMES, RAIN_BURST, PICKUP_DIST
from weather import Weather
from clouds import SporeCloud, draw_fog_inside
from mushrooms import PUFFBALL, TOADSTOOL
from effects import Poisoning
from market import Market, BASE_PRICE, HIST_EVERY, HIST_LEN
from stall import Stall
from daynight import Clock
from flashlight import Flashlight, FLASHLIGHT_COST, FLASHLIGHT_HOURS
from sprites import make_vignette
import savegame

MAX_BEARS = 25          # górny limit, żeby gra nie zwolniła
HIGHSCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscore.json")


def load_highscore():
    try:
        with open(HIGHSCORE_FILE, encoding="utf-8") as f:
            return int(json.load(f).get("best_earned", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_highscore(best):
    try:
        with open(HIGHSCORE_FILE, "w", encoding="utf-8") as f:
            json.dump({"best_earned": best}, f)
    except OSError:
        pass


class Game:
    def __init__(self, seed=None, save_data=None):
        """save_data: słownik z savegame.read() - gra wczytuje zapis zamiast zaczynać od nowa."""
        if save_data is not None:
            seed = save_data["seed"]
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        fonts = "arial,helvetica,dejavusans"
        self.font = pygame.font.SysFont(fonts, 16)
        self.mid_font = pygame.font.SysFont(fonts, 22, bold=True)
        self.big_font = pygame.font.SysFont(fonts, 30, bold=True)
        self.huge_font = pygame.font.SysFont(fonts, 72, bold=True)
        self.vignette = make_vignette(SCREEN_W, SCREEN_H)
        self.danger = make_vignette(SCREEN_W, SCREEN_H, strength=200, color=(170, 0, 0))
        self.show_map = True
        self.show_help = False      # domyślnie tylko podpowiedź "H - pomoc"
        self.best = load_highscore()
        self.time = 0.0
        self.flashlight = Flashlight()   # maska światła liczona raz; stan baterii zerowany w new_round
        self.new_world(seed if seed is not None else random.randrange(1_000_000))
        if save_data is not None:
            savegame.restore(self, save_data)

    # ------------------------------------------------------------------ świat / runda

    def new_world(self, seed):
        self.screen.fill((20, 34, 20))
        txt = self.big_font.render("Generowanie lasu...", True, (220, 230, 200))
        self.screen.blit(txt, txt.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
        pygame.display.flip()
        pygame.event.pump()

        self.seed = seed
        self.world = World(seed)
        self.minimap = self.world.build_minimap()
        self.stall = Stall(self.world.stall)
        self.round = 0
        self.new_round()

    def new_round(self):
        """Nowa rozgrywka w tym samym lesie: świeże grzyby, gracz na drodze, niedźwiedź daleko."""
        self.round += 1
        rseed = self.seed * 101 + self.round
        self.player = Player(*self.world.spawn)
        self.field = MushroomField(self.world, rseed)
        rng = random.Random(rseed)
        pos = self.world.random_open_point(rng, 22, avoid=self.world.spawn, min_dist=1700, attempts=500)
        self.bear_rng = rng
        self.bears = [Bear(*(pos or (self.world.pw * 0.75, self.world.ph * 0.5)), rseed)]
        self.message = None         # [tekst, pozostały czas]
        self.weather = Weather(self.world, rseed)
        self.world.wetness = 0.0
        self.clouds = []
        self.world.clouds = self.clouds
        self.poison = Poisoning(rseed)
        self.backpack = {k: 0 for k in KINDS}
        self.market = Market(rseed)
        self.daytime = Clock()
        self.collected = 0          # grzyby zebrane w tej rozgrywce
        self.full_warn = 0.0
        self.shop_msg = None        # [tekst, czas, kolor]
        self.stall_armed = True     # sklep otworzy się po podejściu; po wyjściu trzeba najpierw odejść
        self.flashlight.charge = 0.0
        self.flashlight.on = False
        self.floaters = []          # [tekst, x, y, wiek]
        self.state = "play"         # play | shop | paused | over
        self.over_t = 0.0
        self.new_record = False
        self.intro_t = 6.0
        self.cam_x, self.cam_y = self._camera_target()
        for cx, cy in self._chunks_in_view(0):
            self.world.get_chunk(cx, cy)

    @property
    def score(self):
        """Wynik = pieniądze zarobione na sprzedaży grzybów (wydatki na ulepszenia go nie zmniejszają)."""
        return self.market.total_earned

    @property
    def backpack_count(self):
        return sum(self.backpack.values())

    @property
    def load_mult(self):
        """Mnożnik prędkości od ciężaru plecaka: 1.0 do LOAD_FREE grzybów, potem coraz wolniej."""
        over = max(0, self.backpack_count - LOAD_FREE)
        return 1.0 - min(LOAD_MAX_SLOW, over * LOAD_SLOW_PER)

    def _camera_target(self):
        tx = self.player.x - SCREEN_W / 2
        ty = self.player.y - SCREEN_H / 2
        tx = max(0, min(self.world.pw - SCREEN_W, tx))
        ty = max(0, min(self.world.ph - SCREEN_H, ty))
        return tx, ty

    def _chunks_in_view(self, margin):
        cs = CHUNK * TILE
        ncx, ncy = self.world.chunk_count()
        x0 = int(self.cam_x // cs) - margin
        y0 = int(self.cam_y // cs) - margin
        x1 = int((self.cam_x + SCREEN_W) // cs) + margin
        y1 = int((self.cam_y + SCREEN_H) // cs) + margin
        for cy in range(max(0, y0), min(ncy, y1 + 1)):
            for cx in range(max(0, x0), min(ncx, x1 + 1)):
                yield cx, cy

    # ------------------------------------------------------------------ pętla

    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            if not self.handle_events():
                return
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type != pygame.KEYDOWN:
                continue
            if self.state == "shop":
                self.shop_key(event)
                continue
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_m:
                if self.market.has_minimap:
                    self.show_map = not self.show_map
                else:
                    self.message = ["Nie masz jeszcze minimapy - kupisz ją na straganie (B).", 3.0]
            elif event.key == pygame.K_h:
                self.show_help = not self.show_help
            elif event.key == pygame.K_r:
                self.new_world(random.randrange(1_000_000))
            elif event.key == pygame.K_l and self.state == "play":
                if not self.flashlight.toggle():
                    self.message = ["Nie masz latarki - kupisz ją na straganie.", 3.0]
            elif event.key == pygame.K_p and self.state in ("play", "paused"):
                self.state = "paused" if self.state == "play" else "play"
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) \
                    and self.state == "over" and self.over_t > 0.6:
                self.new_round()
        return True

    def update(self, dt):
        if self.state == "paused":
            return
        self.time += dt
        if self.state == "over":
            self.over_t += dt
            return
        if self.state == "shop":              # w sklepie świat stoi, ale ceny żyją
            self.market.update(dt)
            if self.shop_msg:
                self.shop_msg[1] -= dt
                if self.shop_msg[1] <= 0:
                    self.shop_msg = None
            return

        self.intro_t = max(0.0, self.intro_t - dt)
        self.update_weather(dt)
        self.poison.update(dt)
        self.market.update(dt)
        self.daytime.update(dt)
        self.full_warn = max(0.0, self.full_warn - dt)
        self.player.update(dt, pygame.key.get_pressed(), self.world, self.poison.controls(), self.load_mult)

        if self.flashlight.update(dt):
            self.message = ["Bateria latarki się wyczerpała - kup nową latarkę na straganie.", 4.0]
        if self.player.just_tired:
            self.floaters.append(["Zmęczony!", self.player.x, self.player.y - 30, 0.0])

        # stragan: podejście otwiera sklep samo; ponownie dopiero po odejściu i powrocie
        if self.stall_armed and self.stall.near(self.player.x, self.player.y):
            self.stall_armed = False
            self.state = "shop"
            self.shop_msg = None
            self.player.moving = False
            return
        if not self.stall_armed and self.stall.far(self.player.x, self.player.y):
            self.stall_armed = True

        full = self.backpack_count >= self.market.capacity
        m = self.field.pick(self.player.x, self.player.y, full)
        if full and self.full_warn <= 0:
            near = self.field.nearest(self.player.x, self.player.y, PICKUP_DIST)
            if near is not None and near.kind in KINDS:
                self.full_warn = 3.0
                self.floaters.append(["Plecak pełny!", self.player.x, self.player.y - 24, 0.0])
                self.message = ["Plecak pełny! Sprzedaj grzyby na straganie albo kup tam większy plecak.", 3.0]
        if m is not None and m.kind == TOADSTOOL:
            result = self.poison.eat_toadstool()
            if result == "fatal":
                self.game_over("Zatrułeś się muchomorami!")
                return
            if result == "blackout":
                self.message = ["Drugi muchomor! Ciemność na 15 sekund... Trzeci będzie śmiertelny.", 4.0]
            else:
                self.message = ["Muchomor! Przez 10 sekund sterowanie wariuje.", 3.0]
        elif m is not None and m.kind == PUFFBALL:
            self.clouds.append(SporeCloud(m.x, m.y, random.randrange(1_000_000)))
            self.message = ["Purchawka! Obłok zarodników zasłania widok na 10 sekund.", 3.0]
        elif m is not None:
            self.backpack[m.kind] += 1
            self.collected += 1
            self.floaters.append([f"+1 {NAMES[m.kind]}", m.x, m.y - 10, 0.0])
        for c in self.clouds:
            c.update(dt)
        self.clouds[:] = [c for c in self.clouds if c.alive]

        for b in self.bears:
            b.update(dt, self.world, self.player, self.field)
            if b.just_boosted:
                self.floaters.append(["Muchomor! Niedźwiedź przyspiesza!", b.x, b.y - 40, 0.0])
                if math.hypot(b.x - self.player.x, b.y - self.player.y) < 900:
                    self.message = ["Niedźwiedź zjadł muchomora - przez 30 sekund jest szybszy!", 3.5]
        self.split_bears()
        if self.message:
            self.message[1] -= dt
            if self.message[1] <= 0:
                self.message = None
        self.field.update(dt, (self.player.x, self.player.y), self.weather.wetness)
        for f in self.floaters:
            f[3] += dt
        self.floaters = [f for f in self.floaters if f[3] < 1.2]

        for b in self.bears:
            if math.hypot(b.x - self.player.x, b.y - self.player.y) < b.r + self.player.r - 1:
                self.game_over()
                break

        tx, ty = self._camera_target()
        k = min(1.0, dt * 6)
        self.cam_x += (tx - self.cam_x) * k
        self.cam_y += (ty - self.cam_y) * k

        for cx, cy in self._chunks_in_view(1):        # dorenderuj jeden fragment w tle
            if not self.world.has_chunk(cx, cy):
                self.world.get_chunk(cx, cy)
                break

    def update_weather(self, dt):
        event = self.weather.update(dt)
        self.world.wetness = self.weather.wetness
        if event == "start":
            self.message = ["Zaczyna padać... na mokrej ziemi będzie trudniej iść.", 4.0]
        elif event == "stop":
            n = int(RAIN_BURST * self.weather.wetness)
            self.field.burst(n, (self.player.x, self.player.y))
            self.message = ["Przestało padać - w lesie wysyp grzybów!", 4.0]

    def split_bears(self):
        """Niedźwiedź, który zjadł SPLIT_AFTER grzybów, podwaja się."""
        for b in list(self.bears):
            if b.meals < SPLIT_AFTER:
                continue
            b.meals -= SPLIT_AFTER
            if len(self.bears) >= MAX_BEARS:
                continue
            pos = self.world.random_open_point(self.bear_rng, 22, center=(b.x, b.y), radius=60) or (b.x, b.y)
            self.bears.append(Bear(pos[0], pos[1], self.bear_rng.randrange(1_000_000)))
            self.floaters.append(["Niedźwiedź się podwoił!", b.x, b.y - 40, 0.0])
            self.message = [f"Niedźwiedź najadł się grzybów i się podwoił! Niedźwiedzi: {len(self.bears)}", 4.0]

    @property
    def bears_eaten(self):
        return sum(b.eaten for b in self.bears)

    def game_over(self, reason="Niedźwiedź cię dopadł!"):
        self.over_reason = reason
        self.state = "over"
        self.over_t = 0.0
        self.player.moving = False
        for b in self.bears:
            b.moving = False
        if self.score > self.best:
            self.best = self.score
            self.new_record = True
            save_highscore(self.best)

    # ------------------------------------------------------------------ rysowanie

    def draw(self):
        cam_x, cam_y = round(self.cam_x), round(self.cam_y)
        screen = self.screen
        screen.fill((0, 0, 0))
        cs = CHUNK * TILE
        for cx, cy in self._chunks_in_view(0):
            screen.blit(self.world.get_chunk(cx, cy), (cx * cs - cam_x, cy * cs - cam_y))

        self.weather.draw_ground(screen, cam_x, cam_y)
        self.stall.draw(screen, cam_x, cam_y)
        self.field.draw(screen, cam_x, cam_y, SCREEN_W, SCREEN_H)
        self.player.draw(screen, cam_x, cam_y)
        on_screen = [b for b in self.bears
                     if cam_x - 60 < b.x < cam_x + SCREEN_W + 60 and cam_y - 60 < b.y < cam_y + SCREEN_H + 60]
        for b in on_screen:
            b.draw(screen, cam_x, cam_y, self.big_font, self.time)

        # korony drzew; przezroczyste nad graczem i nad niedźwiedziami
        px, py = self.player.x, self.player.y
        ts = self.world.tree_sprites
        for t in self.world.visible_trees(cam_x, cam_y, cam_x + SCREEN_W, cam_y + SCREEN_H):
            under = (t.x - px) ** 2 + (t.y - py) ** 2 < (t.canopy_r + 12) ** 2
            if not under:
                for b in on_screen:
                    if (t.x - b.x) ** 2 + (t.y - b.y) ** 2 < (t.canopy_r + 22) ** 2:
                        under = True
                        break
            spr = ts.get(t.kind, t.variant, under)
            sway = math.sin(self.time * 1.1 + t.phase) * 1.2
            screen.blit(spr, (t.x - spr.get_width() / 2 - cam_x + sway,
                              t.y - spr.get_height() / 2 - cam_y + sway * 0.5))

        for b in on_screen:
            b.draw_marker(screen, cam_x, cam_y, self.big_font, self.time)
        for text, x, y, age in self.floaters:
            surf = self.mid_font.render(text, True, (255, 240, 170))
            surf.set_alpha(int(255 * (1 - age / 1.2)))
            screen.blit(surf, surf.get_rect(center=(x - cam_x, y - cam_y - age * 40)))

        for c in self.clouds:
            c.draw(screen, cam_x, cam_y)
        draw_fog_inside(screen, self.clouds, self.player.x, self.player.y)
        self.weather.draw_sky(screen)
        lit = self.daytime.night_level() > 0.005 and self.flashlight.on
        if lit:                                # latarka: zapamiętaj obraz sprzed nocnego filtra w snopie światła
            self.flashlight.capture(screen, self.player.x - cam_x, self.player.y - cam_y, self.player.angle)
        self.daytime.apply(screen)             # noc: szaro-ciemny świat (HUD i ostrzeżenia zostają kolorowe)
        if lit:
            self.flashlight.apply(screen)
        screen.blit(self.vignette, (0, 0))
        hunters = [b for b in self.bears if b.state in ("alert", "chase")]
        if hunters and self.state == "play":
            self.danger.set_alpha(int(150 + 100 * math.sin(self.time * 9)))
            screen.blit(self.danger, (0, 0))
            for b in hunters:
                self.draw_bear_arrow(b, cam_x, cam_y)

        self.poison.draw(screen)
        map_visible = self.market.has_minimap and self.show_map and not self.poison.blackout
        if map_visible:
            self.draw_minimap()
        self.draw_hud()
        self.draw_backpack()
        self.draw_stamina()
        clock_y = 182 if map_visible else 16              # bez minimapy zegar przesuwa się na górę
        self.daytime.draw_widget(screen, SCREEN_W - 16 - 206 + 3, clock_y, self.big_font, self.font)
        self.flashlight.draw_widget(screen, SCREEN_W - 16 - 206 + 3, clock_y + 68, self.font)
        if self.state == "shop":
            self.draw_shop()
        elif self.state == "paused":
            self.draw_center_panel(["PAUZA", "P - wznów"])
        elif self.state == "over":
            self.draw_game_over()

    def draw_bear_arrow(self, bear, cam_x, cam_y):
        """Strzałka przy krawędzi ekranu, gdy goniący niedźwiedź jest poza kadrem."""
        sx, sy = bear.x - cam_x, bear.y - cam_y
        if -10 < sx < SCREEN_W + 10 and -10 < sy < SCREEN_H + 10:
            return
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        a = math.atan2(sy - cy, sx - cx)
        k = min((SCREEN_W / 2 - 40) / (abs(math.cos(a)) or 1e-6), (SCREEN_H / 2 - 40) / (abs(math.sin(a)) or 1e-6))
        ax, ay = cx + math.cos(a) * k, cy + math.sin(a) * k
        pts = [(ax + math.cos(a) * 18, ay + math.sin(a) * 18),
               (ax + math.cos(a + 2.5) * 14, ay + math.sin(a + 2.5) * 14),
               (ax + math.cos(a - 2.5) * 14, ay + math.sin(a - 2.5) * 14)]
        pygame.draw.polygon(self.screen, (255, 60, 40), pts)
        pygame.draw.polygon(self.screen, (0, 0, 0), pts, 2)

    def draw_minimap(self):
        mm = self.minimap
        w, h = mm.get_size()
        x0, y0 = SCREEN_W - w - 16, 16
        frame = pygame.Rect(x0 - 3, y0 - 3, w + 6, h + 6)
        pygame.draw.rect(self.screen, (24, 30, 20), frame, border_radius=4)
        self.screen.blit(mm, (x0, y0))
        view = pygame.Rect(x0 + self.cam_x / TILE, y0 + self.cam_y / TILE, SCREEN_W / TILE, SCREEN_H / TILE)
        pygame.draw.rect(self.screen, (240, 240, 220), view, 1)
        sp = (x0 + self.stall.x / TILE, y0 + self.stall.y / TILE)           # stragan
        pygame.draw.rect(self.screen, (0, 0, 0), (sp[0] - 4, sp[1] - 4, 9, 9))
        pygame.draw.rect(self.screen, (255, 210, 60), (sp[0] - 3, sp[1] - 3, 7, 7))
        # grzyby (wszystkie jednakowo, bez rozróżnienia gatunków) - po wykupieniu ulepszenia
        if self.market.mushroom_map:
            for mu in self.field.items:
                self.screen.fill((245, 240, 225), (int(x0 + mu.x / TILE), int(y0 + mu.y / TILE), 2, 2))
        # niedźwiedzie tylko po wykupieniu ulepszenia na straganie; goniące pulsują
        if self.market.radar:
            pulse = 0.5 + 0.5 * math.sin(self.time * 10)
            for b in self.bears:
                bpos = (x0 + b.x / TILE, y0 + b.y / TILE)
                if b.state in ("alert", "chase"):
                    pygame.draw.circle(self.screen, (0, 0, 0), bpos, 5)
                    pygame.draw.circle(self.screen, (255, int(60 + 120 * pulse), 30), bpos, 4)
                else:
                    pygame.draw.circle(self.screen, (0, 0, 0), bpos, 4)
                    pygame.draw.circle(self.screen, (160, 100, 50), bpos, 3)
        ppos = (x0 + self.player.x / TILE, y0 + self.player.y / TILE)
        pygame.draw.circle(self.screen, (0, 0, 0), ppos, 4)
        pygame.draw.circle(self.screen, (240, 60, 50), ppos, 3)
        pygame.draw.rect(self.screen, (180, 170, 130), frame, 1, border_radius=4)

    def _text(self, text, pos, font=None, color=(236, 236, 214), center=False):
        font = font or self.font
        shadow = font.render(text, True, (0, 0, 0))
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        self.screen.blit(shadow, rect.move(1, 1))
        self.screen.blit(surf, rect)

    def draw_hud(self):
        if self.show_help:
            lines = ["WASD / strzałki - ruch    Shift - bieg (głośny!)",
                     "Stragan: podejdź, aby handlować   L - latarka   P - pauza   M - mapa   R - nowy las   Esc - wyjście",
                     "Krzaki zasłaniają widok - można się w nich ukryć.",
                     "H - ukryj pomoc"]
        else:
            lines = ["H - pomoc"]
        y = 12
        for line in lines:
            self._text(line, (12, y))
            y += 20
        if self.message and self.state == "play":
            surf = self.mid_font.render(self.message[0], True, (255, 190, 120))
            surf.set_alpha(int(255 * min(1.0, self.message[1])))
            rect = surf.get_rect(center=(SCREEN_W / 2, 150))
            bg = pygame.Surface(rect.inflate(24, 12).size, pygame.SRCALPHA)
            bg.fill((40, 10, 0, int(150 * min(1.0, self.message[1]))))
            self.screen.blit(bg, rect.inflate(24, 12))
            self.screen.blit(surf, rect)
        if self.intro_t > 0 and self.state == "play":
            alpha_k = min(1.0, self.intro_t)
            surf = self.mid_font.render("Zbieraj grzyby i sprzedawaj je na straganie. Uważaj na niedźwiedzie!", True, (255, 240, 180))
            surf.set_alpha(int(255 * alpha_k))
            self.screen.blit(surf, surf.get_rect(center=(SCREEN_W / 2, 110)))

    def draw_stamina(self):
        """Pasek wytrzymałości na dole ekranu (bieg ją zużywa, odpoczynek odnawia)."""
        p = self.player
        w, h = 260, 16
        x0, y0 = (SCREEN_W - w) // 2, SCREEN_H - 40
        self._text("Wytrzymałość", (SCREEN_W // 2, y0 - 12), color=(230, 230, 210), center=True)
        pygame.draw.rect(self.screen, (20, 20, 16), (x0 - 3, y0 - 3, w + 6, h + 6), border_radius=6)
        s = p.stamina
        if p.tired:
            col = (255, 60, 50) if int(self.time * 6) % 2 == 0 else (120, 30, 25)   # miga przy zmęczeniu
        elif p.run_locked:
            col = (200, 120, 60)
        else:
            col = (90, 210, 90) if s > 0.5 else ((235, 200, 60) if s > 0.25 else (240, 90, 60))
        pygame.draw.rect(self.screen, (55, 55, 48), (x0, y0, w, h), border_radius=4)
        if s > 0:
            pygame.draw.rect(self.screen, col, (x0, y0, max(4, int(w * s)), h), border_radius=4)
        if p.tired:
            self._text("ZMĘCZENIE", (SCREEN_W // 2, y0 + h // 2), center=True, color=(255, 255, 255))

    def draw_backpack(self):
        rows = len(KINDS)
        w, h = 250, 52 + rows * 30 + 70
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (20, 26, 16, 190), panel.get_rect(), border_radius=10)
        pygame.draw.rect(panel, (180, 160, 110, 220), panel.get_rect(), 2, border_radius=10)
        x0, y0 = 14, SCREEN_H - h - 14
        self.screen.blit(panel, (x0, y0))
        self._text("Plecak", (x0 + 14, y0 + 10), self.mid_font, (250, 226, 160))
        cap = f"{self.backpack_count}/{self.market.capacity}"
        full = self.backpack_count >= self.market.capacity
        self._text(cap, (x0 + w - 16 - self.mid_font.size(cap)[0], y0 + 10), self.mid_font,
                   (255, 110, 90) if full else (255, 255, 255))
        y = y0 + 46
        for k in KINDS:
            icon = self.field.icons[k]
            self.screen.blit(icon, icon.get_rect(center=(x0 + 30, y + 10)))
            self._text(NAMES[k], (x0 + 56, y))
            self._text(f"x {self.backpack[k]}", (x0 + w - 60, y))
            y += 30
        self._text(f"Monety: {self.market.money} zł", (x0 + 14, y + 4), self.mid_font, (255, 215, 90))
        # ciężar plecaka celowo nie jest pokazywany - gracz odczuwa go tylko jako wolniejszy ruch
        self._text(f"Rekord zarobków: {self.best} zł", (x0 + 14, y + 32), color=(200, 220, 170))
        self._text(f"Niedźwiedzie: {len(self.bears)}   zjadły: {self.bears_eaten}", (x0 + 14, y + 50),
                   color=(220, 180, 140))

    # ------------------------------------------------------------------ stragan

    SELL_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                 pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2}

    def shop_key(self, event):
        m = self.market
        key = event.key
        if key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN):
            self.state = "play"
        elif key in self.SELL_KEYS:
            kind = KINDS[self.SELL_KEYS[key]]
            count = 10_000 if event.mod & pygame.KMOD_SHIFT else 1
            n, total = m.sell(kind, self.backpack, count)
            if n:
                self.shop_msg = [f"Sprzedano: {n} x {NAMES[kind]} za {total} zł", 2.5, (170, 255, 150)]
            else:
                self.shop_msg = [f"Nie masz grzybów: {NAMES[kind]}", 2.0, (255, 150, 120)]
        elif key == pygame.K_u:
            nxt = m.next_capacity()
            if nxt is None:
                self.shop_msg = ["Plecak ma już maksymalną pojemność.", 2.5, (255, 200, 120)]
            elif m.buy_capacity():
                self.shop_msg = [f"Kupiono większy plecak: {nxt[0]} miejsc!", 2.5, (170, 255, 150)]
            else:
                self.shop_msg = [f"Za mało monet - potrzeba {nxt[1]} zł.", 2.5, (255, 150, 120)]
        elif key == pygame.K_l:
            fl = self.flashlight
            if fl.owned:
                self.shop_msg = [f"Masz jeszcze latarkę ({fl.hours_left():.1f} h). Nową kupisz, gdy ta się wyczerpie.",
                                 3.0, (255, 200, 120)]
            elif m.spend(FLASHLIGHT_COST):
                fl.refill()
                self.shop_msg = [f"Kupiono latarkę ({FLASHLIGHT_HOURS:g} h świecenia). Włączysz ją klawiszem L.",
                                 3.0, (170, 255, 150)]
            else:
                self.shop_msg = [f"Za mało monet - potrzeba {FLASHLIGHT_COST} zł.", 2.5, (255, 150, 120)]
        elif key == pygame.K_z:
            try:
                path = savegame.save(self)
                self.shop_msg = [f"Zapisano grę: zapisy/{os.path.basename(path)}", 4.0, (170, 255, 150)]
            except OSError as e:
                self.shop_msg = [f"Nie udało się zapisać gry: {e}", 4.0, (255, 150, 120)]
        elif key == pygame.K_b:
            nxt = m.next_map_upgrade()
            if nxt is None:
                self.shop_msg = ["Minimapa ma już wszystkie ulepszenia.", 2.5, (255, 200, 120)]
            elif m.buy_map_upgrade():
                self.shop_msg = [f"Kupiono: {nxt[0]}!", 3.0, (170, 255, 150)]
            else:
                self.shop_msg = [f"Za mało monet - potrzeba {nxt[1]} zł.", 2.5, (255, 150, 120)]

    def _draw_trend(self, x, y, trend):
        if trend > 0:
            pygame.draw.polygon(self.screen, (90, 220, 90), [(x, y + 14), (x + 16, y + 14), (x + 8, y)])
        elif trend < 0:
            pygame.draw.polygon(self.screen, (235, 80, 70), [(x, y), (x + 16, y), (x + 8, y + 14)])
        else:
            pygame.draw.rect(self.screen, (170, 170, 150), (x, y + 5, 16, 4))

    def _draw_chart(self, rect, kind):
        m = self.market
        pygame.draw.rect(self.screen, (14, 20, 12), rect, border_radius=4)
        base = BASE_PRICE[kind]
        top = base * 1.6
        hist = list(m.history[kind]) + [m.price(kind)]

        def pt(i, v):
            return (rect.x + 4 + (rect.w - 8) * i / (len(hist) - 1),
                    rect.bottom - 4 - (rect.h - 8) * max(0.0, min(1.0, v / top)))

        by = pt(0, base)[1]
        for x in range(rect.x + 4, rect.right - 4, 8):                    # linia ceny bazowej
            pygame.draw.line(self.screen, (90, 90, 70), (x, by), (x + 4, by))
        pygame.draw.lines(self.screen, (240, 200, 90), False, [pt(i, v) for i, v in enumerate(hist)], 2)
        pygame.draw.circle(self.screen, (255, 255, 255), pt(len(hist) - 1, hist[-1]), 3)
        pygame.draw.rect(self.screen, (120, 110, 80), rect, 1, border_radius=4)

    def draw_shop(self):
        m = self.market
        scr = self.screen
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        scr.blit(shade, (0, 0))
        w, h = 1000, 600
        panel = pygame.Rect((SCREEN_W - w) // 2, (SCREEN_H - h) // 2, w, h)
        pygame.draw.rect(scr, (30, 24, 16), panel, border_radius=14)
        pygame.draw.rect(scr, (196, 160, 100), panel, 3, border_radius=14)
        x0, y0 = panel.x, panel.y

        self._text("Stragan - skup grzybów", (x0 + 28, y0 + 18), self.big_font, (250, 226, 160))
        money = f"Monety: {m.money} zł"
        self._text(money, (panel.right - 28 - self.big_font.size(money)[0], y0 + 18), self.big_font, (255, 215, 90))
        cap = f"Plecak: {self.backpack_count}/{m.capacity}"
        self._text(cap, (x0 + 28, y0 + 60), self.mid_font,
                   (255, 130, 110) if self.backpack_count >= m.capacity else (230, 230, 210))

        heads = (("Grzyb", 100), ("W plecaku", 280), ("Cena", 400), ("Popyt", 560), (f"Wykres cen ({round(HIST_EVERY * HIST_LEN / 60)} min)", 730))
        for text, dx in heads:
            self._text(text, (x0 + dx, y0 + 100), color=(180, 170, 140))
        pygame.draw.line(scr, (110, 90, 60), (x0 + 24, y0 + 122), (panel.right - 24, y0 + 122), 1)

        y = y0 + 134
        for i, kind in enumerate(KINDS):
            icon = self.field.icons[kind]
            key = pygame.Rect(x0 + 28, y + 22, 28, 28)
            pygame.draw.rect(scr, (70, 56, 36), key, border_radius=5)
            self._text(str(i + 1), key.center, self.mid_font, center=True)
            scr.blit(icon, icon.get_rect(center=(x0 + 76, y + 36)))
            self._text(NAMES[kind], (x0 + 100, y + 14), self.mid_font)
            self._text(f"bazowa {BASE_PRICE[kind]} zł", (x0 + 100, y + 44), color=(160, 150, 120))
            self._text(f"x {self.backpack[kind]}", (x0 + 280, y + 22), self.mid_font)
            self._text(f"{m.price_int(kind)} zł", (x0 + 400, y + 14), self.big_font, (255, 240, 170))
            self._draw_trend(x0 + 510, y + 22, m.trend(kind))
            df = m.demand_factor(kind)
            col = (120, 230, 120) if df > 0.9 else ((240, 210, 90) if df > 0.6 else (240, 110, 90))
            self._text(f"{int(df * 100)}%", (x0 + 560, y + 14), self.mid_font, col)
            self._text(f"ost. minuta: {m.recent_sales(kind)} szt.", (x0 + 560, y + 44), color=(160, 150, 120))
            self._draw_chart(pygame.Rect(x0 + 730, y + 4, 240, 62), kind)
            y += 82

        pygame.draw.line(scr, (110, 90, 60), (x0 + 24, y + 4), (panel.right - 24, y + 4), 1)
        self._text("Ulepszenia", (x0 + 28, y + 14), self.mid_font, (250, 226, 160))
        nxt = m.next_capacity()
        if nxt is None:
            cap_txt, cap_ok = f"[U] Plecak: maksymalna pojemność ({m.capacity} miejsc)", False
        else:
            cap_txt = f"[U] Większy plecak: {m.capacity} -> {nxt[0]} miejsc - {nxt[1]} zł"
            cap_ok = m.money >= nxt[1]
        self._text(cap_txt, (x0 + 28, y + 48), self.mid_font, (170, 255, 150) if cap_ok else (200, 190, 160))
        nxt_map = m.next_map_upgrade()
        if nxt_map is None:
            map_txt, map_ok = "[B] Mapa: wszystkie ulepszenia kupione (minimapa, grzyby, niedźwiedzie)", False
        else:
            map_txt = f"[B] {nxt_map[0]} - {nxt_map[1]} zł"
            map_ok = m.money >= nxt_map[1]
        self._text(map_txt, (x0 + 28, y + 78), self.mid_font, (170, 255, 150) if map_ok else (200, 190, 160))
        fl = self.flashlight
        if fl.owned:
            fl_txt, fl_ok = f"[L] Latarka - masz ją jeszcze na {fl.hours_left():.1f} h", False
        else:
            fl_txt = f"[L] Latarka ({FLASHLIGHT_HOURS:g} h świecenia, potem trzeba kupić nową) - {FLASHLIGHT_COST} zł"
            fl_ok = m.money >= FLASHLIGHT_COST
        self._text(fl_txt, (x0 + 28, y + 108), self.mid_font, (170, 255, 150) if fl_ok else (200, 190, 160))

        if self.shop_msg:
            self._text(self.shop_msg[0], (panel.centerx, panel.bottom - 60), self.mid_font, self.shop_msg[2],
                       center=True)
        self._text("[1][2][3] sprzedaj 1 szt.     Shift + [1][2][3] wszystkie     Z - zapisz grę     E / Esc - wyjdź",
                   (panel.centerx, panel.bottom - 30), center=True, color=(200, 190, 160))

    def draw_center_panel(self, lines):
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        self.screen.blit(shade, (0, 0))
        y = SCREEN_H / 2 - 30
        for i, line in enumerate(lines):
            self._text(line, (SCREEN_W / 2, y), self.big_font if i == 0 else self.font, center=True)
            y += 44

    def draw_game_over(self):
        k = min(1.0, self.over_t / 0.8)
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((60, 0, 0, int(170 * k)))
        self.screen.blit(shade, (0, 0))
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        self._text("GAME OVER", (cx, cy - 110), self.huge_font, (255, 80, 60), center=True)
        self._text(self.over_reason, (cx, cy - 40), self.big_font, center=True)
        self._text(f"Zarobiono na grzybach: {self.score} zł", (cx, cy + 10), self.mid_font, (255, 240, 170),
                   center=True)
        self._text(f"Zebrano: {self.collected}   sprzedano: {self.market.sold}   "
                   f"niesprzedane w plecaku: {self.backpack_count}", (cx, cy + 40), center=True)
        rec = "NOWY REKORD!" if self.new_record else f"Rekord: {self.best}"
        self._text(rec, (cx, cy + 72), self.mid_font, (180, 255, 150) if self.new_record else (220, 220, 200),
                   center=True)
        if self.over_t > 0.6:
            self._text("Enter - jeszcze raz w tym lesie    R - nowy las    Esc - wyjście",
                       (cx, cy + 120), center=True)


def main():
    """python main.py [ziarno]  albo  python main.py <plik_zapisu.json>"""
    seed, save_data = None, None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            seed = int(arg)
        except ValueError:
            try:
                save_data = savegame.read(arg)
            except savegame.SaveError as e:
                print(f"Błąd: {e}", file=sys.stderr)
                sys.exit(1)
    Game(seed, save_data).run()
    pygame.quit()


if __name__ == "__main__":
    main()
