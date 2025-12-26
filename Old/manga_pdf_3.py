from pathlib import Path
from natsort import natsorted
from PIL import Image, ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
import imagehash
import pandas as pd

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input")
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

def detect_page_side(img: Image.Image):
    gray = img.convert("L")
    w, h = gray.size

    left_strip = gray.crop((0, 0, int(w * 0.08), h))
    right_strip = gray.crop((int(w * 0.92), 0, w, h))

    left_mean = ImageStat.Stat(left_strip).mean[0]
    right_mean = ImageStat.Stat(right_strip).mean[0]

    # More white → outer margin
    if left_mean > right_mean:
        return "LEFT"
    return "RIGHT"

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

        side = detect_page_side(img)

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

        print(page_no ,img_path)

        if FORCE_CMYK:
            img = convert_to_cmyk(img)

        phash = str(imagehash.phash(img))
        duplicate_of = hash_seen.get(phash)

        hash_seen.setdefault(phash, img_path.name)

        draw_w, draw_h = fit_image_no_crop(
            img.width, img.height,
            PAGE_WIDTH, PAGE_HEIGHT
        )

        x = (PAGE_WIDTH - draw_w) / 2
        y = (PAGE_HEIGHT - draw_h) / 2
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

        last_side = side
        page_no += 1

    pdf.save()

    df = pd.DataFrame(csv_rows)
    df.to_csv(CSV_DIR / f"{volume.name}_pages.csv", index=False)

print("\nAll volumes processed.")
