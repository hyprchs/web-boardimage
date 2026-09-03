import asyncio
import json
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlencode
from xml.etree import ElementTree

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, ImageChops
from server import Service

EMPTY_FEN = "8/8/8/8/8/8/8/8 w - - 0 1"
PAWN_FEN = "8/8/8/8/4P3/8/8/8 w - - 0 1"
LEGAL_HINT_FEN = "4k3/8/5p2/8/4N3/8/8/4K3 w - - 0 1"
BOARD_SIZE = 360
SQUARE_SIZE = BOARD_SIZE // 8
DUBROVNY_PAWN_SIZE = 189
CARDINAL_KING_SIZE = 180
# Human-reviewed Cardinal rendering baseline. The previous renderer differs.
CARDINAL_WHITE_KING_PIXELS_SHA256 = (
    "e7586682f682a5e4250081677220980895eeec6122f2accb7ea237525a11fd7b"
)


def request_url(path, **query):
    return f"{path}?{urlencode(query)}" if query else path


def create_test_app():
    app = web.Application()
    service = Service()
    app.router.add_get("/board.png", service.render_png)
    app.router.add_get("/board.svg", service.render_svg)
    app.router.add_get("/board.annotations.json", service.render_annotations)
    app.router.add_get("/piece.png", service.render_piece_png)
    app.router.add_get("/piece.svg", service.render_piece_svg)
    return app


async def fetch_response(path):
    async with TestClient(TestServer(create_test_app())) as client:
        response = await client.get(path)
        return response.status, response.content_type, await response.read()


def get_response(path):
    return asyncio.run(fetch_response(path))


def decode_png(png_data):
    return Image.open(BytesIO(png_data)).convert("RGBA")


@pytest.mark.parametrize(
    ("orientation", "square_origin"),
    [
        ("white", (4 * SQUARE_SIZE, 4 * SQUARE_SIZE)),
        ("black", (3 * SQUARE_SIZE, 3 * SQUARE_SIZE)),
    ],
)
def test_board_svg_places_piece_on_expected_square(orientation, square_origin):
    status, content_type, svg_data = get_response(
        request_url("/board.svg", fen=PAWN_FEN, size=BOARD_SIZE, orientation=orientation)
    )

    assert status == 200
    assert content_type == "image/svg+xml"
    root = ElementTree.fromstring(svg_data)  # noqa: S314 - local test-app response
    x, y = square_origin
    assert [
        element.attrib["transform"]
        for element in root.iter()
        if element.tag.endswith("use") and element.attrib.get("href") == "#piece-wP"
    ] == [f"translate({x}, {y})"]


@pytest.mark.parametrize(
    ("orientation", "square_origin"),
    [
        ("white", (4 * SQUARE_SIZE, 4 * SQUARE_SIZE)),
        ("black", (3 * SQUARE_SIZE, 3 * SQUARE_SIZE)),
    ],
)
def test_board_png_changes_only_the_piece_square(orientation, square_origin):
    query = {"size": BOARD_SIZE, "orientation": orientation}
    status, content_type, empty_png = get_response(
        request_url("/board.png", fen=EMPTY_FEN, **query)
    )
    assert status == 200
    assert content_type == "image/png"

    status, content_type, pawn_png = get_response(
        request_url("/board.png", fen=PAWN_FEN, **query)
    )
    assert status == 200
    assert content_type == "image/png"

    empty_image = decode_png(empty_png)
    pawn_image = decode_png(pawn_png)
    assert empty_image.size == pawn_image.size == (BOARD_SIZE, BOARD_SIZE)
    changed_bounds = ImageChops.difference(pawn_image, empty_image).convert("RGB").getbbox()
    assert changed_bounds is not None
    left, top, right, bottom = changed_bounds
    x, y = square_origin
    assert x <= left < right <= x + SQUARE_SIZE
    assert y <= top < bottom <= y + SQUARE_SIZE


def test_dubrovny_piece_png_is_visible_at_requested_size():
    status, content_type, png_data = get_response(
        request_url(
            "/piece.png", piece="P", size=DUBROVNY_PAWN_SIZE, pieceSet="dubrovny"
        )
    )

    assert status == 200
    assert content_type == "image/png"
    rendered = decode_png(png_data)
    assert rendered.size == (DUBROVNY_PAWN_SIZE, DUBROVNY_PAWN_SIZE)
    assert rendered.getchannel("A").getbbox() is not None


def test_cardinal_king_png_matches_reviewed_rendering():
    status, content_type, png_data = get_response(
        request_url(
            "/piece.png", piece="K", size=CARDINAL_KING_SIZE, pieceSet="cardinal"
        )
    )

    assert status == 200
    assert content_type == "image/png"
    rendered = decode_png(png_data)
    assert rendered.size == (CARDINAL_KING_SIZE, CARDINAL_KING_SIZE)
    assert sha256(rendered.tobytes()).hexdigest() == CARDINAL_WHITE_KING_PIXELS_SHA256


@pytest.mark.parametrize(
    ("arrow_style", "expected_class"),
    [("lichess", "arrow lichess"), ("chess.com", "arrow chess-com")],
)
def test_board_svg_uses_requested_arrow_style(arrow_style, expected_class):
    status, content_type, svg_data = get_response(
        request_url(
            "/board.svg",
            fen=EMPTY_FEN,
            size=BOARD_SIZE,
            arrows="Ge2e4",
            arrowStyle=arrow_style,
        )
    )

    assert status == 200
    assert content_type == "image/svg+xml"
    root = ElementTree.fromstring(svg_data)  # noqa: S314 - local test-app response
    assert any(element.attrib.get("class") == expected_class for element in root.iter())


def test_board_svg_uses_chess_com_colors():
    status, content_type, svg_data = get_response(
        request_url(
            "/board.svg",
            fen=PAWN_FEN,
            size=BOARD_SIZE,
            lastMove="e3e4",
            colors="chess-com",
        )
    )

    assert status == 200
    assert content_type == "image/svg+xml"
    assert all(
        color in svg_data
        for color in (b"#ebecd0", b"#779556", b"#f5f682", b"#b9ca43")
    )


def test_random_board_colors_are_repeatable_with_a_seed():
    query = {"fen": EMPTY_FEN, "colors": "random", "randomSeed": 20260808}

    first = get_response(request_url("/board.svg", **query))
    second = get_response(request_url("/board.svg", **query))
    different = get_response(request_url("/board.svg", **{**query, "randomSeed": 20260809}))

    assert first == second
    assert first != different


def test_random_board_colors_reject_an_invalid_seed():
    status, _, _ = get_response(
        request_url("/board.svg", fen=EMPTY_FEN, colors="random", randomSeed="nope")
    )

    assert status == 400


def test_random_piece_set_is_repeatable_with_the_request_seed():
    query = {
        "fen": PAWN_FEN,
        "colors": "lichess-brown",
        "pieceSet": "random",
        "randomSeed": 20260808,
    }

    first = get_response(request_url("/board.svg", **query))
    second = get_response(request_url("/board.svg", **query))

    assert first == second


def test_board_annotations_are_renderer_authoritative_and_scaled_to_png():
    query = {
        "fen": LEGAL_HINT_FEN,
        "size": BOARD_SIZE,
        "coordinates": "false",
        "arrows": "Ge2e4",
        "arrowStyle": "chess.com",
        "legalMoves": "e4d6,e4f6",
        "legalMoveStyle": "chess.com",
        "userHighlights": "e4:red:lichess",
    }
    status, content_type, payload = get_response(
        request_url("/board.annotations.json", **query)
    )

    assert status == 200
    assert content_type == "application/json"
    response = json.loads(payload)
    assert response["width"] == response["height"] == BOARD_SIZE
    assert [overlay["kind"] for overlay in response["overlays"]] == [
        "legal_destination_dot",
        "legal_destination_capture",
        "user_highlight",
        "arrow",
    ]
    assert response["overlays"][2]["color"] == "red"
    assert response["overlays"][3]["color"] == "green"
    assert response["overlays"][3]["tail_xy"] == [202.5, 292.5]
    assert response["overlays"][3]["head_xy"] == [202.5, 202.5]
    anchor_bbox = response["overlays"][3]["anchor_bbox_xyxy"]
    assert anchor_bbox[3] - anchor_bbox[1] < BOARD_SIZE / 8
    arrow_obb = response["overlays"][3]["obb_xyxyxyxy"]
    assert len(arrow_obb) == 4
    assert all(len(point) == 2 for point in arrow_obb)
    for overlay in response["overlays"]:
        left, top, right, bottom = overlay["bbox_xyxy"]
        assert 0 <= left < right <= BOARD_SIZE
        assert 0 <= top < bottom <= BOARD_SIZE


@pytest.mark.parametrize(
    "query",
    [
        {"fen": PAWN_FEN, "legalMoveStyle": "unknown"},
        {"fen": PAWN_FEN, "userHighlights": "e4:red"},
        {"fen": PAWN_FEN, "legalMoves": "e2e4,d2d4"},
        {"fen": PAWN_FEN, "legalMoves": "e2e5"},
    ],
)
def test_board_annotations_reject_invalid_overlay_requests(query):
    status, _, _ = get_response(request_url("/board.annotations.json", **query))

    assert status == 400


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/board.svg", {}),
        ("/board.svg", {"fen": PAWN_FEN, "coordinates": "perhaps"}),
        ("/board.svg", {"fen": PAWN_FEN, "arrowStyle": "unknown"}),
        ("/piece.png", {"piece": "X", "size": 180}),
        ("/piece.png", {"piece": "P", "size": 9}),
        ("/piece.png", {"piece": "P", "size": 180, "pieceSet": "unknown"}),
    ],
)
def test_invalid_request_returns_bad_request(path, query):
    status, _, _ = get_response(request_url(path, **query))

    assert status == 400
