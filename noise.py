"""Prosty, deterministyczny szum wartości (value noise) + fBm."""

import math
import random


class ValueNoise:
    def __init__(self, seed):
        rnd = random.Random(seed)
        perm = list(range(256))
        rnd.shuffle(perm)
        self.perm = perm + perm
        self.values = [rnd.random() for _ in range(256)]

    def _v(self, ix, iy):
        p = self.perm
        return self.values[p[p[ix & 255] + (iy & 255)]]

    def noise(self, x, y):
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        sx = fx * fx * (3 - 2 * fx)
        sy = fy * fy * (3 - 2 * fy)
        a = self._v(ix, iy)
        b = self._v(ix + 1, iy)
        c = self._v(ix, iy + 1)
        d = self._v(ix + 1, iy + 1)
        top = a + (b - a) * sx
        bottom = c + (d - c) * sx
        return top + (bottom - top) * sy

    def fbm(self, x, y, octaves=4, lacunarity=2.0, gain=0.5):
        amp, freq, total, norm = 1.0, 1.0, 0.0, 0.0
        for i in range(octaves):
            total += self.noise(x * freq + i * 17.3, y * freq - i * 9.1) * amp
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm
