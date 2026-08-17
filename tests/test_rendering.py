import struct
import unittest
import zlib

import chess
import chess.svg

from server import render_svg_to_png


def has_nontransparent_pixel(png_data: bytes) -> bool:
    offset = 8
    image_data = []

    while offset < len(png_data):
        chunk_size = struct.unpack_from(">I", png_data, offset)[0]
        chunk_type = png_data[offset + 4 : offset + 8]
        chunk_data = png_data[offset + 8 : offset + 8 + chunk_size]
        offset += chunk_size + 12

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if (bit_depth, color_type, interlace) != (8, 6, 0):
                raise AssertionError("expected a non-interlaced 8-bit RGBA PNG")
        elif chunk_type == b"IDAT":
            image_data.append(chunk_data)

    scanline_size = 1 + width * 4
    scanlines = zlib.decompress(b"".join(image_data))
    if len(scanlines) != height * scanline_size:
        raise AssertionError("invalid PNG scanline data length")
    # PNG filters operate independently per byte position, so nonzero alpha
    # survives in at least one filtered alpha byte.
    return any(
        alpha
        for row_start in range(0, len(scanlines), scanline_size)
        for alpha in scanlines[row_start + 4 : row_start + scanline_size : 4]
    )


class TestRendering(unittest.TestCase):
    def test_renders_piece_with_physical_dimensions(self) -> None:
        svg_data = chess.svg.piece(
            chess.Piece.from_symbol("P"), size=189, piece_set="dubrovny"
        )
        self.assertTrue(has_nontransparent_pixel(render_svg_to_png(svg_data)))
