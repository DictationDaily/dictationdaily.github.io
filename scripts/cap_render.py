"""Turn a recording's frames into a Cap-style video: a big pointer, a ring on
each click, captions drawn on top, and a gentle zoom towards whatever is being
clicked or typed into, easing back out when nothing happens.

record.py logs what it does while Chrome's screencast saves frames:
    {'k': 'pos',   't': …, 'x': …, 'y': …}            pointer placed
    {'k': 'move',  't': …, 'x': …, 'y': …, 'dur': …}  pointer glides there
    {'k': 'click', 't': …, 'x': …, 'y': …}            click / tap
    {'k': 'focus', 't': …, 't1': …, 'x': …, 'y': …}   typing into something there
    {'k': 'cap',   't': …, 'html': … | None, 'small': bool}
Times are wall-clock seconds (the screencast's own clock); x/y are CSS pixels.
"""
import html as htmllib
import math
import os
import re
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FPS = 25
ZOOM = 1.35           # "not too much"
ZOOM_PHONE = 1.2      # a phone screen is small already
ZOOM_TAU = 0.5        # seconds for the zoom to settle
PAN_TAU = 0.5         # seconds for the zoom's centre to glide
# Zoom out only for a reason: once in, stay in while the next action is close
# by (glide there instead) and comes within STAY_GAP seconds
STAY_GAP = 5.0
BRIEF = 1.5           # seconds: a shorter zoom-out is skipped
NEAR = 0.6            # "close by": within this share of the zoomed view's size
CLICK_BEFORE, CLICK_AFTER = 0.75, 1.6   # zoomed in around a click
TYPE_BEFORE, TYPE_AFTER = 0.35, 1.1     # and around typing
BRAND = (213, 39, 40)

_FONT = os.path.expanduser('~/.cache/dd-guide/Nunito.ttf')
_FALLBACK = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
SYMBOLS = set('✓✕◀▶⚙→←')  # drawn with DejaVu; other emoji are left out


def _font(size):
    try:
        f = ImageFont.truetype(_FONT, size)
        f.set_variation_by_name('ExtraBold')
        return f
    except Exception:
        return ImageFont.truetype(_FALLBACK, size)


def _ease(p):
    """cubic-bezier(.4,0,.2,1)-like ease in-out."""
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


def _pointer(t, events):
    """Pointer position (CSS px) at time t, or None before it is placed."""
    pos = None
    for e in events:
        if e['t'] > t:
            break
        if e['k'] == 'pos' or e['k'] == 'click':
            pos = (e['x'], e['y'])
        elif e['k'] == 'move':
            start = pos or (e['x'], e['y'])
            p = _ease((t - e['t']) / e['dur'])
            pos = (start[0] + (e['x'] - start[0]) * p, start[1] + (e['y'] - start[1]) * p)
            if p < 1:
                # a later event can't apply before this glide is done
                return pos
    return pos


def _windows(events):
    """When to be zoomed in, and on what (CSS px)."""
    out = []
    for e in events:
        if e['k'] == 'click':
            out.append((e['t'] - CLICK_BEFORE, e['t'] + CLICK_AFTER, e['x'], e['y']))
        elif e['k'] == 'focus':
            out.append((e['t'] - TYPE_BEFORE, e['t1'] + TYPE_AFTER, e['x'], e['y']))
    return out


def _plan(windows, w_css, h_css, zoom):
    """Zoomed stretches: [start, end, [(time, x, y), …]]. Actions close in time
    and place share one stretch, so the view stays in and glides between them."""
    plan = []
    for a, b, x, y in sorted(windows):
        if plan:
            seg = plan[-1]
            _, lx, ly = seg[2][-1]
            near = abs(x - lx) <= w_css / zoom * NEAR and abs(y - ly) <= h_css / zoom * NEAR
            if near and a - seg[1] <= STAY_GAP:
                seg[1] = max(seg[1], b)
                seg[2].append((a, x, y))
                continue
        plan.append([a, b, [(a, x, y)]])
    # a zoom out that would last under BRIEF seconds isn't worth it: glide instead
    for prev, nxt in zip(plan, plan[1:]):
        if nxt[0] - prev[1] < BRIEF:
            prev[1] = nxt[0]
    return plan


def _caption_at(t, events):
    cap, since = None, None
    for e in events:
        if e['k'] != 'cap' or e['t'] > t:
            continue
        cap, since = (e['html'], e.get('small')), e['t']
    if not cap or not cap[0]:
        return None, 0
    return cap, t - since


def _arrow(draw, x, y, s, pressed):
    k = s / 20 * (0.88 if pressed else 1)
    pts = [(0, 0), (0, 17.5), (4.2, 13.6), (7.2, 20.2), (10, 19), (7.1, 12.6), (12.6, 12.6)]
    poly = [(x + px * k, y + py * k) for px, py in pts]
    draw.polygon(poly, fill=(255, 255, 255, 255), outline=(17, 17, 17, 255), width=max(2, round(s / 14)))


def _caption(img, cap, age, out_w, out_h, phone):
    text, small = cap
    m = re.match(r'\s*<b>(\d+)</b>', text)
    num = m.group(1) if m else None
    if m:
        text = text[m.end():]
    text = htmllib.unescape(re.sub(r'<[^>]+>', '', text)).strip()
    text = ''.join(ch for ch in text if ord(ch) < 0x2190 or ch in SYMBOLS).strip()
    if not text:
        return
    size = round(out_w * (0.046 if phone else 0.02))
    font, sym = _font(size), ImageFont.truetype(_FALLBACK, round(size * 0.92))
    pad_x, pad_y, gap = round(size * 0.95), round(size * 0.55), round(size * 0.4)
    max_w = out_w * (0.86 if phone else 0.8) - 2 * pad_x

    def width(s):
        return sum((sym if ch in SYMBOLS else font).getlength(ch) for ch in s)

    words, lines, line = text.split(), [], ''
    lead = (width(num) + gap) if num else 0
    for w in words:
        trial = (line + ' ' + w).strip()
        if line and width(trial) + (lead if not lines else 0) > max_w:
            lines.append(line)
            line = w
        else:
            line = trial
    lines.append(line)
    line_h = round(size * 1.35)
    box_w = max(width(l) + (lead if i == 0 else 0) for i, l in enumerate(lines)) + 2 * pad_x
    box_h = line_h * len(lines) + 2 * pad_y
    fade = min(1.0, age / 0.25)
    rise = round((1 - _ease(fade)) * size * 0.6)
    x0 = (out_w - box_w) / 2
    y0 = out_h - box_h - round(out_h * (0.16 if phone else 0.1)) + rise
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    shadow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 6, x0 + box_w, y0 + box_h + 6), radius=min(box_h / 2, size * 1.2),
                                             fill=(0, 0, 0, round(90 * fade)))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d.rounded_rectangle((x0, y0, x0 + box_w, y0 + box_h), radius=min(box_h / 2, size * 1.2),
                        fill=(33, 33, 33, round(240 * fade)))
    for i, l in enumerate(lines):
        x, y = x0 + pad_x, y0 + pad_y + i * line_h
        if i == 0 and num:
            d.text((x, y), num, font=font, fill=(255, 107, 107, round(255 * fade)))
            x += lead
        for ch in l:
            f = sym if ch in SYMBOLS else font
            d.text((x, y + (size * 0.06 if f is sym else 0)), ch, font=f, fill=(255, 255, 255, round(255 * fade)))
            x += f.getlength(ch)
    img.alpha_composite(layer)


def render(frames, events, out_mp4, out_w, scale, touch=False, poster_at=None, poster_path=None):
    """frames: [(jpg path, wall time)]; scale: frame px per CSS px."""
    events = sorted(events, key=lambda e: e['t'])
    t0 = frames[0][1]
    end = frames[-1][1] + 0.6
    first = Image.open(frames[0][0])
    W, H = first.size
    out_h = round(H * out_w / W / 2) * 2
    phone = touch
    zoom_in = ZOOM_PHONE if touch else ZOOM
    plan = _plan(_windows(events), W / scale, H / scale, zoom_in)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{out_w}x{out_h}',
           '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', '26', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', '-an', out_mp4]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    z, cx, cy = 1.0, W / 2, H / 2
    fi, cache = 0, (None, None)
    dt = 1 / FPS
    n = int((end - t0) * FPS)
    poster_frame = None
    for i in range(n):
        t = t0 + i * dt
        while fi + 1 < len(frames) and frames[fi + 1][1] <= t:
            fi += 1
        if cache[0] != fi:
            cache = (fi, Image.open(frames[fi][0]).convert('RGB'))
        src = cache[1]
        # zoom target: the stretch covering t, centred on its latest action
        tz, tx, ty = 1.0, W / 2, H / 2
        for a, b, points in plan:
            if a <= t <= b:
                x, y = points[0][1:]
                for pt, px, py in points:
                    if pt <= t:
                        x, y = px, py
                # a phone screen is narrow: stay centred across, follow up and down
                tz, tx, ty = zoom_in, (W / 2 if touch else x * scale), y * scale
        z += (tz - z) * (1 - math.exp(-dt / ZOOM_TAU))
        k = 1 - math.exp(-dt / PAN_TAU)
        cx += (tx - cx) * k
        cy += (ty - cy) * k
        w, h = W / z, H / z
        left = min(max(cx - w / 2, 0), W - w)
        top = min(max(cy - h / 2, 0), H - h)
        img = src.resize((out_w, out_h), Image.BICUBIC, box=(left, top, left + w, top + h)).convert('RGBA')
        sx, sy = out_w / w, out_h / h
        d = ImageDraw.Draw(img)
        # click rings
        for e in events:
            if e['k'] == 'click' and 0 <= t - e['t'] < 0.55:
                p = (t - e['t']) / 0.55
                r = (12 + 30 * _ease(p)) * out_w / 1280 * (1.6 if phone else 1)
                x, y = (e['x'] * scale - left) * sx, (e['y'] * scale - top) * sy
                ring = Image.new('RGBA', img.size, (0, 0, 0, 0))
                ImageDraw.Draw(ring).ellipse((x - r, y - r, x + r, y + r), outline=BRAND + (round(230 * (1 - p)),),
                                             width=max(3, round(4 * out_w / 1280)))
                img.alpha_composite(ring)
        pos = _pointer(t, events)
        if pos:
            x, y = (pos[0] * scale - left) * sx, (pos[1] * scale - top) * sy
            pressed = any(e['k'] == 'click' and 0 <= t - e['t'] < 0.15 for e in events)
            if touch:
                r = out_w * 0.05 * (0.85 if pressed else 1)
                dot = Image.new('RGBA', img.size, (0, 0, 0, 0))
                ImageDraw.Draw(dot).ellipse((x - r, y - r, x + r, y + r), fill=BRAND + (95,), outline=BRAND + (255,),
                                            width=max(2, round(r / 7)))
                img.alpha_composite(dot)
            else:
                size = 44 * out_w / 1280
                sh = Image.new('RGBA', img.size, (0, 0, 0, 0))
                _arrow(ImageDraw.Draw(sh), x + 2, y + 3, size, pressed)
                sh = sh.filter(ImageFilter.GaussianBlur(2.5))
                sh.putalpha(sh.getchannel('A').point(lambda a: a * 0.45))
                img.alpha_composite(sh)
                _arrow(ImageDraw.Draw(img), x, y, size, pressed)
        cap, age = _caption_at(t, events)
        if cap:
            _caption(img, cap, age, out_w, out_h, phone)
        rgb = img.convert('RGB')
        if poster_at is not None and poster_frame is None and t - t0 >= poster_at:
            poster_frame = rgb.copy()
        enc.stdin.write(rgb.tobytes())
    enc.stdin.close()
    enc.wait()
    if poster_path:
        (poster_frame or rgb).save(poster_path, quality=86)
