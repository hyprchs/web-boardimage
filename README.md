web-boardimage
==============

An HTTP service that renders chess board images.

Installation
------------

Requires Python and [uv](https://docs.astral.sh/uv/):

```
git submodule update --init --recursive
```

Usage
-----

```
uv run python server.py [--port 8080] [--bind 127.0.0.1]
```

Docker
------

Build and run:

```
git submodule update --init --recursive
docker build -t web-boardimage .
docker run --rm -p 8080:8080 web-boardimage
```

Or with compose:

```
git submodule update --init --recursive
docker compose up --build
```

HTTP API
--------

### `GET /board.svg` render an SVG

name | type | default | description
--- | --- | --- | ---
**fen** | string | required | FEN of the position with at least the board part
**orientation** | string | white | `white` or `black`
**size** | int | 360 | The width and height of the image
**lastMove** | string | *(none)* | The last move to highlight, e.g., `f4g6`
**check** | string | *(none)* | A square to highlight for check, e.g., `h8`
**arrows** | string | *(none)* | Draw arrows and circles, e.g., `Ge6g8,Bh7`, possible color prefixes: `G`, `B`, `R`, `Y`
**arrowStyle** | string | `lichess` | Arrow geometry: `lichess` or `chess.com`
**legalMoves** | string | *(none)* | Comma-separated legal UCI moves with one source square, e.g., `e2e4,e2e3`
**legalMoveStyle** | string | `lichess` | Legal-destination geometry: `lichess` or `chess.com`
**userHighlights** | string | *(none)* | Comma-separated `square:color:palette` values, e.g., `e4:green:lichess,d5:red:chess.com`
**squares** | string | *(none)* | Marked squares, e.g., `a3,c3`
**coordinates** | bool | *false* | Show a coordinate margin
**colors** | string | lichess-brown | Theme: `wikipedia`, `lichess-brown`, `lichess-blue`, `chess-com`, `random` (generate one on the fly)
**randomSeed** | int | *(none)* | Make all randomized choices deterministic for a given seed
**pieceSet** | string | `cburnett` | Optional piece set; see [supported piece sets](#supported-piece-sets)
**avoidMono** | bool | *false* | Exclude `mono` when `pieceSet=random`

```
https://backscattering.de/web-boardimage/board.svg?fen=5r1k/1b4pp/3pB1N1/p2Pq2Q/PpP5/6PK/8/8&lastMove=f4g6&check=h8&arrows=Ge6g8,Bh7&squares=a3,c3
```

![example board image](https://backscattering.de/web-boardimage/board.svg?fen=5r1k/1b4pp/3pB1N1/p2Pq2Q/PpP5/6PK/8/8&lastMove=f4g6&check=h8&arrows=Ge6g8,Bh7&squares=a3,c3)

### `GET /board.png` render a PNG

Accepts the same query parameters as `/board.svg`.

**`GET /board.annotations.json` returns overlay annotations.**

Accepts the same query parameters as `/board.svg`. Coordinates use the rendered
image's pixel coordinate system. Arrow entries additionally include their
arrowhead box, ordered tail/head points, and oriented bounds.

```json
{
  "width": 360,
  "height": 360,
  "overlays": [
    {
      "kind": "arrow",
      "color": "green",
      "bbox_xyxy": [178.332893, 201.279052, 219.289822, 297.023014],
      "arrowhead_bbox_xyxy": [188.4375, 202.851562, 216.5625, 223.945312],
      "tail_xy": [202.5, 292.5],
      "head_xy": [202.5, 202.5],
      "obb_xyxyxyxy": [
        [219.289822, 205.30861],
        [205.868202, 297.023014],
        [178.332893, 292.993457],
        [191.754514, 201.279052]
      ]
    }
  ]
}
```

### `GET /piece.svg` and `/piece.png` render a piece

name | type | default | description
--- | --- | --- | ---
**pieceSet** | string | `cburnett` | Optional piece set; see [supported piece sets](#supported-piece-sets)
**avoidMono** | bool | *false* | Exclude `mono` when `pieceSet=random`
**randomSeed** | int | *(none)* | Make all randomized choices deterministic for a given seed
**piece** | char | required | Piece letter: `p`, `n`, `b`, `r`, `q`, `k` for pawn, knight, bishop, rook, queen, king; uppercase is white, lowercase is black
**size** | int | required | The width and height of the bounding-box/image/square, from 10 through 1000 pixels inclusive

#### Supported Piece Sets

<details>
<summary>Show all supported piece sets</summary>

The default piece set is `cburnett`. Use `random` to choose a piece set at render time.

- `alpha`
- `anarcandy`
- `caliente`
- `california`
- `cardinal`
- `cburnett`
- `celtic`
- `chess7`
- `chessnut`
- `companion`
- `cooke`
- `dubrovny`
- `fantasy`
- `fresca`
- `gioco`
- `governor`
- `horsey`
- `icpieces`
- `kiwen-suwi`
- `kosal`
- `leipzig`
- `letter`
- `libra`
- `maestro`
- `merida`
- `monarchy`
- `mono`
- `mpchess`
- `pirouetti`
- `pixel`
- `reillycraig`
- `riohacha`
- `shapes`
- `spatial`
- `staunty`
- `tatiana`
- `random`

</details>

License
-------

web-boardimage is licensed under the AGPLv3+. See LICENSE.txt for the full
license text.
