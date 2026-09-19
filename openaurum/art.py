"""More art for the Aurum V60 scene gallery (openaurum.scenes imports this at its end).

Each scene is per_key(f): f(key, x, y) -> '#rrggbb', x and y the key center
scaled to 0-1 (rows are at y = .1 .3 .5 .7 .9; x runs over 15 key units).
Static pictures only (the per-key table is in flash), deterministic (noise()),
pure LED-friendly colors: no pastels, and orange/yellow never the only contrast.
Picked from an interview with the user on 2026-09-19: games, space, seasons,
Brazil & flags, plus a dark "Noturnas" set for the night.
"""

import math

from openaurum.scenes import GEO, H, W, mix, noise, per_key, ramp, scale


def row_of(y):
    return min(4, int(y * 5))


def col(x):
    return x * W  # key units, 0-15


def dist(x, y, cx, cy, sx=1.0, sy=1.0):
    """Distance in key units (a key is 1x1), optionally stretched."""
    return math.hypot((x * W - cx) / sx, (y * H - cy) / sy)


# --- games ----------------------------------------------------------------------------

def a_minecraft():
    ores = ["#00e5ff", "#ffd000", "#ff0000", "#00ff40"]  # diamond gold redstone emerald

    def f(k, x, y):
        r = row_of(y)
        if r == 0:
            return "#20d020" if noise(k, 21) > 0.25 else "#108010"  # grass
        if r == 1:
            return ramp(["#6b3a10", "#4a2808"], noise(k, 22))  # dirt
        if r in (2, 3):
            n = noise(k, 23)
            if n > 0.86:
                return ores[int(noise(k, 24) * 4) % 4]
            return scale("#808080", 0.55 + 0.3 * noise(k, 25))  # stone
        return "#ff4000" if noise(k, 26) > 0.35 else "#101010"  # lava / bedrock
    return per_key(f)


def a_vicecity():
    def f(k, x, y):
        if y < 0.62:
            if dist(x, y, 7.5, 1.9, 1.9, 0.95) < 1:
                return "#ffa000" if y < 0.35 else "#ff5000"  # the sun, banded
            return ramp(["#5000c0", "#ff0080"], y / 0.62)
        return "#00f0ff" if row_of(y) == 3 else "#0060ff"
    return per_key(f)


def a_lossantos():
    def f(k, x, y):
        c = ramp(["#ff5000", "#c02060", "#003050", "#001828"], y)
        if row_of(y) >= 3 and noise(k, 31) > 0.62:
            return "#ffd060"  # city lights
        return c
    return per_key(f)


def a_pacman():
    ghosts = {"AC08": "#ff0000", "AC09": "#ff40c0", "AC10": "#00ffff", "AC11": "#ff6000"}

    def f(k, x, y):
        X, r = col(x), row_of(y)
        if k in ("AC03", "AC04"):
            return "#ffe000"  # Pac-Man
        if k == "AC05":
            return "#000000"  # his mouth
        if k in ghosts:
            return ghosts[k]
        if r in (0, 4) or X < 1.6 or X > W - 1.8:
            return "#0020ff"  # maze walls
        return "#ffffff" if noise(k, 41) > 0.7 else "#000000"  # pellets
    return per_key(f)


TETRIS = {"I": "#00ffff", "O": "#ffff00", "T": "#a000ff", "S": "#00ff00",
          "Z": "#ff0000", "J": "#0000ff", "L": "#ff7000"}


def a_tetris():
    # stacked pieces, bottom 3 rows (col ranges in key units), a T falling above
    stack = [
        (4, 0, 3.0, "J"), (4, 3.0, 9.5, "I"), (4, 9.5, 12.5, "L"), (4, 12.5, 15, "O"),
        (3, 0, 2.3, "J"), (3, 2.3, 5.2, "S"), (3, 5.2, 6.2, None), (3, 6.2, 9.2, "Z"),
        (3, 9.2, 12.2, "L"), (3, 12.2, 15, "O"),
        (2, 0, 1.8, "J"), (2, 1.8, 3.8, "S"), (2, 6.8, 8.8, "Z"), (2, 11.8, 14, "I"),
    ]
    falling = {"AD07", "AE07", "AD06", "AD08"}

    def f(k, x, y):
        if k in falling:
            return TETRIS["T"]
        r, X = row_of(y), col(x)
        for sr, a, b, p in stack:
            if r == sr and a <= X < b:
                return TETRIS[p] if p else "#000000"
        return "#000000"
    return per_key(f)


def a_mario():
    def f(k, x, y):
        r, X = row_of(y), col(x)
        if r == 4:
            return "#c04000"  # ground
        if X > 12.2 and r >= 2:
            return "#00c000" if r > 2 else "#00ff30"  # pipe (rim brighter)
        if r == 2 and 4 <= X < 9:
            return "#ffc000" if k in ("AC05",) else "#a03000"  # bricks and a ? block
        if r == 0 and (2 <= X < 4.5 or 9 <= X < 11):
            return "#ffffff"  # clouds
        return "#2060ff"  # sky
    return per_key(f)


def a_hollowknight():
    mask = {"AE06", "AE08", "AD06", "AD07", "AC05", "AC08", "AB05", "AB06"}  # horns, face, chin
    eyes = {"AC06", "AC07"}

    def f(k, x, y):
        if k in eyes:
            return "#000000"
        if k in mask:
            return "#ffffff"
        glow = max(0.0, 1 - dist(x, y, 7.4, 2.4, 5.0, 2.4))
        base = mix("#000410", "#001040", noise(k, 51) * 0.6)
        c = mix(base, "#40c0ff", glow * 0.6)
        return "#a0f0ff" if noise(k, 52) > 0.93 else c  # floating souls
    return per_key(f)


def a_zelda():
    def inside(X, Y, cx, top, h):
        # isoceles triangle apex (cx, top), height h, base width 2h*0.9
        if not (top <= Y <= top + h):
            return False
        return abs(X - cx) <= (Y - top) * 0.95

    def f(k, x, y):
        X, Y = col(x), y * H
        tri = inside(X, Y, 7.5, 0.0, 2.5) or inside(X, Y, 5.1, 2.5, 2.5) or inside(X, Y, 9.9, 2.5, 2.5)
        if tri:
            return "#ffc000"
        return ramp(["#008020", "#004010"], y)
    return per_key(f)


def a_portal():
    def f(k, x, y):
        X, r = col(x), row_of(y)
        if X < 1.6 and r in (1, 2, 3):
            return "#ff6000"  # orange portal
        if X > W - 1.9 and r in (1, 2, 3):
            return "#0080ff"  # blue portal
        side = "#ff4000" if X < W / 2 else "#0050ff"
        glow = max(0.0, 1 - min(X, W - X) / 6)  # light spilling from the portals
        return mix("#101010", side, 0.12 + glow * 0.5)
    return per_key(f)


# --- space ------------------------------------------------------------------------------

def a_nebula():
    def f(k, x, y):
        if noise(k, 61) > 0.9:
            return "#ffffff"
        t = 0.5 + 0.5 * math.sin(x * 7 + y * 4 + 1.5 * math.sin(x * 3))
        c = ramp(["#2000a0", "#a000ff", "#ff0080", "#ff40a0"], t)
        return scale(c, 0.35 + 0.65 * (0.5 + 0.5 * math.sin(x * 5 - y * 6)))
    return per_key(f)


def a_galaxy():
    def f(k, x, y):
        X, Y = col(x) - 7.5, y * H - 2.5
        r = math.hypot(X / 2.2, Y)
        a = math.atan2(Y, X / 2.2)
        if r < 0.6:
            return "#fff0c0"
        arm = 0.5 + 0.5 * math.cos(2 * a - 2.4 * r)
        c = mix("#000010", ramp(["#ffd080", "#6040ff", "#2000a0"], min(1, r / 3.5)), arm ** 2)
        return "#ffffff" if noise(k, 62) > 0.94 else c
    return per_key(f)


def a_storm():
    bolt = {"AE10", "AD09", "AD08", "AC08", "AC07", "AB07", "AB06"}  # zigzag down

    def f(k, x, y):
        if k in bolt:
            return "#ffffff"
        near = min(dist(x, y, *GEO[b]) for b in bolt)
        glow = max(0.0, 1 - near / 1.8)
        c = mix("#0a0020", "#8000ff", glow * 0.8)
        return "#0060ff" if noise(k, 63) > 0.88 else c  # rain
    return per_key(f)


def a_volcano():
    def f(k, x, y):
        X, Y = col(x), y * H
        mountain = Y > 1.0 and abs(X - 7.5) < (Y - 0.6) * 1.6
        if mountain:
            if abs(X - 7.5 + 0.4 * math.sin(Y * 2)) < 0.9:
                return "#ff2000" if Y < 3 else "#ff6000"  # lava flow
            return "#000000" if noise(k, 71) > 0.3 else "#200800"  # dark rock
        if Y < 1.2 and abs(X - 7.5) < 1.5:
            return "#ffa000"  # eruption
        return ramp(["#ff2000", "#800000"], y)  # sky lit by the lava
    return per_key(f)


# --- seasons ----------------------------------------------------------------------------

def a_spring():
    def f(k, x, y):
        n = noise(k, 81)
        if row_of(y) == 4:
            return "#10a020"
        if n > 0.45:
            return "#ff2080" if n > 0.72 else "#ff60c0"  # sakura
        return "#301008"  # branches
    return per_key(f)


def a_summer():
    def f(k, x, y):
        r = row_of(y)
        sun = dist(x, y, 13.3, 0.6, 1.4, 1.0)
        if sun < 1:
            return "#ffe000"
        if r <= 1:
            return "#00a0ff"
        if r in (2, 3):
            return "#0040ff" if r == 3 else "#00c0ff"
        return "#ffb000"  # sand
    return per_key(f)


def a_autumn():
    leaves = ["#ff4000", "#ff0000", "#ffb000", "#c02000"]

    def f(k, x, y):
        n = noise(k, 91)
        if n > 0.4:
            return leaves[int(noise(k, 92) * 4) % 4]
        return "#2a1000"
    return per_key(f)


def a_winter():
    def f(k, x, y):
        if row_of(y) == 4:
            return "#ffffff" if k == "SPCE" else "#a0d0ff"
        return "#ffffff" if noise(k, 93) > 0.72 else ramp(["#000850", "#0020a0"], y)
    return per_key(f)


# --- Brazil & flags ---------------------------------------------------------------------

def a_flamengo():
    return per_key(lambda k, x, y: "#ff0000" if row_of(y) % 2 == 0 else "#000000")


def a_carnival():
    confetti = ["#ff0080", "#00ff40", "#ffe000", "#00c0ff", "#a000ff", "#ff4000"]

    def f(k, x, y):
        if noise(k, 101) > 0.35:
            return confetti[int(noise(k, 102) * 6) % 6]
        return "#100020"
    return per_key(f)


def a_festajunina():
    flags = ["#ff0000", "#ffe000", "#00c0ff", "#00ff40", "#ff00c0"]

    def f(k, x, y):
        r, X = row_of(y), col(x)
        if r == 0:
            return flags[int(X) % 5]
        if k == "SPCE":
            return "#ff4000"  # bonfire
        if r == 4 and 3.5 < X < 11:
            return "#ffa000"
        if r == 3 and 5 < X < 9.5 and noise(k, 103) > 0.3:
            return "#ff2000"  # flames reaching up
        return "#ffffff" if noise(k, 104) > 0.9 else "#000820"  # night sky + stars
    return per_key(f)


def a_ipanema():
    def f(k, x, y):
        X, Y = col(x), y * H
        # Dois Irmaos: two humps on the right
        hill = (Y > 1.0 and abs(X - 12.3) < (Y - 0.6) * 1.2) or (Y > 1.6 and abs(X - 10.6) < (Y - 1.4) * 1.3)
        r = row_of(y)
        if r == 4:
            return "#ffb030"  # sand
        if r == 3:
            return "#0060c0"  # sea
        if hill:
            return "#101808"
        return ramp(["#ff3070", "#ff7000", "#ffc000"], y / 0.6)
    return per_key(f)


def a_lencois():
    def f(k, x, y):
        n = noise(k, 111)
        lagoon = 0.5 + 0.5 * math.sin(x * 9 + y * 5) > 0.75 and row_of(y) >= 2
        if lagoon:
            return "#00e0c0" if n > 0.3 else "#0090ff"
        if row_of(y) == 0:
            return "#40a0ff"  # sky
        return mix("#ffd8a0", "#ffffff", n * 0.6)
    return per_key(f)


def a_ipe():
    def f(k, x, y):
        X, Y = col(x), y * H
        if Y > 2.8 and abs(X - 7.5) < 0.9:
            return "#3a1a08"  # trunk
        if row_of(y) == 4:
            return "#108020"
        canopy = dist(x, y, 7.5, 1.4, 5.5, 1.5)
        if canopy < 1:
            return "#ffe000" if X < 7.5 else "#a000ff"  # yellow and purple ipe
        return "#0080ff"
    return per_key(f)


def a_japan():
    return per_key(lambda k, x, y: "#ff0000" if dist(x, y, 7.3, 2.5, 1.7, 1.25) < 1 else "#c0c0c0")


def a_jamaica():
    def f(k, x, y):
        d1, d2 = abs(y - x), abs(y - (1 - x))
        if min(d1, d2) < 0.11:
            return "#ffd000"  # the saltire
        if (y > x) == (y < 1 - x):
            return "#000000"  # left and right triangles
        return "#009b3a"  # top and bottom
    return per_key(f)


def a_rainbow():
    stripes = ["#ff0000", "#ff4000", "#ffe000", "#00c000"]

    def f(k, x, y):
        r = row_of(y)
        return stripes[r] if r < 4 else mix("#0040ff", "#8000ff", x)  # blue into violet
    return per_key(f)


# --- night (V <= ~0x30: comfortable in the dark) ------------------------------------------

def dim(colors, v=0.19):
    return {k: scale(c, v) for k, c in colors.items()}


def a_bloodmoon():
    def f(k, x, y):
        d = dist(x, y, 7.4, 2.4, 2.0, 1.4)
        return "#400000" if d < 1 else ("#140000" if d < 1.4 else "#040000")
    return per_key(f)


def a_night_ember():
    def f(k, x, y):
        return ramp(["#080000", "#200200", "#301000"], y * 0.7 + noise(k, 7) * 0.5)
    return per_key(f)


def a_amber():
    return per_key(lambda k, x, y: ramp(["#1a0800", "#301400", "#1a0800"], x))


def a_night_nebula():
    return dim(a_nebula(), 0.14)


SCENES = {
    "minecraft": ("Minecraft", "Games", a_minecraft),
    "vicecity": ("Vice City", "Games", a_vicecity),
    "lossantos": ("Los Santos", "Games", a_lossantos),
    "pacman": ("Pac-Man", "Games", a_pacman),
    "tetris": ("Tetris", "Games", a_tetris),
    "mario": ("Mario", "Games", a_mario),
    "hollowknight": ("Hollow Knight", "Games", a_hollowknight),
    "zelda": ("Zelda", "Games", a_zelda),
    "portal": ("Portal", "Games", a_portal),
    "nebula": ("Nebulosa", "Espaço", a_nebula),
    "galaxy": ("Galáxia", "Espaço", a_galaxy),
    "storm": ("Tempestade", "Espaço", a_storm),
    "volcano": ("Vulcão", "Espaço", a_volcano),
    "spring": ("Primavera", "Estações", a_spring),
    "summer": ("Verão", "Estações", a_summer),
    "autumn": ("Outono", "Estações", a_autumn),
    "winter": ("Inverno", "Estações", a_winter),
    "flamengo": ("Flamengo", "Brasil e mundo", a_flamengo),
    "carnaval": ("Carnaval", "Brasil e mundo", a_carnival),
    "festajunina": ("Festa junina", "Brasil e mundo", a_festajunina),
    "ipanema": ("Ipanema", "Brasil e mundo", a_ipanema),
    "lencois": ("Lençóis Maranhenses", "Brasil e mundo", a_lencois),
    "ipe": ("Ipê", "Brasil e mundo", a_ipe),
    "japan": ("Japão", "Brasil e mundo", a_japan),
    "jamaica": ("Jamaica", "Brasil e mundo", a_jamaica),
    "rainbow": ("Arco-íris", "Brasil e mundo", a_rainbow),
    "bloodmoon": ("Lua de sangue", "Noturnas", a_bloodmoon),
    "nightember": ("Brasa noturna", "Noturnas", a_night_ember),
    "amber": ("Âmbar", "Noturnas", a_amber),
    "nightnebula": ("Nebulosa noturna", "Noturnas", a_night_nebula),
}
