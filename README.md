# foodchain

Discrete-grid ecosystem game. Climb the food chain from omnivore to apex by
eating the right things, hiding from the wrong ones, and not starving.

## Play

    python main.py --species phase2 --play

Welcome screen asks for a seed. The last two digits of the seed set how many
apex predators spawn at game start — seed ending `00` is chill mode, seed
ending `99` is nightmare.

### Controls
| key | action |
|-----|--------|
| arrows / WASD | move (or attack if edible prey there) |
| `.` / SPACE | wait one turn |
| `1` | dash (unlock L1) — up to 2 cells in a direction |
| `2` | hide (unlock L2) — invisible at distance > 1 for 3 turns |
| ESC | cancel pending ability |
| `r` | restart after death |
| `q` | quit |

### Tier progression
Eat enough of your current tier to unlock the next. Passive **dominance**
kicks in at level 3+ — the named predator stops hunting you entirely.

| level | food unlock | passive reward |
|-------|-------------|----------------|
| 0 | grass, multiplier | — |
| 1 | + hider | dash ability |
| 2 | + runner | hide ability |
| 3 | + stalker | stalker can no longer eat you |
| 4 | + sprinter | sprinter can no longer eat you |
| 5 | + apex | apex can no longer eat you — eat one to win |

## Observer mode
For watching the ecology without a player:

    python main.py --species phase2                   # flat grid
    python main.py --species phase2 --biomes          # with terrain

## Headless tuning

    python -m scripts.tune --species phase2 --ticks 3000 --every 100 > run.csv

## Ship to itch.io (browser build)

    pip install pygbag
    ./scripts/build-web.sh

This produces `build/web.zip` ready for upload. Upload it on itch.io as
an HTML5 project, tick *"This file will be played in the browser"*, and
set viewport to `1004 × 556`.

Test locally before uploading:

    python -m pygbag --template pygbag/default.tmpl main.py

Then open `http://localhost:8000`.

### Why a build script instead of plain `pygbag main.py`

Three pygbag 0.9.3 quirks the script papers over:

1. `pygbag --archive` only bundles `index.html`, `favicon.png`, and
   `foodchain.apk` into `web.zip`. The browser runtime also requests
   `foodchain.tar.gz` as an apk-parse fallback — without it, an apk
   parse failure gives a silent blank screen. The script appends the
   tar.gz after pygbag finishes.
2. The stock template references `/browserfs.min.js` which no longer
   exists on the CDN (404 in browser). Our `pygbag/default.tmpl` has
   that line removed; `--template` points pygbag at it.
3. Under pygbag, `main.py`'s directory isn't on `sys.path` by default,
   so package imports silently fail. `main.py` inserts the dir itself.

## Layout
    foodchain/sim/        headless sim core (no pygame)
    foodchain/render/     pygame renderer
    scripts/tune.py       CLI: N ticks, population CSV
    tests/test_world.py   sanity + mechanics tests
    main.py               entrypoint (async, pygbag-friendly)
