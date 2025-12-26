from pathlib import Path
from natsort import natsorted
from PIL import Image, ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
import imagehash
import pandas as pd

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input2")
OUTPUT_DIR = Path("output_pdfs")
CSV_DIR = Path("csv_reports")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

RTL_BINDING = True
AUTO_ROTATE = True
FORCE_CMYK = True

GUTTER_MM = 6.0
SPINE_COMP_MM = 0.15
WHITE_THRESHOLD = 240  # luminance threshold

OUTPUT_DIR.mkdir(exist_ok=True)
CSV_DIR.mkdir(exist_ok=True)
PAGE_WIDTH, PAGE_HEIGHT = A5
# --------------------------------------

def fit_image_safe(
    img_w, img_h,
    page_w, page_h,
    gutter_mm, spine_mm, page_no
):
    """
    Scale image so that AFTER gutter + spine offsets
    it still fully fits inside the page.
    """

    # Total horizontal offset that will be applied later
    total_offset_pt = abs(gutter_mm * mm) + abs(page_no * spine_mm * mm)

    usable_w = page_w - total_offset_pt
    usable_h = page_h

    scale = min(usable_w / img_w, usable_h / img_h)
    return img_w * scale, img_h * scale


def is_landscape(img):
    return img.width > img.height

def convert_to_cmyk(img):
    return img.convert("CMYK") if img.mode != "CMYK" else img

def fit_image_no_crop(img_w, img_h, page_w, page_h):
    scale = min(page_w / img_w, page_h / img_h)
    return img_w * scale, img_h * scale

def gutter_offset(side):
    if RTL_BINDING:
        return -GUTTER_MM * mm if side == "RIGHT" else GUTTER_MM * mm
    return GUTTER_MM * mm if side == "RIGHT" else -GUTTER_MM * mm

def spine_comp(page_no):
    return page_no * SPINE_COMP_MM * mm

import numpy as np
from PIL import Image, ImageFilter

def detect_page_side(
    img: Image.Image,
    last_side: str | None = None,
    ambiguity_ratio: float = 0.05
) -> str:
    """
    Detect LEFT / RIGHT manga page using vertical edge density.

    Fallback logic:
    - If detection is ambiguous, infer from `last_side`
      (LEFT ↔ RIGHT alternation).
    - If last_side is None, default to RIGHT (page 1 rule).

    Returns: "LEFT" or "RIGHT"
    """

    gray = img.convert("L")
    gray = gray.filter(ImageFilter.GaussianBlur(radius=1.0))

    arr = np.array(gray, dtype=np.int16)

    sobel_v = np.array([
        [-1, 0, 1],
        [-2, 0, 2],
        [-1, 0, 1]
    ])

    edge = np.abs(
        np.convolve(arr.flatten(), sobel_v.flatten(), mode="same")
    ).reshape(arr.shape)

    h, w = edge.shape
    band = int(w * 0.06)

    left_energy = edge[:, :band].sum()
    right_energy = edge[:, w - band:].sum()

    max_energy = max(left_energy, right_energy)

    print(left_energy, right_energy, abs(left_energy - right_energy) / max_energy)

    # ---- SAFEGUARD ----
    if max_energy > 0:
        diff_ratio = abs(left_energy - right_energy) / max_energy
        if diff_ratio < ambiguity_ratio:
            # Ambiguous → infer from last page
            if last_side == "LEFT":
                return "RIGHT"
            if last_side == "RIGHT":
                return "LEFT"
            return "RIGHT"  # First page fallback
    else:
        # No signal at all (blank / near blank)
        if last_side == "LEFT":
            return "RIGHT"
        if last_side == "RIGHT":
            return "LEFT"
        return "RIGHT"
    # -------------------

    # Clear signal
    if left_energy > right_energy:
        return "RIGHT"  # gutter on left
    else:
        return "LEFT"



def collect_volume_pages(volume):
    pages = []
    for chapter in natsorted([c for c in volume.iterdir() if c.is_dir()]):
        for img in natsorted(p for p in chapter.iterdir() if p.suffix.lower() in IMAGE_EXTS):
            pages.append((chapter.name, img))
    return pages

# ---------------- MAIN ----------------
for volume in sorted(v for v in MANGA_ROOT.iterdir() if v.is_dir()):
    print(f"\nProcessing {volume.name}")

    pages = collect_volume_pages(volume)
    if not pages:
        continue

    pdf = canvas.Canvas(
        str(OUTPUT_DIR / f"{volume.name}_A5_PRINT.pdf"),
        pagesize=A5
    )

    csv_rows = []
    hash_seen = {}
    page_no = 1
    last_side = None

    for chapter_name, img_path in pages:
        img = Image.open(img_path)

        if AUTO_ROTATE and is_landscape(img):
            img = img.rotate(90, expand=True)

        landscape = is_landscape(img)

        side = detect_page_side(img, last_side)

        # Insert blank if side repeats
        if last_side == side:
            blank = Image.new("CMYK", (int(PAGE_WIDTH), int(PAGE_HEIGHT)), (0, 0, 0, 0))
            pdf.showPage()
            csv_rows.append({
                "volume": volume.name,
                "chapter": chapter_name,
                "image_path": "BLANK",
                "page_no": page_no,
                "detected_side": "BLANK",
                "landscape": False,
                "perceptual_hash": None,
                "duplicate_of": None
            })
            page_no += 1

        if FORCE_CMYK:
            img = convert_to_cmyk(img)

        phash = str(imagehash.phash(img))
        duplicate_of = hash_seen.get(phash)

        hash_seen.setdefault(phash, img_path.name)

        draw_w, draw_h = fit_image_safe(
            img.width, img.height,
            PAGE_WIDTH, PAGE_HEIGHT,
            GUTTER_MM,
            SPINE_COMP_MM,
            page_no
        )

        x = (PAGE_WIDTH - draw_w) / 2
        y = (PAGE_HEIGHT - draw_h) / 2

        # Apply offsets AFTER scaling
        x += gutter_offset(side)
        x += spine_comp(page_no)


        pdf.drawInlineImage(img, x, y, width=draw_w, height=draw_h)
        pdf.showPage()

        csv_rows.append({
            "volume": volume.name,
            "chapter": chapter_name,
            "image_path": str(img_path),
            "page_no": page_no,
            "detected_side": side,
            "landscape": landscape,
            "perceptual_hash": phash,
            "duplicate_of": duplicate_of
        })

        print(page_no, img_path, side)

        last_side = side
        page_no += 1

    pdf.save()

    df = pd.DataFrame(csv_rows)
    df.to_csv(CSV_DIR / f"{volume.name}_pages.csv", index=False)

print("\nAll volumes processed.")
