from __future__ import annotations

from collections import deque
import re
from typing import Iterable, Mapping

import chess
import chess.svg as svg
import resvg_py

Arrow = svg.Arrow


def available_piece_sets() -> list[str]:
    return svg.available_piece_sets()


def render_svg_to_png(svg_data: str) -> bytes:
    # CSS defines 96 pixels per inch; bundled piece SVGs use mm and pt sizes.
    return resvg_py.svg_to_bytes(svg_string=svg_data, dpi=96)


def render_board_svg(
    board: chess.BaseBoard | None = None,
    *,
    orientation: chess.Color = chess.WHITE,
    lastmove: chess.Move | None = None,
    check: chess.Square | None = None,
    arrows: Iterable[svg.Arrow | tuple[chess.Square, chess.Square]] = (),
    arrow_style: svg.ArrowStyle = "lichess",
    squares: chess.IntoSquareSet | None = None,
    size: int | None = None,
    coordinates: bool = True,
    colors: Mapping[str, str] | None = None,
    piece_set: str | None = None,
) -> str:
    return _deduplicate_svg_attrs(
        svg.board(
            board,
            orientation=orientation,
            lastmove=lastmove,
            check=check,
            arrows=arrows,
            arrow_style=arrow_style,
            squares=squares,
            size=size,
            coordinates=coordinates,
            colors=dict(colors or {}),
            piece_set=piece_set,
        )
    )


def render_board_png(
    board: chess.BaseBoard | None = None,
    **kwargs: object,
) -> bytes:
    return render_svg_to_png(render_board_svg(board, **kwargs))


def render_piece_svg(
    piece: chess.Piece,
    *,
    size: int | None = None,
    piece_set: str | None = None,
) -> str:
    return _deduplicate_svg_attrs(svg.piece(piece, size=size, piece_set=piece_set))


def render_piece_png(
    piece: chess.Piece,
    *,
    size: int | None = None,
    piece_set: str | None = None,
) -> bytes:
    return render_svg_to_png(render_piece_svg(piece, size=size, piece_set=piece_set))


def _split_not_in_quotes(
    value: str,
    delimiter: str = " ",
    quotes: list[tuple[str, str]] | None = None,
) -> list[str]:
    if quotes is None:
        quotes = [('"', '"'), ("'", "'")]
    if not all(len(open_quote) == len(close_quote) == 1 for open_quote, close_quote in quotes):
        raise ValueError("All quotes must be exactly one character long")

    stack: deque[str] = deque()
    splits: list[str] = []
    current: list[str] = []
    for character in value:
        if not stack and character == delimiter:
            splits.append("".join(current))
            current = []
        else:
            current.append(character)
        if stack and character == stack[-1]:
            stack.pop()
        elif not stack:
            for open_quote, close_quote in quotes:
                if character == open_quote:
                    stack.append(close_quote)
                    break
    if current:
        splits.append("".join(current))
    return splits


def _deduplicate_svg_attrs(svg_string: str) -> str:
    pattern = re.compile(r"<svg ?([^>]*)>")
    match = pattern.match(svg_string)
    if match is None:
        raise ValueError("Expected an SVG opening tag")
    attrs: dict[str, str] = {}
    for attr in _split_not_in_quotes(match.group(1)):
        key, value = attr.split("=", 1)
        attrs[key] = value
    new_attrs = " ".join(f"{key}={value}" for key, value in attrs.items())
    return pattern.sub(f"<svg {new_attrs}>", svg_string, count=1)
