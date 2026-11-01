"""Extract the existing menu's brush artwork without its paper rectangle."""
from statistics import median
from PIL import Image


def extract_brush(source, kind):
    left, top, right, bottom = (230, 65, 565, 145) if kind == "orange" else (595, 68, 940, 143)
    crop = source.crop((left, top, right, bottom)).convert("RGBA")
    pixels = crop.load()
    if kind == "black":
        # Estimate the underlying paper separately in every column. A single
        # brightness threshold also picked up the paper's dark folds and frame.
        gray = source.convert("L")
        above = [median(gray.getpixel((left+x, y)) for y in range(49, 63)) for x in range(crop.width)]
        below = [median(gray.getpixel((left+x, y)) for y in range(157, 169)) for x in range(crop.width)]
    for y in range(crop.height):
        ratio = y / max(1, crop.height-1)
        for x in range(crop.width):
            r, g, b, _ = pixels[x, y]
            if kind == "orange":
                alpha = max(0, min(255, (r-g-18)*8))
            else:
                paper = above[x]*(1-ratio) + below[x]*ratio
                luminance = gray.getpixel((left+x, top+y))
                alpha = max(0, min(245, (paper-luminance-8)*7.5))
            edge = min(1, x/2, (crop.width-1-x)/2, y/2, (crop.height-1-y)/2)
            # RGB and shape come from the same original crop; only alpha changes.
            pixels[x, y] = (r, g, b, round(alpha*max(0, edge)))
    return crop
