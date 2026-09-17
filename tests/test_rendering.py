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


@pytest.mark.parametrize("style", ["lichess", "chess.com"])
@pytest.mark.parametrize("orientation", ["white", "black"])
@pytest.mark.parametrize("coordinates", ["false", "true"])
def test_explicit_destination_markers_match_legal_moves(style, orientation, coordinates):
    query = dict(fen=LEGAL_HINT_FEN, size=720, orientation=orientation,
                 coordinates=coordinates, legalMoveStyle=style)
    for path in ("/board.png", "/board.annotations.json"):
        derived_status, _, derived = get_response(
            request_url(path, **query, legalMoves="e4d6,e4f6")
        )
        explicit_status, _, explicit = get_response(
            request_url(path, **query, destinationMarkers="d6:dot,f6:capture")
        )
        assert derived_status == explicit_status == 200
        if path.endswith(".png"):
            assert decode_png(explicit).tobytes() == decode_png(derived).tobytes()
        else:
            assert json.loads(explicit) == json.loads(derived)


@pytest.mark.parametrize("path", ["/board.svg", "/board.png", "/board.annotations.json"])
def test_explicit_destination_markers_do_not_require_legal_moves_or_occupancy(path):
    status, _, payload = get_response(request_url(
        path, fen=PAWN_FEN, destinationMarkers="e4:dot,f6:capture",
    ))
    assert status == 200
    if path.endswith(".json"):
        assert [value["kind"] for value in json.loads(payload)["overlays"]] == [
            "legal_destination_dot", "legal_destination_capture",
        ]
    elif path.endswith(".svg"):
        assert b'class="legal-destination lichess dot"' in payload
        assert b'class="legal-destination lichess capture"' in payload


@pytest.mark.parametrize("path", ["/board.svg", "/board.png", "/board.annotations.json"])
@pytest.mark.parametrize("markers", [
    "", "e4", "a9:dot", "e4:ring", "e4:dot,", "e4:dot:extra",
    "e4:dot,e4:dot", "e4:dot,e4:capture",
])
def test_explicit_destination_markers_reject_malformed_or_duplicate_values(path, markers):
    assert get_response(request_url(path, fen=EMPTY_FEN, destinationMarkers=markers))[0] == 400


@pytest.mark.parametrize("path", ["/board.svg", "/board.png", "/board.annotations.json"])
def test_explicit_destination_markers_reject_repeated_parameters_and_mixed_inputs(path):
    url = request_url(path, fen=EMPTY_FEN, destinationMarkers="e4:dot")
    assert get_response(url + "&destinationMarkers=f6:capture")[0] == 400
    assert get_response(request_url(
        path, fen=LEGAL_HINT_FEN, destinationMarkers="f6:capture", legalMoves="e4d6",
    ))[0] == 400


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

    assert first == second
    assert b'fill="#5260ab"' in first[2]
    assert b'fill="#394377"' in first[2]


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
        "userHighlights": "e4:red:chess.com",
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
    assert response["overlays"][3]["tail_xy"] == [202.5, 276.3]
    assert response["overlays"][3]["head_xy"] == [202.5, 202.5]
    _, _, svg_data = get_response(request_url("/board.svg", **query))
    assert b'class="user-highlight chess-com"' in svg_data
    arrowhead_bbox = response["overlays"][3]["arrowhead_bbox_xyxy"]
    assert arrowhead_bbox[3] - arrowhead_bbox[1] < BOARD_SIZE / 8
    arrow_obb = response["overlays"][3]["obb_xyxyxyxy"]
    assert len(arrow_obb) == 4
    assert all(len(point) == 2 for point in arrow_obb)
    for overlay in response["overlays"]:
        left, top, right, bottom = overlay["bbox_xyxy"]
        assert 0 <= left < right <= BOARD_SIZE
        assert 0 <= top < bottom <= BOARD_SIZE


@pytest.mark.parametrize("arrow_style", ["lichess", "chess.com"])
@pytest.mark.parametrize("arrow", ["Ge2e4", "Bb1c3", "Re4b5"])
@pytest.mark.parametrize("orientation,coordinates", [("white", "false"), ("black", "true")])
@pytest.mark.parametrize("size", [320, 640, 960])
def test_painted_arrow_landmarks_agree_with_png(arrow_style, arrow, orientation, coordinates, size):
    query = {
        "fen": EMPTY_FEN, "size": size, "arrowStyle": arrow_style,
        "orientation": orientation, "coordinates": coordinates,
    }
    status, _, background = get_response(request_url("/board.png", **query))
    assert status == 200
    query["arrows"] = arrow
    status, _, png = get_response(request_url("/board.png", **query))
    assert status == 200
    status, _, payload = get_response(request_url("/board.annotations.json", **query))
    assert status == 200
    annotation, = json.loads(payload)["overlays"]
    image = decode_png(png)
    assert image.size == (size, size)
    difference = ImageChops.difference(image, decode_png(background)).convert("RGB")
    # Both endpoints must touch painted pixels, allowing the rasterizer's edge antialiasing.
    for name in ("head_xy", "tail_xy"):
        x, y = annotation[name]
        assert difference.crop((round(x) - 2, round(y) - 2, round(x) + 3, round(y) + 3)).getbbox()
    changed = difference.getbbox()
    assert changed is not None
    assert all(
        abs(actual - expected) <= 2
        for actual, expected in zip(changed, annotation["bbox_xyxy"], strict=True)
    )


def test_same_square_circles_do_not_claim_painted_arrow_keypoints():
    status, _, payload = get_response(
        request_url("/board.annotations.json", fen=EMPTY_FEN, arrows="Ge4", size=360)
    )
    assert status == 200
    annotation, = json.loads(payload)["overlays"]
    assert annotation["head_xy"] == annotation["tail_xy"]
    assert "arrowhead_bbox_xyxy" not in annotation


@pytest.mark.parametrize("piece_set", ["cburnett", "dubrovny"])
@pytest.mark.parametrize("orientation", ["white", "black"])
def test_ghost_squares_fade_complete_custom_piece_and_preserve_annotations(piece_set, orientation):
    query = {
        "fen": PAWN_FEN, "pieceSet": piece_set, "orientation": orientation,
        "size": 360, "arrows": "Ga4h4", "userHighlights": "e4:red:lichess",
    }
    without_piece = {**query, "fen": EMPTY_FEN}
    status, _, background = get_response(request_url("/board.png", **without_piece))
    assert status == 200
    status, _, sprite = get_response(request_url("/piece.png", piece="P", pieceSet=piece_set, size=45))
    assert status == 200
    expected = decode_png(background)
    faded_piece = decode_png(sprite)
    faded_piece.putalpha(faded_piece.getchannel("A").point(lambda alpha: round(alpha * 0.3)))
    origin = (180, 180) if orientation == "white" else (135, 135)
    expected.alpha_composite(faded_piece, origin)
    status, _, png = get_response(request_url("/board.png", **query, ghostSquares="e4"))
    assert status == 200
    # One transparency layer over the whole piece, AFTER the arrow/highlight.
    difference = ImageChops.difference(decode_png(png), expected)
    assert max(high for _, high in difference.getextrema()) <= 2
    status, _, svg_data = get_response(request_url("/board.svg", **query, ghostSquares="e4"))
    assert status == 200
    root = ElementTree.fromstring(svg_data)  # noqa: S314 - local test-app response
    assert root[-1].attrib == {"class": "ghosts", "opacity": "0.3"}
    assert root[-1][0].attrib["href"] == "#piece-wP"
    ordinary = get_response(request_url("/board.annotations.json", **query))
    ghost = get_response(request_url("/board.annotations.json", **query, ghostSquares="e4"))
    assert ordinary == ghost


@pytest.mark.parametrize("path", ["/board.svg", "/board.png", "/board.annotations.json"])
@pytest.mark.parametrize("ghost_squares", ["d4", "i9", "", "e4,", "e4,e4", "e4&ghostSquares=e4"])
def test_ghost_squares_reject_empty_unoccupied_invalid_and_duplicate_requests(path, ghost_squares):
    # The final case deliberately repeats the HTTP parameter rather than a list item.
    url = request_url(path, fen=PAWN_FEN) + "&ghostSquares=" + ghost_squares
    status, _, _ = get_response(url)
    assert status == 400


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


@pytest.mark.parametrize("style", ["lichess", "chess.com"])
@pytest.mark.parametrize("orientation", ["white", "black"])
def test_inboard_coordinates(style, orientation):
    query = dict(fen=PAWN_FEN, size=640, orientation=orientation, coordinateStyle=style)
    plain = get_response(request_url("/board.png", **query))[2]
    status, _, annotated = get_response(request_url("/board.png", **query, coordinates="true"))
    assert status == 200
    assert decode_png(plain).size == decode_png(annotated).size == (640, 640)
    assert plain != annotated
    _, _, svg = get_response(request_url("/board.svg", **query, coordinates="true"))
    root = ElementTree.fromstring(svg)
    assert root.get("viewBox") == "0 0 360 360"
    coords = next(e for e in root if e.get("class") == f"coordinates {style}")
    assert len(coords) == 16
    assert get_response(request_url("/board.annotations.json", **query))[2] == get_response(
        request_url("/board.annotations.json", **query, coordinates="true")
    )[2]


def test_invalid_coordinate_style():
    status, _, body = get_response(
        request_url("/board.svg", fen=PAWN_FEN, coordinateStyle="unknown")
    )
    assert status == 400
    assert b"coordinateStyle is not supported" in body
