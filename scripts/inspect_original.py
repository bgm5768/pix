import numpy as np
from PIL import Image

ids = ["604043791572","0a9b1e1e6aa6","4b74b12b0119"]
for jid in ids:
    im = Image.open(f"outputs/originals/{jid}_original.png").convert("RGB")
    arr = np.array(im)
    print("="*30, jid, im.size)
    # print a 64x32 downsample of luminance
    small = im.resize((64,32))
    sa = np.array(small)
    for y in range(32):
        print("".join(" .:-=+*#%@"[min(9,int((0.299*r+0.587*g+0.114*b)/28))] for r,g,b in sa[y]))
