"""Convert images/*.png to WebP (the page references .webp) and delete the PNGs.

Also writes close-ups of the hint (images/crop-*.webp) from the lesson shots,
for the "kinds of mistake" pictures, which would be too small as whole screens."""
import glob
import os

from PIL import Image

# right-hand side of a 1440x900 lesson: the text box and the hint under it
HINT_BOX = (750, 260, 1440, 660)
CROPS = {'lesson-hint': 'crop-hint', 'lesson-hint-missing': 'crop-missing',
         'lesson-hint-extra': 'crop-extra', 'lesson-almost': 'crop-almost'}

for path in glob.glob('images/*.png'):
    image = Image.open(path).convert('RGB')
    name = os.path.basename(path)[:-4]
    if name in CROPS:
        image.crop(HINT_BOX).save(f'images/{CROPS[name]}.webp', 'WEBP', quality=86, method=6)
        print('cropped', name)
    image.save(path[:-4] + '.webp', 'WEBP', quality=82, method=6)
    os.remove(path)
    print('converted', path)
