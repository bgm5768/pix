import glob, numpy as np
from PIL import Image

ids = ["4b74b12b0119","604043791572","5e6b2e3c1855","3695475c30b7","0a9b1e1e6aa6"]
for jid in ids:
    pf = f"outputs/pixel_art/{jid}_pixel_32.png"
    im = Image.open(pf).convert("RGBA")
    arr = np.array(im)
    print("="*40)
    print(jid)
    for y in range(32):
        row=""
        for x in range(32):
            a=arr[y,x,3]
            if a<128:
                row+=" "
            else:
                r,g,b=arr[y,x,:3]
                # choose char by brightness
                lum=0.299*r+0.587*g+0.114*b
                chars=" .:-=+*#%@"
                idx=int(lum/256*len(chars))
                idx=min(len(chars)-1,idx)
                row+=chars[idx]
        print(row)
