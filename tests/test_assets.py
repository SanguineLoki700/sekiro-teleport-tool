from pathlib import Path
import pytest
from PIL import Image
from brush_texture import extract_brush


@pytest.mark.parametrize("kind,rectangle", [
    ("black", (595, 68, 940, 143)), ("orange", (230, 65, 565, 145)),
])
def test_original_brush_rgb_is_unchanged_and_crop_border_is_transparent(kind, rectangle):
    path = Path(__file__).resolve().parents[1] / "assets" / "menu-background.png"
    source = Image.open(path).convert("RGB").resize((1920,1080), Image.Resampling.LANCZOS)
    brush = extract_brush(source, kind)
    assert brush.convert("RGB").tobytes() == source.crop(rectangle).tobytes()
    alpha = brush.getchannel("A")
    assert alpha.getextrema()[0] == 0
    assert alpha.getextrema()[1] > 200
    for border in ((0,0,brush.width,1),(0,brush.height-1,brush.width,brush.height),
                   (0,0,1,brush.height),(brush.width-1,0,brush.width,brush.height)):
        assert alpha.crop(border).getextrema() == (0,0)
