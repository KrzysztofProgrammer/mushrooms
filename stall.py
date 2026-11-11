"""Stragan na końcu ścieżki: grafika (widok z góry) i punkt interakcji."""

import pygame

INTERACT_DIST = 105          # px od środka straganu - po podejściu tak blisko sklep otwiera się sam
REARM_DIST = 135             # px - trzeba odejść dalej niż tyle, żeby sklep mógł otworzyć się ponownie
SPRITE_W, SPRITE_H = 120, 96
CENTER = (60, 46)            # środek straganu w sprite'cie (tu leży linia kolizji)

WOOD_DARK = (84, 58, 34)
WOOD = (130, 94, 56)
WOOD_LIGHT = (160, 120, 74)
RED = (196, 48, 40)
CREAM = (240, 230, 200)


def make_stall_sprite():
    s = pygame.Surface((SPRITE_W, SPRITE_H), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 80), (10, 22, 108, 70))                       # cień

    # lada: deski
    pygame.draw.rect(s, WOOD_DARK, (8, 34, 104, 44), border_radius=4)
    pygame.draw.rect(s, WOOD, (10, 36, 100, 40), border_radius=3)
    for y in (46, 56, 66):
        pygame.draw.line(s, WOOD_DARK, (11, y), (109, y), 1)
    pygame.draw.rect(s, WOOD_LIGHT, (10, 36, 100, 4))

    # kosze z grzybami na ladzie
    baskets = ((28, 60, (128, 78, 38), (176, 120, 64)),      # borowiki
               (60, 60, (74, 50, 34), (110, 80, 54)),        # podgrzybki
               (92, 60, (236, 170, 36), (250, 210, 90)))     # kurki
    for x, y, c1, c2 in baskets:
        pygame.draw.circle(s, (96, 70, 38), (x, y), 13)
        pygame.draw.circle(s, (150, 116, 66), (x, y), 11)
        for i, (ox, oy) in enumerate(((-4, -3), (4, -2), (0, 4), (-5, 4), (5, 4))):
            pygame.draw.circle(s, c1, (x + ox, y + oy), 4.2)
            pygame.draw.circle(s, c2, (x + ox - 1, y + oy - 1), 2)

    # słupki z przodu
    for x in (9, 111):
        pygame.draw.circle(s, WOOD_DARK, (x, 78), 5)
        pygame.draw.circle(s, WOOD, (x - 1, 77), 3)

    # daszek w pasy, z falbaną z przodu
    stripe = 13
    n = 8
    x0 = 8
    pygame.draw.rect(s, (60, 30, 24), (x0 - 2, 6, stripe * n + 4, 40))
    for i in range(n):
        col = RED if i % 2 == 0 else CREAM
        pygame.draw.rect(s, col, (x0 + i * stripe, 8, stripe, 34))
        pygame.draw.circle(s, col, (x0 + i * stripe + stripe // 2, 42), stripe // 2)
    pygame.draw.rect(s, (255, 255, 255, 60), (x0, 8, stripe * n, 6))               # połysk

    # tabliczka na daszku
    plaque = pygame.Rect(34, 18, 52, 17)
    pygame.draw.rect(s, WOOD_DARK, plaque.inflate(4, 4), border_radius=4)
    pygame.draw.rect(s, WOOD, plaque, border_radius=3)
    font = pygame.font.SysFont("arial,helvetica,dejavusans", 12, bold=True)
    txt = font.render("GRZYBY", True, (252, 240, 210))
    s.blit(txt, txt.get_rect(center=plaque.center))
    return s


class Stall:
    def __init__(self, pos):
        self.x, self.y = pos
        self.sprite = make_stall_sprite()

    def near(self, x, y):
        return (self.x - x) ** 2 + (self.y - y) ** 2 < INTERACT_DIST ** 2

    def far(self, x, y):
        return (self.x - x) ** 2 + (self.y - y) ** 2 > REARM_DIST ** 2

    def draw(self, screen, cam_x, cam_y):
        screen.blit(self.sprite, (self.x - CENTER[0] - cam_x, self.y - CENTER[1] - cam_y))
