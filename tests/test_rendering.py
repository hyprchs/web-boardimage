import unittest

import chess.svg

from server import render_svg_to_png


class TestRendering(unittest.TestCase):
    def test_renders_piece_with_physical_dimensions(self) -> None:
        svg_data = chess.svg.load_pieces("dubrovny")["wP"]
        self.assertTrue(render_svg_to_png(svg_data).startswith(b"\x89PNG\r\n\x1a\n"))
