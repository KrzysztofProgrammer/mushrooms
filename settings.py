"""Globalne ustawienia gry."""

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
TITLE = "Grzybobranie"

TILE = 32            # rozmiar kafla w pikselach
WORLD_W = 200        # szerokość świata w kaflach
WORLD_H = 150        # wysokość świata w kaflach
CHUNK = 16           # bok fragmentu (chunka) tła w kaflach
MAX_CACHED_CHUNKS = 48

WALK_SPEED = 135.0   # px/s
RUN_MULT = 1.75
PLAYER_RADIUS = 11
STAMINA_RUN_TIME = 10.0    # s - pełna wytrzymałość wystarcza na tyle sekund biegu
STAMINA_REGEN_TIME = 8.0   # s - od zera do pełna, gdy się nie biegnie
TIRED_TIME = 2.0           # s - po wyczerpaniu wytrzymałości postać stoi i łapie oddech
RUN_UNLOCK = 0.3           # po zmęczeniu można znów biec dopiero przy takiej wytrzymałości (0..1)
LOAD_FREE = 30       # tyle grzybów w plecaku nie spowalnia
LOAD_SLOW_PER = 0.01 # każdy grzyb ponad LOAD_FREE zabiera tyle prędkości (1%)
LOAD_MAX_SLOW = 0.45 # największe spowolnienie od ciężaru

# Kolory terenu
GRASS_LIGHT = (98, 150, 66)
GRASS_DRY = (128, 150, 74)
FOREST_FLOOR = (50, 86, 42)
SHORE = (92, 96, 58)
WATER_SHALLOW = (66, 128, 160)
WATER_DEEP = (44, 98, 138)

ROAD_SHOULDER = (112, 94, 62)
ROAD_CORE = (166, 140, 98)
ROAD_RUT = (138, 114, 78)
TRAIL_SHOULDER = (88, 82, 50)
TRAIL_CORE = (136, 116, 80)
