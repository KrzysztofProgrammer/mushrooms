# CLAUDE.md: notes for AI development sessions

"Grzybobranie" is a top-down (orthographic) 2D game in Python + **pygame-ce**. The player collects
mushrooms in a procedurally generated forest while avoiding bears. All graphics are drawn in code;
the repo has no asset files. `README.md` is the player-facing manual (in Polish) and must be kept
in sync with gameplay changes.

## Conventions

- **Language:** all user-visible text (HUD, messages, README) and code comments/docstrings are **Polish**.
  Identifiers are English. Keep it that way.
- **Communication with the user:** the user writes in Polish; reply in Polish.
- No external assets: new visuals are drawn with `pygame.draw` into cached surfaces (see `sprites.py`).
- Tunable gameplay values are module-level UPPER_CASE constants at the top of each module. Add new
  tuning knobs the same way and avoid scattering magic numbers.
- The project is not a git repository (at the time of writing).

## Running and testing

```bash
.venv/bin/python main.py [seed | save.json]   # pygame-ce 2.5.x is installed in .venv
```

There is no test suite. Verification is done with headless scripts (keep them **outside** the repo,
e.g. in `/tmp`):

```python
import os, sys; os.environ["SDL_VIDEODRIVER"] = "dummy"; sys.path.insert(0, "<repo>")
import main as M, pygame
M.HIGHSCORE_FILE = "/tmp/hs.json"          # do not overwrite the player's record
g = M.Game(1234)
pygame.key.get_pressed = lambda: FakeKeys()  # object with __getitem__(key) -> bool
for _ in range(600): g.update(1/60)
g.draw(); pygame.image.save(g.screen, "/tmp/shot.png")   # then view the PNG
```

Useful levers: set `g.player.x/y` and `g.bears[0].x/y/angle` directly to stage a scene, and call
`g.weather.start_rain()` while setting `intensity`/`wetness`. Run long simulations at 1/30–1/60 s steps
and use the results to check balance.

**Important: also verify rendering with the real macOS driver (`cocoa`).** The dummy driver uses a
different pixel format and hides bugs. Run without `SDL_VIDEODRIVER`, in the background with
`sleep N; kill`, and read pixels with `g.screen.get_at(...)`.

## Architecture

| File | Responsibility |
|---|---|
| `main.py` | `Game`: main loop, states `play / shop / paused / over`, camera, drawing order, HUD, backpack panel, minimap, messages, bear splitting, high score (`highscore.json`) |
| `settings.py` | screen, tile and world sizes, player speed, terrain colours |
| `noise.py` | `ValueNoise` + `fbm`, deterministic per seed |
| `world.py` | `World`: map generation, collisions/queries, background chunk rendering, minimap |
| `sprites.py` | tree canopy sprite pool (`TreeSprites`), player drawing, vignette |
| `player.py` | `Player`: input, 8-direction movement, walk animation |
| `bear.py` | `Bear`: state-machine AI, perception, steering, drawing |
| `mushrooms.py` | `MushroomField`: spawning, regrowth, rain burst, decay, pickup, drawing |
| `clouds.py` | `SporeCloud`: puffball spore cloud (10 s), blocks bear sight, fog when the player is inside |
| `daynight.py` | `Clock`: game clock (1 real minute = 1 game hour), `night_level()`, night filter, clock widget |
| `market.py` | `Market`: mushroom prices (random walk + supply/demand), wallet, backpack capacity and minimap upgrades |
| `stall.py` | `Stall`: stall sprite (top-down, drawn in code) and interaction distance |
| `effects.py` | `Poisoning`: toadstool poisoning (10 s scrambled controls + colour filter), blackout (15 s) after a second toadstool |
| `weather.py` | `Weather`: rain cycle, ground wetness, particles, puddles |
| `savegame.py` | save/load: `snapshot`/`save` (JSON in `zapisy/`), `read` (validation, `SaveError`), `restore` |
| `flashlight.py` | `Flashlight`: flashlight (bought at the stall, 3 game hours of light, toggled with L), light beam and HUD widget |

### World (`world.py`)
- 200×150 tiles of 32 px. Tile types: `GRASS`, `ROAD`, `WATER`.
- Per-tile fields: `forest` (density 0..1), `mix` (pine/deciduous ratio), `wet` (lakes), `var` (colour variation),
  `path_norm` (distance to the nearest road axis divided by that road's radius; ≤1 = road), `ground` (base colour).
- Generation order: fields → paths (`_walk`, a smooth random walk with `max_dev` that prevents loops; main road W→E,
  side trail to a clearing) → water (lakes from noise + a pond on the clearing) → colours → trees → rocks/bushes.
- Objects: `Tree` (collision = trunk `r`, visual = `canopy_r`), `Rock` (collides when `r >= 8`), `Bush` (slows movement and blocks sight).
  Each has its own `SpatialHash` (`tree_hash`, `rock_hash`, `bush_hash`).
- Key queries: `blocked` (water and world bounds), `move_circle` (axis-separated movement + push-out from trunks and rocks:
  the shared movement routine for every entity), `line_of_sight`, `is_open`, `random_open_point`, `speed_factor`,
  `mud_factor`. `wetness` is set every frame from the weather.
- Background is rendered in 16×16-tile chunks (512 px), with an LRU cache (`MAX_CACHED_CHUNKS`). The game pre-renders
  one missing chunk per frame around the view. Static elements (ground, roads, water, shadows, trunks, rocks, bushes)
  are baked into chunks, so after changing a chunk's content its cache must be cleared (`world.chunks.clear()`).

### Stall and economy
- `World._place_stall` (called from `_gen_paths`): the stall sits `STALL_REACH` tiles past the end of the side trail.
  The trail is extended to it and ends in a dirt plaza (extra path points). `world.stall` = pixel position;
  collision = 5 `Solid` circles in `world.solids` (included by `colliders_near`, so the player, bears, and mushroom
  spawning respect it). Trees/rocks/bushes are suppressed within `STALL_CLEAR` px (`near_stall`) and water within
  3.6 tiles. None of this consumes `world.rng`, so seeds still generate the same forest.
- `Market.price(kind) = BASE_PRICE * noise * demand_factor`. `noise` is an Ornstein-Uhlenbeck walk;
  `demand_factor = FLOOR + (1-FLOOR) * exp(-DEMAND_K * pressure)`, where `pressure` sums sale weights
  (1 for `HOLD_TIME` s, then a linear decay over `RECOVER_TIME` s). `sell()` prices each unit separately and records
  the sale, so selling 5 of one kind lowers the price along the way. All tuning constants are at the top of `market.py`.
- Game flow: **the shop opens by itself on approach** (no key, no prompt; user's request): in `Game.update`, when
  `stall_armed` and `stall.near()` (`INTERACT_DIST` 105 px) → `state = "shop"`, `stall_armed = False`. It re-arms only
  after walking away beyond `REARM_DIST` (135 px, hysteresis against flicker), so after closing (E/Esc/Enter) the shop does
  not reopen until the player leaves and comes back. In the shop, `state = "shop"` (`Game.update` runs only `market.update`; the world is frozen);
  keys are handled in `Game.shop_key`, drawing in `draw_shop`. The backpack limit = `market.capacity`;
  `field.pick(..., backpack_full)` skips edible kinds (toadstool/puffball still trigger).
- **Score = `market.total_earned`** (money earned from sales), not the number of mushrooms. `highscore.json` stores
  `{"best_earned": N}`; the old `"best"` key (mushroom count) is ignored.
- Map upgrades are a single tiered upgrade under key **B** (like the backpack under U): `market.map_level`
  0 (**no minimap at the start**) → 1 (minimap) → 2 (mushrooms: every kind, including puffball/toadstool, as identical
  white 2×2 dots, so species cannot be told apart) → 3 (bears). Order and prices are in `MAP_UPGRADES`;
  `has_minimap`, `mushroom_map`, and `radar` are properties derived from `map_level`. There is no separate G key.
  Without the minimap, M only shows a message, and the clock widget moves up to y=16 (under the minimap it sits at y=182).
  On the minimap the stall is always marked with a yellow square.
- Price recovery: `HOLD_TIME` 60 s (the user's spec: one mushroom lowers the price for 1 minute) + `RECOVER_TIME` 360 s,
  lengthened at the user's request so that a repeat sale still feels the effect. The chart covers `HIST_EVERY * HIST_LEN` = 8 min.
- Backpack, money, upgrades, and prices are per round: `Game.new_round` creates a new `Market`.

### Time of day and weight
- `Game.daytime` (a `daynight.Clock`; **not** `Game.clock`, which is the pygame frame clock). Starts at 15:00 (`START_HOUR`), runs only in
  the `play` state. `night_level()`: 0 by day, ramps 20→21, 1 from 21 to 05, ramps down 05→06 (night starts at 21:00, the user's request).
- `Clock.apply(screen)`: the whole-scene night effect: `transform.grayscale` into an opaque buffer (alpha
  `GRAY_MAX * night`) → **fog/blur**: the gray buffer is downscaled `BLUR_DOWNSCALE`× and scaled back up with
  `smoothscale` into opaque buffers (~0.7 ms; `transform.gaussian_blur` is ~260 ms/frame, so do not use it) and blended with
  alpha `BLUR_ALPHA * night` → gray fog (`FOG_ALPHA`) → dark tint. Goal (user's request): at night a kurka and a
  muchomor must look the same. Measured: a 13×13 px patch over a kurka and over a muchomor came out identical
  (difference 0 vs 65 by day). It is applied after the weather and before the vignette/danger/poison/HUD, so the HUD,
  the stamina bar, and chase warnings keep their colours.
- Stamina (`player.py`, constants in `settings.py`): `stamina` 0..1, running drains it over `STAMINA_RUN_TIME` (10 s),
  not running restores it over `STAMINA_REGEN_TIME`. At 0 → `tired_t = TIRED_TIME` (2 s): `update` returns early and the
  player cannot move. After that `run_locked` until `RUN_UNLOCK` (prevents stuttering). `just_tired` (one frame) →
  "Zmęczony!" floater. Tired animation in `Player.draw`/`_draw_tired` (breathing pulse, sweat drops, breath puffs).
  The bar is `Game.draw_stamina` (bottom of the screen; the user explicitly asked for a bar, unlike weight, which stays hidden).
- Weight: `Game.load_mult` = 1 − min(`LOAD_MAX_SLOW`, (count − `LOAD_FREE`) · `LOAD_SLOW_PER`) (constants in `settings.py`),
  passed to `Player.update(..., speed_mult)`. The weight is deliberately **not** shown anywhere in the UI (user's request).
- The player has no key for triggering rain (O was removed at the user's request). Rain comes only from
  `Weather`; in tests, call `g.weather.start_rain()`.

### Drawing order (`Game.draw`)
chunks → wet ground and puddles → stall → mushrooms → player → bears → tree canopies (semi-transparent over the player
and bears) → bear markers `!`/`?` → floating text → rain and darkening → vignette → red danger vignette and arrows →
minimap → HUD → backpack → clock widget → shop / pause / GAME OVER overlays. (The night filter goes in after the weather
and before the vignette.)

### Bear (`bear.py`)
- States: `wander` (random point or smelled mushroom) → `eat` → `wander`; on seeing the player: `alert` (reaction time)
  → `chase`; losing sight for `LOSE_TIME` → `search` (last known position, looks around) → `wander`.
  Hearing a running player during `wander`/`eat` → `search`.
- Seeing = distance + FOV cone (not checked during `chase`) + `world.line_of_sight`.
- Steering: repulsion from obstacles ahead, **direction smoothing** (`self.dir`), water avoidance by trying rotated
  directions, detour after a lack of progress, and a time limit for reaching the target (`target_limit`); unreachable
  mushrooms go into `ignored`.
- `meals` counts mushrooms since the last split; `Game.split_bears` adds a new bear after `SPLIT_AFTER`
  (capped at `MAX_BEARS`).

### Mushrooms and weather
- Mushrooms spawn on forest GRASS tiles, not under canopies (they would be invisible) and preferably near trees;
  regrowth happens only outside the player's view (`min_dist`).
- `Weather.update` returns `"start"`/`"stop"`. On `"stop"` the game calls `field.burst(...)`. Wetness speeds up
  regrowth and raises the mushroom limit; when the ground dries, the surplus disappears (`DECAY_EVERY`).

### Puffball (`purchawka`)
- `mushrooms.PUFFBALL` is a separate kind (`PUFFBALL_CHANCE`), outside `KINDS`, so it never goes into the backpack.
  Bears skip it (`nearest(..., edible=True)`).
- `Game.update`: picking it up creates a `SporeCloud` in `self.clouds`. That same list object is in `world.clouds`
  (keep it in place with `self.clouds[:] = ...`). `Bear.can_see` calls `clouds.sight_blocked`.
  Drawing: clouds go after the canopies, then `draw_fog_inside`, then rain.

### Toadstool (`muchomor`)
- `mushrooms.TOADSTOOL` (`TOADSTOOL_CHANCE`), outside `KINDS`, so it never goes into the backpack.
- **Bears do eat toadstools** (they smell them with `nearest(..., skip_kinds=(PUFFBALL,))`). Eating one sets
  `Bear.boost_t = TOADSTOOL_BOOST_TIME` (30 s); `Bear.speed_mult` (`TOADSTOOL_BOOST_MULT` 1.35) multiplies the step
  in `_move_toward` (wander, search, and chase). A toadstool does **not** count toward `eaten`/`meals` (no splitting).
  `just_boosted` is set for one frame and `Game.update` turns it into a floater plus a message (when the bear is
  within 900 px). Visuals: a red glow under the bear (`draw`) and a pulsing ring above the canopies (`draw_marker`).
- `Poisoning.eaten` counts toadstools in the round: 1st → `"poison"`, 2nd (any time) → `"blackout"`,
  3rd → `"fatal"` → `Game.game_over("Zatrułeś się muchomorami!")` (`game_over(reason)` sets `over_reason`).
  `Player.update(..., controls=mapping)` remaps logical directions ({"up": "left", ...}).
- `Poisoning.draw` is drawn after the danger vignette and before the minimap/HUD; during blackout the minimap is hidden.

### Extra night darkness and flashlight price
- Recolouring all mushrooms to borowik colours at night was added and then **withdrawn at the user's request**. Do not
  bring it back; at night species are hidden by the fog, and the flashlight beam shows true colours.
- `Clock.apply` ends with `BLEND_MULT` by `1 - NIGHT_EXTRA_DIM * night` (0.10, the user's request: 10% darker at night).
- The flashlight costs 60 zł (`FLASHLIGHT_COST`, the user's request).

### Flashlight (`flashlight.py`)
- `Game.flashlight` is created once in `Game.__init__` (building the mask takes ~50 ms); `new_round` zeroes `charge`/`on`.
  `charge` is in real seconds (`FLASHLIGHT_HOURS * SECONDS_PER_HOUR` = 180 s) and drains only while `on` and only in the
  `play` state. A new one can be bought (`L` in the shop, `FLASHLIGHT_COST`, `Market.spend`) only when the current one is
  empty; after purchase it is off.
- Beam effect: in `Game.draw`, when `night_level() > 0` and the flashlight is on, `capture()` (before
  `daytime.apply`) copies the **unfiltered** screen in the beam's bounding box onto a SRCALPHA surface (alpha forced
  to 255 with `BLEND_RGBA_MAX`), multiplies it by the cone mask (`BLEND_RGBA_MULT`; mask rotated by `player.angle`,
  quantised to 2°), and `apply()` (after the filter) pastes it back. So the beam shows true colours with no blur or fog.
  Cost at night ~8 ms/frame for the whole `draw`.
- Widget below the clock (`clock_y + 68`), visible only when `owned`.

### HUD
- At the user's request the HUD does **not** show FPS, the weather, or the seed. By default only "H - pomoc" is shown;
  H toggles the full help (`Game.show_help`, default `False`).

### Save / load (`savegame.py`)
- Saving happens **only in the shop** (key **Z**, `Game.shop_key`); loading only from the command line:
  `main.py <file.json>` (an int argument is still a seed; a bare file name is also looked up in `zapisy/`).
  There is no in-game load menu (user's spec). Bad file → `SaveError` → message on stderr, exit code 1.
- The world is **not** serialised: it is regenerated from `seed`. `Game(seed, save_data)` builds the world, then
  `restore()`: if `round != 1`, it re-runs `new_round` with the saved round (mushroom sprites etc. depend on `rseed`),
  then overwrites the mutable state: player, backpack, market (incl. sales/history/noise), mushrooms, bears,
  weather, poison, clouds, clock, flashlight, and **all `random.Random` states** (`getstate` → JSON lists).
- Bears: object references are dropped (`food`, `ignored`, `check_*`); a bear in `eat` is restored as `wander`.
- After loading: `state = "shop"`, `stall_armed = False` (as at save time).
- `SAVE_VERSION`: when adding new state to the game, add it to `snapshot`/`restore`; if the format changes
  incompatibly, bump the version. Test: snapshot → save → `Game(None, read(path))` → snapshot must match
  (apart from `saved_at`).

## Pitfalls already hit (do not repeat)

1. **Alpha channel on macOS:** the screen is ARGB, and `Surface(...)` / `convert()` inherit that alpha. Blitting
   a transparent SRCALPHA layer onto such a surface zeroes its alpha, and the next blit with alpha (vignette)
   overwrites the colour; this once made lakes disappear. **Opaque surfaces (chunks, minimap, full-screen overlays)
   must be created with `world.opaque_surface(size)`** (XRGB, no alpha).
2. **`smoothscale` mapping:** a destination pixel `x` maps to source `x*(N-1)/W`. To interpolate tile colours without
   seams use `W = (N-1)*TILE` and an offset of `-TILE//2` (see `_render_chunk`).
3. **Bear steering:** without direction smoothing and progress-based stuck detection, the bear oscillates in front
   of a trunk (moves but stays in place). Do not remove `self.dir`, `check_*`, or `target_limit`.
4. Headless screenshot scenes: the minimap covers the top-right corner and bushes block line of sight. Pick test
   positions accordingly.

## Possible next steps (not implemented)
Sounds, buying mushrooms/items, rain masking footstep noise, saving settings, an in-game load menu.
