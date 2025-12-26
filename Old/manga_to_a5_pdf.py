import os
import csv
import math
from PIL import Image
import numpy as np
import imagehash
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import white

# =========================
# CONFIGURATION
# =========================

DPI = 300

A5_W_MM = 148
A5_H_MM = 210

GUTTER_MM = 3.0
MAX_SPINE_MM = 3.0

AMBIGUITY_RATIO = 0.05

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")

# =========================
# UNIT CONVERSION
# =========================

def mm_to_px(mm_val, dpi=DPI):
    return int((mm_val / 25.4) * dpi)

def mm_to_pt(mm_val):
    return mm_val * mm

A5_W_PX = mm_to_px(A5_W_MM)
A5_H_PX = mm_to_px(A5_H_MM)

# =========================
# DISCOVERY
# =========================

def collect_volume_pages(volume_dir):
    pages = []

    volume = os.path.basename(volume_dir)

    for chapter in sorted(os.listdir(volume_dir)):
        ch_path = os.path.join(volume_dir, chapter)
        if not os.path.isdir(ch_path):
            continue

        for fname in sorted(os.listdir(ch_path)):
            if fname.lower().endswith(IMAGE_EXTS):
                pages.append({
                    "volume": volume,
                    "chapter": chapter,
                    "path": os.path.join(ch_path, fname),
                    "is_blank": False
                })

    return pages

# =========================
# BLANK PAGE INSERTION (RTL)
# =========================

def insert_blank_pages_rtl(pages):
    out = []
    last_side = None

    for page in pages:
        if last_side == "LEFT":
            out.append({
                "is_blank": True
            })
            last_side = "RIGHT"

        out.append(page)
        last_side = "LEFT" if last_side == "RIGHT" else "RIGHT"

    return out

# =========================
# SPINE COMPENSATION
# =========================

def compute_spine_compensation(page_index, total_pages, max_spine_mm):
    if total_pages <= 1:
        return 0.0

    center = (total_pages - 1) / 2
    distance = abs(page_index - center) / center
    return max_spine_mm * (1 - distance)

# =========================
# SAFE IMAGE FIT (NO CROP)
# =========================

def fit_image_safe(img_w, img_h, page_w, page_h, gutter_px, spine_px):
    usable_w = page_w - gutter_px - spine_px
    usable_h = page_h

    scale = min(usable_w / img_w, usable_h / img_h)
    return int(img_w * scale), int(img_h * scale)

# =========================
# PAGE SIDE DETECTION
# =========================

def detect_page_side_with_confidence(img, last_side=None, ambiguity_ratio=AMBIGUITY_RATIO):
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.int16)

    h, w = arr.shape
    band = int(w * 0.12)

    left_energy = np.sum(np.abs(np.diff(arr[:, :band], axis=1)))
    right_energy = np.sum(np.abs(np.diff(arr[:, w-band:], axis=1)))

    total = left_energy + right_energy
    diff = abs(left_energy - right_energy)

    confidence = diff / total if total > 0 else 0.0

    if confidence < ambiguity_ratio:
        resolution = "fallback_last_page"
        if last_side == "LEFT":
            return "RIGHT", confidence, resolution
        if last_side == "RIGHT":
            return "LEFT", confidence, resolution
        return "RIGHT", confidence, "fallback_default"

    side = "RIGHT" if left_energy > right_energy else "LEFT"
    return side, confidence, "edge_analysis"

# =========================
# PDF RENDERING
# =========================

def render_volume(volume_dir, output_dir):
    pages = collect_volume_pages(volume_dir)
    pages = insert_blank_pages_rtl(pages)

    total_pages = len(pages)
    volume = os.path.basename(volume_dir)

    pdf_path = os.path.join(output_dir, f"{volume}.pdf")
    csv_path = os.path.join(output_dir, f"{volume}.csv")

    c = canvas.Canvas(
        pdf_path,
        pagesize=(mm_to_pt(A5_W_MM), mm_to_pt(A5_H_MM))
    )

    csv_rows = []
    last_side = None

    for page_index, page in enumerate(pages):

        c.setFillColor(white)
        c.rect(0, 0, mm_to_pt(A5_W_MM), mm_to_pt(A5_H_MM), fill=1)

        if page.get("is_blank"):
            c.showPage()
            last_side = "LEFT" if last_side == "RIGHT" else "RIGHT"
            continue

        img = Image.open(page["path"]).convert("RGB")

        is_landscape = img.width > img.height

        side, confidence, resolution = detect_page_side_with_confidence(
            img, last_side
        )
        last_side = side

        spine_mm = compute_spine_compensation(
            page_index, total_pages, MAX_SPINE_MM
        )

        gutter_px = mm_to_px(GUTTER_MM)
        spine_px = mm_to_px(spine_mm)

        new_w, new_h = fit_image_safe(
            img.width, img.height,
            A5_W_PX, A5_H_PX,
            gutter_px, spine_px
        )

        img = img.resize((new_w, new_h), Image.LANCZOS)

        if side == "RIGHT":
            x_px = gutter_px + spine_px
        else:
            x_px = 0

        y_px = (A5_H_PX - new_h) // 2

        c.drawInlineImage(
            img,
            mm_to_pt(x_px * 25.4 / DPI),
            mm_to_pt(y_px * 25.4 / DPI),
            width=mm_to_pt(new_w * 25.4 / DPI),
            height=mm_to_pt(new_h * 25.4 / DPI)
        )

        phash = str(imagehash.phash(img))

        csv_rows.append({
            "volume": page["volume"],
            "chapter": page["chapter"],
            "page_index": page_index,
            "image_path": page["path"],
            "page_side": side,
            "confidence": round(confidence, 4),
            "side_resolution": resolution,
            "landscape": is_landscape,
            "is_blank": False,
            "spine_mm": round(spine_mm, 3),
            "gutter_mm": GUTTER_MM,
            "phash": phash
        })

        print(page["path"], side)

        c.showPage()

    c.save()

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Rendered {volume}: {pdf_path}")

# =========================
# ENTRY POINT
# =========================

def main(root_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for vol in sorted(os.listdir(root_dir)):
        vol_path = os.path.join(root_dir, vol)
        if os.path.isdir(vol_path):
            render_volume(vol_path, output_dir)

if __name__ == "__main__":
    # Example:
    main("input", "Output")
    pass
