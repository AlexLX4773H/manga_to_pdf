from pathlib import Path
from natsort import natsorted
from PIL import Image, ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
import imagehash
import pandas as pd
from reportlab.lib.utils import ImageReader
import numpy as np

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input")
OUTPUT_DIR = Path("output_pdfs")
CSV_DIR = Path("csv_reports")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

RTL_BINDING = False
AUTO_ROTATE = True
FORCE_RGB = True

image_edge_start = 0.002

image_edge_crop = 0.04
image_similarity_threshold = 0.012

image_brightest_cutoff = 250
image_darkest_cutoff = 200

image_pixel_threshold = 200

GUTTER_MM = 1.0
SPINE_COMP_MM = 0.1

OUTPUT_DIR.mkdir(exist_ok=True)
CSV_DIR.mkdir(exist_ok=True)
PAGE_WIDTH, PAGE_HEIGHT = A5
# --------------------------------------


def fit_image_safe(img_w, img_h, page_w, page_h, gutter_mm, spine_mm, page_no):
    total_offset_pt = abs(gutter_mm * mm) + abs(page_no * spine_mm * mm)
    usable_w = page_w - total_offset_pt
    usable_h = page_h
    scale = min(usable_w / img_w, usable_h / img_h)
    return img_w * scale, img_h * scale


def is_landscape(img):
    return img.width > img.height


def convert_to_rgb(img: Image.Image):
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def gutter_offset(side):
    if RTL_BINDING:
        return -GUTTER_MM * mm if side == "RIGHT" else GUTTER_MM * mm
    return GUTTER_MM * mm if side == "RIGHT" else -GUTTER_MM * mm


def spine_comp(page_no):
    return page_no * SPINE_COMP_MM * mm


def detect_page_side(img: Image.Image, threshold = image_pixel_threshold):
    gray = img.convert("L")
    w, h = gray.size

    left_strip = gray.crop((int(w * image_edge_start), 0, int(w * image_edge_crop), h))
    right_strip = gray.crop((int(w * (1.0 - image_edge_crop)), 0, int(w * ( 1.0 -  image_edge_start ) ), h))

    left_mean = ImageStat.Stat(left_strip).mean[0]
    right_mean = ImageStat.Stat(right_strip).mean[0]

    diff_ratio = abs(left_mean - right_mean) / max(left_mean, right_mean)

    # left_pixels = np.array(left_strip)
    # right_pixels = np.array(right_strip)

    # # Binarize
    # left_black_ratio = float(np.mean(left_pixels < threshold))
    # right_black_ratio = float(np.mean(right_pixels < threshold))

    # diff_ratio_black = abs(left_black_ratio - right_black_ratio) / max(left_black_ratio, right_black_ratio, 0.1)

    # if left_black_ratio > right_black_ratio:
    #     side2 = "LEFT"
    # else:
    #     side2 = "RIGHT"

    if left_mean > image_brightest_cutoff and right_mean > image_brightest_cutoff:
        side = "UNKNOWN"
    elif left_mean < image_darkest_cutoff and right_mean < image_darkest_cutoff:
        side = "UNKNOWN"
    elif diff_ratio < image_similarity_threshold:
        side = "UNKNOWN"
    # elif diff_ratio_black < image_similarity_threshold:
    #     side = "UNKNOWN"
    else:
        side = "LEFT" if left_mean < right_mean else "RIGHT"

    # if side != "UNKNOWN":
    #     side = side2

    # return side, (left_mean, left_black_ratio), (right_mean, right_black_ratio), (diff_ratio, diff_ratio_black)
    return side, left_mean, right_mean, diff_ratio


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
        str(OUTPUT_DIR / f"{volume.name}_A5_PRINT_RGB.pdf"),
        pagesize=A5
    )

    csv_rows = []
    hash_seen = {}
    page_no = 1
    last_side = None

    for chapter_name, img_path in pages:
        img = Image.open(img_path)

        if FORCE_RGB:
            img = convert_to_rgb(img)

        if AUTO_ROTATE and is_landscape(img):
            img = img.rotate(90, expand=True)

        landscape = is_landscape(img)
        side, left_mean, right_mean, diff_ratio = detect_page_side(img)

        if side == "UNKNOWN" or landscape:
            if last_side == "LEFT":
                side = "RIGHT"
            elif last_side == "RIGHT":
                side = "LEFT"
            else :
                side = "LEFT"

        # Insert blank if side repeats
        if last_side == side:
            pdf.showPage()
            csv_rows.append({
                "volume": volume.name,
                "chapter": chapter_name,
                "image_path": "BLANK",
                "page_no": page_no,
                "detected_side": "BLANK",
                "landscape": False,
                "left_mean": None,
                "right_mean": None,
                "diff_ratio": None,
                "perceptual_hash": None,
                "duplicate_of": None
            })
            page_no += 1

        phash = str(imagehash.phash(img))
        duplicate_of = hash_seen.get(phash)
        hash_seen.setdefault(phash, img_path.name)

        draw_w, draw_h = fit_image_safe(
            img.width, img.height,
            PAGE_WIDTH, PAGE_HEIGHT,
            GUTTER_MM,
            SPINE_COMP_MM,
            1
        )

        x = (PAGE_WIDTH - draw_w) / 2
        y = (PAGE_HEIGHT - draw_h) / 2
        x += gutter_offset(side)
        x += spine_comp(1)

        pdf.drawImage(
            ImageReader(img),
            x,
            y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto"
        )
        pdf.showPage()

        csv_rows.append({
            "volume": volume.name,
            "chapter": chapter_name,
            "image_path": str(img_path),
            "page_no": page_no,
            "detected_side": side,
            "landscape": landscape,
            "left_mean": left_mean,
            "right_mean": right_mean,
            "diff_ratio": diff_ratio,
            "perceptual_hash": phash,
            "duplicate_of": duplicate_of
        })

        print(
            f"{page_no:04d}",
            img_path.name,
            side,
            f"L={left_mean}",
            f"R={right_mean}",
            f"Δ={diff_ratio}"
        )

        last_side = side
        page_no += 1

    pdf.save()
    pd.DataFrame(csv_rows).to_csv(CSV_DIR / f"{volume.name}_pages.csv", index=False)

print("\nAll volumes processed.")
