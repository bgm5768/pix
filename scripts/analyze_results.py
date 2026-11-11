import json, glob, os, numpy as np
from PIL import Image
from collections import deque

ids = [
"4b74b12b0119","3f66a4fea410","527d2a7e2fb7",
"604043791572","fddf963fdc00","3b405ecb34fc",
"5e6b2e3c1855","d1bd2dd01e58","1f6a8dd220a1",
"3695475c30b7","7c0bff96d141","3b1b018ccd9b",
"0a9b1e1e6aa6","411cfd66232f","d1a480013f1c",
]

def components(mask):
    h,w = mask.shape
    seen=np.zeros_like(mask)
    comps=[]
    for y in range(h):
        for x in range(w):
            if mask[y,x] and not seen[y,x]:
                # bfs
                q=deque([(y,x)]); seen[y,x]=True; cnt=0
                while q:
                    yy,xx=q.popleft(); cnt+=1
                    for ny,nx in ((yy-1,xx),(yy+1,xx),(yy,xx-1),(yy,xx+1)):
                        if 0<=ny<h and 0<=nx<w and mask[ny,nx] and not seen[ny,nx]:
                            seen[ny,nx]=True; q.append((ny,nx))
                comps.append(cnt)
    return comps

for jid in ids:
    px = Image.open(f"outputs/pixel_art/{jid}_pixel_{[32,64,128][0] if False else ''}".replace('','')) if False else None
    # find actual size file
    import glob
    pfiles = glob.glob(f"outputs/pixel_art/{jid}_pixel_*.png")
    for pf in pfiles:
        size = int(pf.split('_pixel_')[1].split('.png')[0])
        im = Image.open(pf)
        arr = np.array(im)
        if arr.ndim==3 and arr.shape[2]==4:
            mask = arr[:,:,3]>0
        else:
            mask = np.ones((arr.shape[0],arr.shape[1]),dtype=bool)
        ys,xs = np.where(mask)
        if len(ys):
            y0,y1=ys.min(),ys.max(); x0,x1=xs.min(),xs.max()
            bh=y1-y0+1; bw=x1-x0+1
            cx=(x0+x1)/2; cy=(y0+y1)/2
            occ=mask.mean()
            comps=components(mask)
            ncol = len(np.unique(arr[mask][:,:3],axis=0)) if mask.any() else 0
            print(f"{jid} size={size} mode={im.mode} occ={occ:.3f} bbox={bw}x{bh} center=({cx:.1f},{cy:.1f}) img_center=({size/2:.1f},{size/2:.1f}) components={len(comps)} largest={max(comps) if comps else 0} colors={ncol}")
        else:
            print(jid, size, "EMPTY")
    # cutout
    cim = Image.open(f"outputs/cutouts/{jid}_cutout.png")
    carr = np.array(cim)
    cmask = carr[:,:,3]>127 if carr.ndim==3 and carr.shape[2]==4 else np.ones((carr.shape[0],carr.shape[1]),dtype=bool)
    cys,cxs=np.where(cmask)
    if len(cys):
        print(f"   cutout {cim.size} occ={cmask.mean():.3f} bbox={cxs.max()-cxs.min()+1}x{cys.max()-cys.min()+1} components={len(components(cmask))}")
    # crop
    rim = Image.open(f"outputs/crops/{jid}_crop.png")
    print(f"   crop {rim.size}")
