"""Independent integer reference for exact x2 cubic a=-3/4 and half-pixel centers."""
import numpy as np

WEIGHTS = ((-9,67,225,-27),(-27,225,67,-9)) # even t=.75; odd t=.25 /256

def round_even_clip(n):
    q,r=np.divmod(n,65536)
    q += (r>32768) | ((r==32768)&((q&1)==1))
    return np.clip(q,0,255).astype(np.uint8)

def scalar_pixel(a,y,x):
    h,w=a.shape
    sy,sx=(y-1)//2,(x-1)//2
    n=0
    for iy,wy in enumerate(WEIGHTS[y%2]):
        for ix,wx in enumerate(WEIGHTS[x%2]):
            n+=int(a[min(h-1,max(0,sy+iy-1)),min(w-1,max(0,sx+ix-1))])*wy*wx
    q,r=divmod(n,65536)
    q+=r>32768 or (r==32768 and q%2==1)
    return min(255,max(0,q))

def integer_reference(a):
    # Separable but never round or clip the intermediate signed result.
    h,w=a.shape
    sx=(np.arange(w*2)-1)//2
    sy=(np.arange(h*2)-1)//2
    horizontal=np.zeros((h,w*2),np.int64)
    weights=np.array(WEIGHTS,np.int64)
    for k in range(4):
        horizontal += a[:,np.clip(sx+k-1,0,w-1)].astype(np.int64)*weights[np.arange(w*2)%2,k]
    n=np.zeros((h*2,w*2),np.int64)
    for k in range(4):
        n+=horizontal[np.clip(sy+k-1,0,h-1),:]*weights[np.arange(h*2)%2,k,None]
    return round_even_clip(n)
