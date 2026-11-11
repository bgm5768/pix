from PIL import Image
import numpy as np
for jid in ['d55284ffceee','62ffe07de458','a04948097e01']:
    im=Image.open(f'outputs/pixel_art/{jid}_pixel_32.png').convert('RGBA')
    arr=np.array(im)
    print('='*35, jid)
    for y in range(32):
        print(''.join(' ' if arr[y,x,3]<128 else '#' for x in range(32)))