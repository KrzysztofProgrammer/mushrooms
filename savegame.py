"""Zapis i odczyt stanu gry (plik JSON).

Zapis robi się na straganie (klawisz Z). Odczyt: `python main.py <plik_zapisu.json>`.

Las (teren, drzewa, droga, stragan) nie jest zapisywany - odtwarza się go deterministycznie
z ziarna. Zapisujemy tylko to, co się zmienia w trakcie gry: gracza, plecak, rynek, grzyby,
niedźwiedzie, pogodę, zatrucie, zegar, latarkę i stany generatorów losowych.
"""

import json
import os
import time
from collections import deque

from bear import Bear
from clouds import SporeCloud
from mushrooms import Mushroom, KINDS
from world import SpatialHash
from settings import TILE

SAVE_VERSION = 1
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zapisy")


class SaveError(Exception):
    """Nie da się wczytać zapisu (brak pliku, zły format, inna wersja)."""


# ---------------------------------------------------------------- pomocnicze

def _rng_get(rng):
    version, state, gauss = rng.getstate()
    return [version, list(state), gauss]


def _rng_set(rng, data):
    version, state, gauss = data
    rng.setstate((version, tuple(state), gauss))


def _pt(p):
    return None if p is None else [p[0], p[1]]


def _tup(p):
    return None if p is None else (p[0], p[1])


# ---------------------------------------------------------------- zapis

def _bear_state(b):
    state = b.state
    if state == "eat":                    # grzyb, który jadł, nie jest zapisywany - wraca do wędrówki
        state = "wander"
    return {
        "x": b.x, "y": b.y, "angle": b.angle, "state": state, "t_state": b.t_state,
        "target": _pt(b.target) if b.food is None else None,
        "target_t": b.target_t, "target_limit": b.target_limit,
        "speed": b.speed, "lost_t": b.lost_t, "last_seen": _pt(b.last_seen), "smell_t": b.smell_t,
        "eaten": b.eaten, "meals": b.meals, "boost_t": b.boost_t, "dir": _pt(b.dir),
        "rng": _rng_get(b.rng),
    }


def snapshot(game):
    """Cały zmienny stan gry jako słownik gotowy do json.dump."""
    p, m, f, w, po = game.player, game.market, game.field, game.weather, game.poison
    return {
        "version": SAVE_VERSION,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": game.seed,
        "round": game.round,
        "time": game.time,
        "collected": game.collected,
        "backpack": dict(game.backpack),
        "show_map": game.show_map,
        "bear_rng": _rng_get(game.bear_rng),
        "player": {"x": p.x, "y": p.y, "angle": p.angle, "stamina": p.stamina,
                   "tired_t": p.tired_t, "run_locked": p.run_locked},
        "market": {
            "t": m.t, "noise": m.noise, "sales": m.sales,
            "history": {k: list(v) for k, v in m.history.items()}, "hist_t": m.hist_t,
            "money": m.money, "total_earned": m.total_earned, "sold": m.sold,
            "cap_level": m.cap_level, "map_level": m.map_level, "rng": _rng_get(m.rng),
        },
        "mushrooms": {
            "items": [[it.x, it.y, it.kind, it.variant] for it in f.items],
            "timer": f.timer, "decay_timer": f.decay_timer, "rng": _rng_get(f.rng),
        },
        "bears": [_bear_state(b) for b in game.bears],
        "weather": {"raining": w.raining, "intensity": w.intensity, "target": w.target,
                    "wetness": w.wetness, "timer": w.timer, "rng": _rng_get(w.rng)},
        "poison": {"eaten": po.eaten, "poison_t": po.poison_t, "blackout_t": po.blackout_t,
                   "mapping": po.mapping, "shuffle_t": po.shuffle_t, "age": po.age, "rng": _rng_get(po.rng)},
        "clouds": [[c.x, c.y, c.t] for c in game.clouds],
        "daytime": game.daytime.t,
        "flashlight": {"charge": game.flashlight.charge, "on": game.flashlight.on},
    }


def save(game, path=None):
    """Zapisuje grę; zwraca ścieżkę pliku. Domyślnie zapisy/grzybobranie_RRRRMMDD_GGMMSS.json."""
    if path is None:
        os.makedirs(SAVE_DIR, exist_ok=True)
        path = os.path.join(SAVE_DIR, time.strftime("grzybobranie_%Y%m%d_%H%M%S.json"))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot(game), fh, ensure_ascii=False)
    os.replace(tmp, path)                 # bez połówkowych plików przy błędzie zapisu
    return path


# ---------------------------------------------------------------- odczyt

def read(path):
    """Wczytuje i wstępnie sprawdza plik zapisu. Zwraca słownik albo rzuca SaveError."""
    if not os.path.exists(path) and os.path.exists(os.path.join(SAVE_DIR, path)):
        path = os.path.join(SAVE_DIR, path)          # sama nazwa pliku - szukamy w katalogu zapisy/
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise SaveError(f"Nie ma pliku zapisu: {path}")
    except (OSError, ValueError) as e:
        raise SaveError(f"Nie da się odczytać zapisu {path}: {e}")
    if not isinstance(data, dict) or "seed" not in data:
        raise SaveError(f"Plik {path} nie jest zapisem Grzybobrania.")
    if data.get("version") != SAVE_VERSION:
        raise SaveError(f"Nieobsługiwana wersja zapisu: {data.get('version')} (oczekiwano {SAVE_VERSION}).")
    return data


def restore(game, data):
    """Przywraca stan z zapisu do gry, w której las z tym samym ziarnem jest już wygenerowany."""
    if data["round"] != game.round:       # obiekty rundy (np. wygląd grzybów) zależą od numeru rundy
        game.round = data["round"] - 1
        game.new_round()

    game.time = data["time"]
    game.collected = data["collected"]
    game.backpack = {k: int(data["backpack"].get(k, 0)) for k in KINDS}
    game.show_map = data["show_map"]
    _rng_set(game.bear_rng, data["bear_rng"])

    p, d = game.player, data["player"]
    p.x, p.y, p.angle = d["x"], d["y"], d["angle"]
    p.stamina, p.tired_t, p.run_locked = d["stamina"], d["tired_t"], d["run_locked"]

    m, d = game.market, data["market"]
    m.t, m.hist_t = d["t"], d["hist_t"]
    m.noise = {k: d["noise"][k] for k in KINDS}
    m.sales = {k: list(d["sales"][k]) for k in KINDS}
    for k in KINDS:
        m.history[k] = deque(d["history"][k], maxlen=m.history[k].maxlen)
    m.money, m.total_earned, m.sold = d["money"], d["total_earned"], d["sold"]
    m.cap_level, m.map_level = d["cap_level"], d["map_level"]
    _rng_set(m.rng, d["rng"])

    f, d = game.field, data["mushrooms"]
    f.items = []
    f.hash = SpatialHash(TILE * 2)
    for x, y, kind, variant in d["items"]:
        it = Mushroom(x, y, kind, variant)
        f.items.append(it)
        f.hash.add(it)
    f.timer, f.decay_timer = d["timer"], d["decay_timer"]
    _rng_set(f.rng, d["rng"])

    game.bears = []
    for bd in data["bears"]:
        b = Bear(bd["x"], bd["y"], 0)
        b.angle, b.state, b.t_state = bd["angle"], bd["state"], bd["t_state"]
        b.target = _tup(bd["target"])
        b.target_t, b.target_limit = bd["target_t"], bd["target_limit"]
        b.speed, b.lost_t, b.smell_t = bd["speed"], bd["lost_t"], bd["smell_t"]
        b.last_seen = _tup(bd["last_seen"])
        b.eaten, b.meals, b.boost_t = bd["eaten"], bd["meals"], bd["boost_t"]
        b.dir = _tup(bd["dir"])
        _rng_set(b.rng, bd["rng"])
        game.bears.append(b)

    w, d = game.weather, data["weather"]
    w.raining, w.intensity, w.target = d["raining"], d["intensity"], d["target"]
    w.wetness, w.timer = d["wetness"], d["timer"]
    _rng_set(w.rng, d["rng"])
    game.world.wetness = w.wetness

    po, d = game.poison, data["poison"]
    po.eaten, po.poison_t, po.blackout_t = d["eaten"], d["poison_t"], d["blackout_t"]
    po.mapping, po.shuffle_t, po.age = dict(d["mapping"]), d["shuffle_t"], d["age"]
    _rng_set(po.rng, d["rng"])

    game.clouds[:] = []                   # ta sama lista jest w world.clouds
    for i, (x, y, t) in enumerate(data["clouds"]):
        c = SporeCloud(x, y, data["seed"] + i)
        c.t = t
        game.clouds.append(c)

    game.daytime.t = data["daytime"]
    game.flashlight.charge = data["flashlight"]["charge"]
    game.flashlight.on = data["flashlight"]["on"] and game.flashlight.charge > 0

    # zapis powstał na straganie - gra startuje w sklepie; żeby wrócić do sklepu, trzeba odejść i podejść
    game.state = "shop"
    game.stall_armed = False
    game.intro_t = 0.0
    game.message = None
    game.shop_msg = ["Wczytano zapis gry.", 3.0, (170, 255, 150)]
    game.cam_x, game.cam_y = game._camera_target()
