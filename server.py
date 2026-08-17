#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# web-boardimage is an HTTP service that renders chess board images.
# Copyright (C) 2016-2017 Niklas Fiekas <niklas.fiekas@backscattering.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""An HTTP service that renders chess board images"""

import argparse
import asyncio
import configparser
import aiohttp.web
import os

import chess
import chess.svg as svg

import json
import random
import colorsys
from collections import deque
import re
import resvg_py

THIS_DIR = os.path.dirname(__file__)


def render_svg_to_png(svg_data: str) -> bytes:
    # CSS defines 96 pixels per inch; bundled piece SVGs use mm and pt sizes.
    return resvg_py.svg_to_bytes(svg_string=svg_data, dpi=96)


def split_not_in_quotes(
    s: str, delim: str = " ", quotes: list[tuple[str, str]] | None = None
) -> list[str]:
    """
    Split a string on a delimeter if the delimeter is not inside a pair of quotes.
    """
    if quotes is None:
        quotes = [('"', '"'), ("'", "'")]

    # Validate that the 'quotes' are all 1 character long
    assert all(
        len(q[0]) == 1 and len(q[1]) == 1 for q in quotes
    ), "All quotes must be exactly 1 character long"

    # Loop through the string and keep track of whether we are inside a quoted string using a stack
    stack = deque()
    splits = []
    current_split = []

    for char in s:
        if not stack and char == delim:
            splits.append("".join(current_split))
            current_split = []
        else:
            current_split.append(char)

        if stack and char == stack[-1]:
            stack.pop()
        elif not stack:
            for open_quote, close_quote in quotes:
                if char == open_quote:
                    stack.append(close_quote)
                    break

    # Add the last split
    if current_split:
        splits.append("".join(current_split))

    return splits


def deduplicate_svg_attrs(svg_string: str) -> str:
    """Deduplicate the attributes in the outer `<svg>` tag in the given SVG string."""

    # We just want to match the very first <svg> opening tag, ex:
    # <svg xmlns="http://www.w3.org/2000/svg" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 45 45">
    # Then we do a simple string manipulation to remove duplicate attributes
    PAT = re.compile(r"<svg ?([^>]*)>")
    svg_attrs = re.match(PAT, svg_string).group(1)

    # We shouldn't assume the attributes' values are always the same even if the attribute names are the same.
    # However, if there are two attributes with the same name, the one that will be used is the last one, so
    # as we iterate through the attrs, we can always overwrite the previous value.
    attrs = {}
    for attr in split_not_in_quotes(svg_attrs):
        key, value = attr.split("=", 1)
        attrs[key] = value

    # Reconstruct the attributes string
    new_attrs = " ".join([f"{key}={value}" for key, value in attrs.items()])
    return re.sub(PAT, f"<svg {new_attrs}>", svg_string, count=1)

PIECE_SETS = svg.available_piece_sets()
DEFAULT_PIECE_SET = "cburnett"


def query_bool(request, name, default=False):
    value = request.query.get(name)
    if value is None:
        return default
    try:
        return configparser.ConfigParser.BOOLEAN_STATES[value.lower()]
    except KeyError:
        raise aiohttp.web.HTTPBadRequest(reason=f"{name} must be a boolean") from None


def select_piece_set(request):
    piece_set = request.query.get("pieceSet", DEFAULT_PIECE_SET)
    if piece_set == "random":
        if query_bool(request, "avoidMono"):
            return random.choice([
                piece_set_name for piece_set_name in PIECE_SETS
                if piece_set_name != 'mono'
            ])
        return random.choice(PIECE_SETS)
    if piece_set not in PIECE_SETS:
        raise aiohttp.web.HTTPBadRequest(reason="invalid piece set")
    return piece_set


def load_theme(name):
    with open(os.path.join(THIS_DIR, "themes", f"{name}.json")) as f:
        return json.load(f)


THEMES = {
    name: load_theme(name) for name in ["wikipedia", "lichess-blue", "lichess-brown"]
}


# Function to generate a random color
def generate_random_color():
    h = random.random()
    s = random.uniform(0.5, 1.0)
    v = random.uniform(0.5, 1.0)
    return colorsys.hsv_to_rgb(h, s, v)


# Function to convert RGB to HEX
def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )


# Function to adjust brightness
def adjust_brightness(color, factor):
    h, s, v = colorsys.rgb_to_hsv(color[0], color[1], color[2])
    v = max(0, min(1, v * factor))
    return colorsys.hsv_to_rgb(h, s, v)


# Function to shift hue
def shift_hue(color, shift):
    h, s, v = colorsys.rgb_to_hsv(color[0], color[1], color[2])
    h = (h + shift) % 1.0
    return colorsys.hsv_to_rgb(h, s, v)


# Function to generate a color scheme
def generate_color_scheme():
    light_square_color = generate_random_color()
    dark_square_color = adjust_brightness(
        light_square_color, 0.7
    )  # Darker than light square

    light_lastmove_color = shift_hue(
        light_square_color, 0.1
    )  # Shift hue slightly for distinction
    dark_lastmove_color = shift_hue(
        dark_square_color, 0.1
    )  # Shift hue slightly for distinction

    color_scheme = {
        "square light": rgb_to_hex(light_square_color),
        "square dark": rgb_to_hex(dark_square_color),
        "square light lastmove": rgb_to_hex(light_lastmove_color),
        "square dark lastmove": rgb_to_hex(dark_lastmove_color),
    }

    return color_scheme


class Service:
    def make_svg(self, request):
        try:
            board = chess.Board(request.query["fen"])
        except KeyError:
            raise aiohttp.web.HTTPBadRequest(reason="fen required")
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="invalid fen")

        try:
            size = min(max(int(request.query.get("size", 360)), 16), 1024)
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="size is not a number")

        try:
            uci = request.query.get("lastMove") or request.query["lastmove"]
            lastmove = chess.Move.from_uci(uci)
        except KeyError:
            lastmove = None
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="lastMove is not a valid uci move")

        try:
            check = chess.parse_square(request.query["check"])
        except KeyError:
            check = None
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="check is not a valid square name")

        try:
            arrows = [
                svg.Arrow.from_pgn(s.strip())
                for s in request.query.get("arrows", "").split(",")
                if s.strip()
            ]
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="invalid arrow")

        try:
            squares = chess.SquareSet(
                chess.parse_square(s.strip())
                for s in request.query.get("squares", "").split(",")
                if s.strip()
            )
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="invalid squares")

        orientation = chess.BLACK if request.query.get("orientation", "white") == "black" else chess.WHITE

        coordinates = query_bool(request, "coordinates")

        try:
            if request.query.get("colors") == "random":
                colors = generate_color_scheme()
            else:
                colors = THEMES[request.query.get("colors", "lichess-brown")]
        except KeyError:
            raise aiohttp.web.HTTPBadRequest(reason="theme colors not found")

        piece_set = select_piece_set(request)

        return deduplicate_svg_attrs(
            svg.board(
                board,
                coordinates=coordinates,
                orientation=orientation,
                lastmove=lastmove,
                check=check,
                arrows=arrows,
                squares=squares,
                size=size,
                colors=colors,
                piece_set=piece_set,
            )
        )

    def make_piece_svg(self, request):
        piece_set = select_piece_set(request)

        try:
            raw_size = request.query.get("size")
            if raw_size is None:
                raise aiohttp.web.HTTPBadRequest(reason="size query parameter is required")
            size = int(raw_size)
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="size is not a valid number") from None
        if size < 10 or size > 1000:
            raise aiohttp.web.HTTPBadRequest(reason="size must be between 10 and 1000")

        piece_symbol = request.query.get("piece")
        if piece_symbol is None:
            raise aiohttp.web.HTTPBadRequest(reason="piece query parameter is required")
        try:
            piece = chess.Piece.from_symbol(piece_symbol)
        except ValueError:
            raise aiohttp.web.HTTPBadRequest(reason="piece is not a valid piece") from None

        piece_svg = svg.piece(piece=piece, size=size, piece_set=piece_set)

        return deduplicate_svg_attrs(piece_svg)

    async def render_piece_png(self, request):
        svg_data = self.make_piece_svg(request)
        png_data = await asyncio.to_thread(render_svg_to_png, svg_data)
        filename = request.query.get("piece", "ERROR")
        return aiohttp.web.Response(
            body=png_data,
            content_type="image/png",
            headers={"Content-Disposition": f"attachment; filename={filename}.png"},
        )

    async def render_piece_svg(self, request):
        return aiohttp.web.Response(
            text=self.make_piece_svg(request), content_type="image/svg+xml"
        )

    async def render_svg(self, request):
        return aiohttp.web.Response(
            text=self.make_svg(request), content_type="image/svg+xml"
        )

    async def render_png(self, request):
        svg_data = self.make_svg(request)
        png_data = await asyncio.to_thread(render_svg_to_png, svg_data)
        return aiohttp.web.Response(body=png_data, content_type="image/png")


def create_app():
    app = aiohttp.web.Application()
    service = Service()
    app.router.add_get("/board.png", service.render_png)
    app.router.add_get("/board.svg", service.render_svg)
    app.router.add_get("/piece.png", service.render_piece_png)
    app.router.add_get("/piece.svg", service.render_piece_svg)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", "-p", type=int, default=8080, help="web server port")
    parser.add_argument(
        "--bind", default="127.0.0.1", help="bind address (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    aiohttp.web.run_app(create_app(), port=args.port, host=args.bind, access_log=None)
