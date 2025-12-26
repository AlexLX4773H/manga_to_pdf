from pathlib import Path
from natsort import natsorted
from PIL import Image, ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import imagehash
import pandas as pd
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

PAGE_NUMBER_FONT = "Helvetica"
PAGE_NUMBER_SIZE = 8
PAGE_NUMBER_MARGIN_MM = 4  # distance from outer edge
PAGE_NUMBER_Y_MM = 4       # distance from bottom

# --------------------------------------

def draw_page_number(pdf, page_no, side):
    """
    Draw page number on outer edge:
    LEFT page  -> right side
    RIGHT page -> left side
    """
    pdf.setFont(PAGE_NUMBER_FONT, PAGE_NUMBER_SIZE)

    y = PAGE_NUMBER_Y_MM * mm

    if side == "LEFT":
        # outer edge = right
        x = PAGE_WIDTH - (PAGE_NUMBER_MARGIN_MM * mm)
        pdf.drawRightString(x, y, str(page_no))
        return "RIGHT"

    else:
        # outer edge = left
        x = PAGE_NUMBER_MARGIN_MM * mm
        pdf.drawString(x, y, str(page_no))
        return "LEFT"


def fit_image_safe(img_w, img_h, page_w, page_h, gutter_mm, spine_mm, page_no):
    total_offset_pt = abs(gutter_mm * mm) + abs(page_no * spine_mm * mm)
    usable_w = page_w - total_offset_pt
    usable_h = page_h
    scale = min(usable_w / img_w, usable_h / img_h)
    return img_w * scale, img_h * scale


def is_landscape(img):
    return img.width > img.height


def convert_to_rgb(img):
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


def detect_page_side(img, threshold=image_pixel_threshold):
    gray = img.convert("L")
    w, h = gray.size

    left_strip = gray.crop((int(w * image_edge_start), 0, int(w * image_edge_crop), h))
    right_strip = gray.crop((int(w * (1.0 - image_edge_crop)), 0,
                             int(w * (1.0 - image_edge_start)), h))

    left_mean = ImageStat.Stat(left_strip).mean[0]
    right_mean = ImageStat.Stat(right_strip).mean[0]

    diff_ratio = abs(left_mean - right_mean) / max(left_mean, right_mean)

    if left_mean > image_brightest_cutoff and right_mean > image_brightest_cutoff:
        side = "UNKNOWN"
    elif left_mean < image_darkest_cutoff and right_mean < image_darkest_cutoff:
        side = "UNKNOWN"
    elif diff_ratio < image_similarity_threshold:
        side = "UNKNOWN"
    else:
        side = "LEFT" if left_mean < right_mean else "RIGHT"

    return side, left_mean, right_mean, diff_ratio


def collect_volume_pages(volume):
    pages = []
    for chapter in natsorted(c for c in volume.iterdir() if c.is_dir()):
        for img in natsorted(p for p in chapter.iterdir() if p.suffix.lower() in IMAGE_EXTS):
            pages.append((chapter.name, img))
    return pages


def remove_sandwiched_blanks(page_plan):
    """
    Remove BLANK pages where both neighbors are BLANK.
    """
    cleaned = []
    removed_indices = set()

    for i in range(1, len(page_plan) - 1):
        if (
            page_plan[i]["type"] == "IMAGE"
            and page_plan[i - 1]["type"] == "BLANK"
            and page_plan[i + 1]["type"] == "BLANK"
        ):
            removed_indices.update({i - 1, i + 1})

    for idx, page in enumerate(page_plan):
        if idx in removed_indices:
            page["removed_blank"] = True
            page["blank_reason"] = "sandwiched"
        else:
            cleaned.append(page)

    return cleaned


# ---------------- MAIN ----------------
for volume in sorted(v for v in MANGA_ROOT.iterdir() if v.is_dir()):
    print(f"\nProcessing {volume.name}")

    pages = collect_volume_pages(volume)
    if not pages:
        continue

    page_plan = []
    hash_seen = {}
    last_side = None

    # -------- PASS 1: BUILD PAGE PLAN --------
    for chapter_name, img_path in pages:
        img = Image.open(img_path)

        if FORCE_RGB:
            img = convert_to_rgb(img)

        if AUTO_ROTATE and is_landscape(img):
            img = img.rotate(90, expand=True)

        landscape = is_landscape(img)
        side, left_mean, right_mean, diff_ratio = detect_page_side(img)

        if side == "UNKNOWN" or landscape:
            side = "RIGHT" if last_side == "LEFT" else "LEFT"

        if last_side == side:
            page_plan.append({
                "type": "BLANK",
                "volume": volume.name,
                "chapter": chapter_name,
            })

        phash = str(imagehash.phash(img))
        duplicate_of = hash_seen.get(phash)
        hash_seen.setdefault(phash, img_path.name)

        page_plan.append({
            "type": "IMAGE",
            "volume": volume.name,
            "chapter": chapter_name,
            "img": img,
            "img_path": str(img_path),
            "side": side,
            "landscape": landscape,
            "left_mean": left_mean,
            "right_mean": right_mean,
            "diff_ratio": diff_ratio,
            "phash": phash,
            "duplicate_of": duplicate_of,
        })

        last_side = side

    # -------- PASS 2: CLEAN BLANKS --------
    page_plan = remove_sandwiched_blanks(page_plan)

    # -------- PASS 3: RENDER PDF + CSV --------
    pdf = canvas.Canvas(
        str(OUTPUT_DIR / f"{volume.name}_A5_PRINT_RGB.pdf"),
        pagesize=A5
    )

    csv_rows = []
    page_no = 1

    for page in page_plan:
        if page["type"] == "BLANK":
            pdf.showPage()
            csv_rows.append({
                "volume": volume.name,
                "chapter": page["chapter"],
                "image_path": "BLANK",
                "page_no": page_no,
                "detected_side": "BLANK",
                "removed_blank": False,
                "blank_reason": None,
            })
            page_no += 1
            continue

        img = page["img"]
        side = page["side"]

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
            x, y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto"
        )

        # ---- PAGE NUMBER ----
        page_number_position = draw_page_number(pdf, page_no, side)

        pdf.showPage()

        csv_rows.append({
            "volume": volume.name,
            "chapter": page["chapter"],
            "image_path": page["img_path"],
            "page_no": page_no,
            "detected_side": side,
            "page_number_position": page_number_position,
            "landscape": page["landscape"],
            "left_mean": page["left_mean"],
            "right_mean": page["right_mean"],
            "diff_ratio": page["diff_ratio"],
            "perceptual_hash": page["phash"],
            "duplicate_of": page["duplicate_of"],
            "removed_blank": False,
            "blank_reason": None,
        })

        print(
            f"{page_no:03d}",
            page["img_path"],
            side,
            f"L={page["left_mean"]}",
            f"R={page["right_mean"]}",
            f"Δ={page["diff_ratio"]}"
        )

        page_no += 1

    pdf.save()
    pd.DataFrame(csv_rows).to_csv(
        CSV_DIR / f"{volume.name}_pages.csv",
        index=False
    )

print("\nAll volumes processed.")
