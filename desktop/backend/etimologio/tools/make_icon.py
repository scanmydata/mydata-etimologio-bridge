# -*- coding: utf-8 -*-
"""
Build the e-Timologio Pro app icon from the ScanmyData logo.

Takes the ScanmyData hand+phone+shield mark and stamps a small invoice/receipt
badge (with a € symbol) in the lower-right corner, so the icon clearly reads as
"ScanmyData, for invoicing" and stays distinct from the plain ScanmyData icon.

Outputs a full favicon set into assets/icons/.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = r"C:\Users\tony-pc\Documents\scanmydata\ScanmyData_private\icons\web-app-manifest-512x512.png"
OUT = os.path.join(ROOT, "assets", "icons")
os.makedirs(OUT, exist_ok=True)

# Brand palette (sampled from the ScanmyData logo)
NAVY = (20, 58, 99, 255)       # deep outline blue
BLUE = (56, 160, 224, 255)     # light accent blue
WHITE = (255, 255, 255, 255)
GREEN = (34, 160, 90, 255)     # money/confirm accent for the € badge

# Work at high resolution, then downsample for crisp edges.
S = 1024
base = Image.open(SRC).convert("RGBA").resize((S, S), Image.LANCZOS)

# The logo mark sits a touch high on the canvas; nudge it up-left a bit to free
# the lower-right quadrant for the invoice badge without cropping the hand.
canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
shift = int(S * 0.06)
canvas.alpha_composite(base.resize((int(S * 0.92), int(S * 0.92)), Image.LANCZOS),
                       (-shift, -shift))

d = ImageDraw.Draw(canvas)


def rounded(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


# ---- Invoice / receipt badge (lower-right) --------------------------------
# A white document with a folded corner, three text lines and a € coin.
bw, bh = int(S * 0.46), int(S * 0.54)
bx = S - bw - int(S * 0.02)
by = S - bh - int(S * 0.02)
r = int(S * 0.05)
fold = int(bw * 0.30)

# soft shadow
sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle(
    [bx + 10, by + 14, bx + bw + 10, by + bh + 14], radius=r, fill=(10, 25, 45, 90))
sh = sh.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(12))
canvas.alpha_composite(sh)

stroke = max(6, int(S * 0.012))

# document body (rounded rect) with a cut/folded top-right corner
rounded(d, [bx, by, bx + bw, by + bh], r, fill=WHITE, outline=NAVY, width=stroke)
# folded corner triangle
d.polygon([(bx + bw - fold, by), (bx + bw, by + fold), (bx + bw - fold, by + fold)],
          fill=(222, 235, 247, 255))
d.line([(bx + bw - fold, by), (bx + bw - fold, by + fold), (bx + bw, by + fold)],
       fill=NAVY, width=stroke)
# repaint the top-right outline hidden by the fold
d.line([(bx + bw - fold, by), (bx + bw, by + fold)], fill=NAVY, width=stroke)

# text lines
lx0 = bx + int(bw * 0.14)
lx1 = bx + int(bw * 0.86)
lw = max(5, int(S * 0.010))
ys = by + int(bh * 0.30)
gap = int(bh * 0.12)
for i in range(3):
    x1 = lx1 if i < 2 else bx + int(bw * 0.60)
    d.line([(lx0, ys + i * gap), (x1, ys + i * gap)], fill=BLUE, width=lw)

# € coin at the bottom of the document
cr = int(bw * 0.20)
ccx = bx + bw - int(bw * 0.30)
ccy = by + bh - int(bh * 0.24)
d.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr], fill=GREEN, outline=WHITE,
          width=max(4, int(S * 0.008)))
# draw a € glyph
euro = None
for name in ("segoeui.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
    try:
        euro = ImageFont.truetype(name, int(cr * 1.7))
        break
    except Exception:
        continue
if euro:
    tb = d.textbbox((0, 0), "€", font=euro)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    d.text((ccx - tw / 2 - tb[0], ccy - th / 2 - tb[1]), "€", font=euro, fill=WHITE)
else:
    # fallback: two bars + C-arc
    d.arc([ccx - cr * 0.6, ccy - cr * 0.7, ccx + cr * 0.6, ccy + cr * 0.7], 40, 320,
          fill=WHITE, width=max(5, int(cr * 0.18)))
    d.line([(ccx - cr * 0.5, ccy - cr * 0.15), (ccx + cr * 0.2, ccy - cr * 0.15)],
           fill=WHITE, width=max(5, int(cr * 0.16)))
    d.line([(ccx - cr * 0.5, ccy + cr * 0.15), (ccx + cr * 0.2, ccy + cr * 0.15)],
           fill=WHITE, width=max(5, int(cr * 0.16)))

# ---- Export ---------------------------------------------------------------
master = canvas.resize((512, 512), Image.LANCZOS)
master.save(os.path.join(OUT, "app-icon-512.png"))
master.resize((192, 192), Image.LANCZOS).save(os.path.join(OUT, "app-icon-192.png"))
master.resize((180, 180), Image.LANCZOS).save(os.path.join(OUT, "apple-touch-icon.png"))
master.resize((96, 96), Image.LANCZOS).save(os.path.join(OUT, "favicon-96.png"))
master.resize((32, 32), Image.LANCZOS).save(os.path.join(OUT, "favicon-32.png"))
# multi-size .ico
master.save(os.path.join(OUT, "favicon.ico"),
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print("wrote icons to", OUT)
