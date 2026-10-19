"""Convert images/*.png to WebP (the page references .webp) and delete the PNGs."""
import glob
import os

from PIL import Image

for path in glob.glob('images/*.png'):
    Image.open(path).convert('RGB').save(path[:-4] + '.webp', 'WEBP', quality=82, method=6)
    os.remove(path)
    print('converted', path)
