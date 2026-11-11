"""Postać gracza: ruch w 8 kierunkach, bieg, kolizje z pniami, kamieniami i wodą."""

import math

import pygame

from settings import (WALK_SPEED, RUN_MULT, PLAYER_RADIUS, STAMINA_RUN_TIME, STAMINA_REGEN_TIME,
                      TIRED_TIME, RUN_UNLOCK)
from sprites import draw_player


class Player:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.r = PLAYER_RADIUS
        self.angle = 0.0          # kierunek patrzenia w stopniach (0 = wschód)
        self.phase = 0.0          # faza animacji kroku
        self.moving = False
        self.running = False
        self.stamina = 1.0        # wytrzymałość 0..1 (bieg ją zużywa)
        self.tired_t = 0.0        # pozostały czas zmęczenia (postać nie może się ruszać)
        self.run_locked = False   # po zmęczeniu bieg zablokowany do odnowienia RUN_UNLOCK
        self.just_tired = False   # ustawiane na jedną klatkę w chwili zmęczenia
        self.anim_t = 0.0

    @property
    def tired(self):
        return self.tired_t > 0

    def update(self, dt, keys, world, controls=None, speed_mult=1.0):
        """controls: opcjonalna zamiana kierunków {"up": "left", ...} (zatrucie muchomorem)."""
        self.anim_t += dt
        self.just_tired = False
        if self.tired:                                  # zmęczona postać stoi i dyszy
            self.tired_t = max(0.0, self.tired_t - dt)
            self.moving = self.running = False
            self.phase = 0.0
            self.stamina = min(1.0, self.stamina + dt / STAMINA_REGEN_TIME)
            return
        pressed = {
            "up": keys[pygame.K_w] or keys[pygame.K_UP],
            "down": keys[pygame.K_s] or keys[pygame.K_DOWN],
            "left": keys[pygame.K_a] or keys[pygame.K_LEFT],
            "right": keys[pygame.K_d] or keys[pygame.K_RIGHT],
        }
        if controls:
            pressed = {d: any(pressed[k] for k, v in controls.items() if v == d) for d in pressed}
        dx = pressed["right"] - pressed["left"]
        dy = pressed["down"] - pressed["up"]
        self.moving = bool(dx or dy)
        wants_run = self.moving and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if self.run_locked and self.stamina >= RUN_UNLOCK:
            self.run_locked = False
        self.running = wants_run and not self.run_locked and self.stamina > 0
        if self.running:
            self.stamina -= dt / STAMINA_RUN_TIME
            if self.stamina <= 0:                       # wyczerpanie: zmęczenie
                self.stamina = 0.0
                self.tired_t = TIRED_TIME
                self.run_locked = True
                self.just_tired = True
                self.moving = self.running = False
                self.phase = 0.0
                return
        else:
            self.stamina = min(1.0, self.stamina + dt / STAMINA_REGEN_TIME)
        if not self.moving:
            self.phase = 0.0
            return

        ln = math.hypot(dx, dy)
        dx, dy = dx / ln, dy / ln
        speed = (WALK_SPEED * (RUN_MULT if self.running else 1.0) * world.speed_factor(self.x, self.y)
                 * speed_mult)
        self.phase += dt * speed * 0.085

        target = math.degrees(math.atan2(dy, dx))
        diff = (target - self.angle + 180) % 360 - 180
        self.angle += diff * min(1.0, dt * 14)

        self.x, self.y = world.move_circle(self.x, self.y, self.r, dx * speed * dt, dy * speed * dt)

    def draw(self, screen, cam_x, cam_y):
        sx, sy = self.x - cam_x, self.y - cam_y
        shadow = pygame.Surface((30, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        screen.blit(shadow, (sx - 15 + 4, sy - 11 + 5))
        base = draw_player(self.phase, self.moving)
        if self.tired:                                  # ciężki oddech: postać "pulsuje"
            base = pygame.transform.smoothscale_by(base, 1.0 + 0.07 * math.sin(self.anim_t * 16))
        sprite = pygame.transform.rotate(base, -(self.angle + 90))
        screen.blit(sprite, sprite.get_rect(center=(round(sx), round(sy))))
        if self.tired:
            self._draw_tired(screen, sx, sy)

    def _draw_tired(self, screen, sx, sy):
        """Animacja zmęczenia: krople potu odlatujące od głowy i obłoczki oddechu."""
        t = self.anim_t
        for i in range(4):                              # krople potu
            k = (t * 1.6 + i / 4) % 1.0
            a = -math.pi / 2 + (i - 1.5) * 0.7
            d = 10 + 16 * k
            x, y = sx + math.cos(a) * d, sy + math.sin(a) * d - 8 + 18 * k * k
            if k < 0.85:
                pygame.draw.circle(screen, (150, 200, 255), (x, y), 3.4 * (1 - k * 0.4))
                pygame.draw.circle(screen, (235, 245, 255), (x - 0.6, y - 0.6), 1)
        fa = math.radians(self.angle)                   # obłoczki oddechu przed twarzą
        for i in range(2):
            k = (t * 2.2 + i * 0.5) % 1.0
            x = sx + math.cos(fa) * (14 + 12 * k)
            y = sy + math.sin(fa) * (14 + 12 * k)
            puff = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(puff, (240, 240, 240, int(150 * (1 - k))), (10, 10), 3 + 5 * k)
            screen.blit(puff, (x - 10, y - 10))
