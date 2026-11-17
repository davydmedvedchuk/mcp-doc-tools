"""Scan clean-up for OCR: adaptive black and white + deskew. Same method as Local OCR (src/prep.cpp)."""
import numpy as np
from PIL import Image

MAXPX = 3000


def fit(im: Image.Image, maxpx: int = MAXPX) -> Image.Image:
    k = min(1.0, maxpx / max(im.size))
    return im if k >= 1 else im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)


def binarize(gray: np.ndarray, win: int, ratio: float = 0.85) -> np.ndarray:
    """Bradley adaptive threshold via an integral image. 0 = ink, 255 = paper."""
    a = gray.astype(np.float64)
    h, w = a.shape
    ii = np.zeros((h + 1, w + 1))
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    r = max(2, win // 2)
    y0 = np.clip(np.arange(h) - r, 0, h)[:, None]
    y1 = np.clip(np.arange(h) + r + 1, 0, h)[:, None]
    x0 = np.clip(np.arange(w) - r, 0, w)[None, :]
    x1 = np.clip(np.arange(w) + r + 1, 0, w)[None, :]
    s = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    cnt = (y1 - y0) * (x1 - x0)
    return np.where(a * cnt < s * ratio, 0, 255).astype(np.uint8)


def skew_angle(bw: np.ndarray) -> float:
    """Degrees in -15..15. Rotating clockwise by this levels the text lines (projection profile)."""
    h, w = bw.shape
    step = max(1, max(w, h) // 900)
    ys, xs = np.nonzero(bw[::step, ::step] == 0)
    if len(xs) < 200:
        return 0.0
    x = xs * step - w / 2
    y = ys * step - h / 2
    bins = h // step + w // step + 2

    def score(deg: float) -> float:
        t = np.radians(deg)
        yr = ((x * np.sin(t) + y * np.cos(t)) / step + bins / 2).astype(int)
        yr = yr[(yr >= 0) & (yr < bins)]
        c = np.bincount(yr, minlength=bins).astype(np.float64)
        return float((c * c).sum())

    best = max(np.arange(-15, 15.01, 0.5), key=score)
    return float(max(np.arange(best - 0.5, best + 0.51, 0.1), key=score))


def clean(gray_img: Image.Image) -> tuple[Image.Image, float]:
    """Returns (black and white page, angle that was removed)."""
    gray = np.asarray(gray_img.convert("L"))
    h, w = gray.shape
    win = max(15, w >> 4) | 1
    bw = binarize(gray, win)
    ang = skew_angle(bw)
    if abs(ang) >= 0.2:
        lvl = np.asarray(gray_img.convert("L").rotate(-ang, resample=Image.BICUBIC, fillcolor=255))
        bw = binarize(lvl, win)
    m = max(8, round(min(w, h) * 0.02))
    bw[:m, :] = 255; bw[-m:, :] = 255; bw[:, :m] = 255; bw[:, -m:] = 255
    return Image.fromarray(bw), ang
