"""Latarka: kupowana na straganie, włączana klawiszem L, świeci przez 3 godziny gry.

W snopie światła nocny filtr (szarość, mgła, ciemność) nie działa - widać prawdziwe kolory,
więc da się odróżnić grzyby. Bateria wyczerpuje się tylko wtedy, gdy latarka jest włączona.
"""

import math

import pygame

from daynight import SECONDS_PER_HOUR

FLASHLIGHT_COST = 60          # zł
FLASHLIGHT_HOURS = 3.0        # godzin gry świecenia na jednej latarce
BEAM_LENGTH = 300             # px - zasięg snopa
BEAM_HALF_ANGLE = 26          # stopni - połowa szerokości snopa
BEAM_SOFT = 10                # stopni - miękka krawędź snopa
GLOW_RADIUS = 46              # px - poświata wokół postaci
MASK_RES = 4                  # maska liczona w niższej rozdzielczości i wygładzana (szybki start)


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _make_mask():
    """Maska światła skierowana w prawo (kąt 0): biel z alfą = jasność snopa."""
    size = BEAM_LENGTH * 2
    n = size // MASK_RES
    small = pygame.Surface((n, n), pygame.SRCALPHA)
    c = n / 2
    for y in range(n):
        for x in range(n):
            dx, dy = (x + 0.5 - c) * MASK_RES, (y + 0.5 - c) * MASK_RES
            d = math.hypot(dx, dy)
            glow = 1.0 - _smooth((d - GLOW_RADIUS * 0.6) / (GLOW_RADIUS * 0.6))
            beam = 0.0
            if dx > 0 and d < BEAM_LENGTH:
                ang = abs(math.degrees(math.atan2(dy, dx)))
                edge = 1.0 - _smooth((ang - (BEAM_HALF_ANGLE - BEAM_SOFT)) / BEAM_SOFT)
                fade = 1.0 - _smooth((d - BEAM_LENGTH * 0.55) / (BEAM_LENGTH * 0.45))
                beam = edge * fade
            a = max(glow, beam)
            if a > 0:
                small.set_at((x, y), (255, 255, 255, int(255 * a)))
    return pygame.transform.smoothscale(small, (size, size))


class Flashlight:
    def __init__(self):
        self.charge = 0.0         # pozostały czas świecenia w sekundach rzeczywistych
        self.on = False
        self.mask = _make_mask()
        self._rot_angle = None
        self._rot = None
        self._piece = None
        self._rect = None

    @property
    def owned(self):
        return self.charge > 0

    def hours_left(self):
        return self.charge / SECONDS_PER_HOUR

    def refill(self):
        """Nowa latarka z pełną baterią (wyłączona - gracz włącza ją klawiszem L)."""
        self.charge = FLASHLIGHT_HOURS * SECONDS_PER_HOUR
        self.on = False

    def toggle(self):
        """Zwraca False, gdy nie ma latarki (albo bateria pusta)."""
        if not self.owned:
            self.on = False
            return False
        self.on = not self.on
        return True

    def update(self, dt):
        """Zwraca True w chwili wyczerpania baterii."""
        if self.on and self.charge > 0:
            self.charge -= dt
            if self.charge <= 0:
                self.charge = 0.0
                self.on = False
                return True
        return False

    # ------------------------------------------------------------ światło

    def capture(self, screen, sx, sy, angle):
        """Przed nocnym filtrem: zapamiętaj nieprzefiltrowany obraz w obszarze snopa."""
        self._piece = None
        if not self.on:
            return
        q = round(angle / 2) * 2                         # obrót maski tylko co 2 stopnie
        if q != self._rot_angle:
            self._rot = pygame.transform.rotate(self.mask, -q)
            self._rot_angle = q
        rect = self._rot.get_rect(center=(round(sx), round(sy)))
        clip = rect.clip(screen.get_rect())
        if clip.w <= 0 or clip.h <= 0:
            return
        piece = pygame.Surface(clip.size, pygame.SRCALPHA)
        piece.blit(screen, (0, 0), clip)
        piece.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MAX)   # pewna pełna alfa
        piece.blit(self._rot, (0, 0), clip.move(-rect.x, -rect.y), special_flags=pygame.BLEND_RGBA_MULT)
        self._piece, self._rect = piece, clip

    def apply(self, screen):
        """Po nocnym filtrze: nałóż oświetlony fragment z miękką maską."""
        if self._piece is not None:
            screen.blit(self._piece, self._rect)

    # ------------------------------------------------------------ HUD

    def draw_widget(self, screen, x, y, font, w=206, h=34):
        if not self.owned:
            return
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(panel, (20, 26, 16, 200), panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, (180, 160, 110, 230), panel.get_rect(), 2, border_radius=8)
        screen.blit(panel, (x, y))
        # ikonka latarki
        body = (230, 220, 120) if self.on else (140, 140, 130)
        pygame.draw.rect(screen, (60, 60, 60), (x + 10, y + 12, 18, 10), border_radius=3)
        pygame.draw.polygon(screen, body, [(x + 28, y + 10), (x + 36, y + 6), (x + 36, y + 28), (x + 28, y + 24)])
        mins = int(self.hours_left() * 60)
        state = "wł." if self.on else "wył."
        txt = font.render(f"Latarka {state}  {mins // 60}:{mins % 60:02d} h  (L)", True, (236, 236, 214))
        screen.blit(txt, (x + 44, y + 8))
        frac = self.charge / (FLASHLIGHT_HOURS * SECONDS_PER_HOUR)
        pygame.draw.rect(screen, (55, 55, 48), (x + 44, y + h - 7, w - 54, 3))
        pygame.draw.rect(screen, (240, 210, 80) if frac > 0.2 else (240, 90, 60),
                         (x + 44, y + h - 7, int((w - 54) * frac), 3))
