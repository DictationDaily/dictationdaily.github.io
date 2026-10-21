"""Find the box of the button or text under each step marker, for the highlight.

For every <step> in src/pages (x/y, or at= from src/coords.json) this looks at
the screenshot around the point: it fills outward over the element's own
background colour until it meets the element's edge. When that colour is just
the page (plain text on the page), it takes the block of text around the point
instead. Boxes go to src/boxes.json as [left, top, width, height] in % of the
image; a step can override with box="left,top,width,height".

usage: python3 scripts/boxes.py   (run again after new screenshots)
"""
import json
import re
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

PAGES = Path('src/pages')
COORDS = json.loads(Path('src/coords.json').read_text())
OUT = Path('src/boxes.json')

TOL = 14          # how far a colour may be from the element's background
INK = 40          # how far a pixel must be from the page to count as text
GAP = 10          # px between words or icons that still belong together


def spots():
    for page in sorted(PAGES.glob('*.html')):
        for m in re.finditer(r'<step([^>]*)>', page.read_text()):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if 'box' in a:
                continue
            for key, x, y in (('at', 'x', 'y'), ('at2', 'x2', 'y2')):
                if key in a:
                    a[x], a[y] = COORDS[a['img']][a[key]]
            for x, y in ((a.get('x'), a.get('y')), (a.get('x2'), a.get('y2'))):
                if x and y:
                    yield a['img'], float(x), float(y)


def fill(mask, sx, sy):
    """Bounding box of the region of mask connected to (sx, sy)."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    q = deque([(sy, sx)])
    seen[sy, sx] = True
    x0 = x1 = sx
    y0 = y1 = sy
    while q:
        y, x = q.popleft()
        x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return x0, y0, x1, y1


def dilate(mask, r):
    out = mask.copy()
    for d in range(1, r + 1):
        out[:, d:] |= mask[:, :-d]
        out[:, :-d] |= mask[:, d:]
    m = out.copy()
    for d in range(1, r // 2 + 1):
        out[d:, :] |= m[:-d, :]
        out[:-d, :] |= m[d:, :]
    return out


def box(img, px, py):
    a = np.asarray(img.convert('RGB')).astype(int)
    H, W, _ = a.shape
    # Work in a window around the point so a leak can't cover the whole page
    wx, wy = int(W * 0.22), int(H * 0.14)
    left, top = max(0, px - wx), max(0, py - wy)
    win = a[top:min(H, py + wy), left:min(W, px + wx)]
    cx, cy = px - left, py - top
    patch = win[max(0, cy - 10):cy + 11, max(0, cx - 10):cx + 11].reshape(-1, 3)
    colours, counts = np.unique(patch // 8, axis=0, return_counts=True)
    bg = colours[counts.argmax()] * 8 + 4
    same = np.abs(win - bg).max(axis=2) <= TOL
    # Start from the matching pixel nearest the point (it may sit on text)
    ys, xs = np.nonzero(same)
    i = ((xs - cx) ** 2 + (ys - cy) ** 2).argmin()
    x0, y0, x1, y1 = fill(same, xs[i], ys[i])
    wh, ww = same.shape
    leaked = x0 == 0 or y0 == 0 or x1 == ww - 1 or y1 == wh - 1
    if leaked:
        # Plain text on the page: the block of ink around the point
        ink = dilate(np.abs(win - bg).max(axis=2) > INK, GAP)
        ys, xs = np.nonzero(ink)
        if len(xs) == 0:
            return None
        i = ((xs - cx) ** 2 + (ys - cy) ** 2).argmin()
        x0, y0, x1, y1 = fill(ink, xs[i], ys[i])
        x0, x1 = x0 + GAP, x1 - GAP  # undo the sideways growth
        y0, y1 = y0 + GAP // 2, y1 - GAP // 2
    x0, x1, y0, y1 = x0 + left, x1 + left, y0 + top, y1 + top
    return [round(x0 / W * 100, 2), round(y0 / H * 100, 2),
            round((x1 - x0 + 1) / W * 100, 2), round((y1 - y0 + 1) / H * 100, 2)]


def main():
    boxes = {}
    for name, x, y in spots():
        img = Image.open(f'images/{name}.webp')
        W, H = img.size
        b = box(img, round(x / 100 * W), round(y / 100 * H))
        if b:
            boxes[f'{name}@{x:g},{y:g}'] = b
        print(f'{name}@{x:g},{y:g}', b)
    OUT.write_text(json.dumps(boxes, indent=1) + '\n')


if __name__ == '__main__':
    main()
