from pathlib import Path
from natsort import natsorted
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input")
OUTPUT_DIR = Path("output_pdfs")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

RTL_BINDING = True
AUTO_ROTATE = True
DETECT_SPREADS = True
FORCE_CMYK = True

GUTTER_MM = 6.0
SPINE_COMP_MM = 0.15

OUTPUT_DIR.mkdir(exist_ok=True)
PAGE_WIDTH, PAGE_HEIGHT = A5
# --------------------------------------

def is_landscape(img):
    return img.width > img.height

def convert_to_cmyk(img):
    return img.convert("CMYK") if img.mode != "CMYK" else img

def fit_image(img_w, img_h, page_w, page_h):
    scale = min(page_w / img_w, page_h / img_h)
    return img_w * scale, img_h * scale

def page_side(page_num):
    # Manga convention: Page 1 = RIGHT
    return "RIGHT" if page_num % 2 == 1 else "LEFT"

def gutter_offset(side):
    if RTL_BINDING:
        return -GUTTER_MM * mm if side == "RIGHT" else GUTTER_MM * mm
    else:
        return GUTTER_MM * mm if side == "RIGHT" else -GUTTER_MM * mm

def spine_compensation(page_num):
    return page_num * SPINE_COMP_MM * mm

def collect_images_from_volume(volume_path: Path):
    """
    Collect images in chapter order, then page order.
    """
    pages = []

    chapters = natsorted(
        [c for c in volume_path.iterdir() if c.is_dir()]
    )

    for chapter in chapters:
        images = natsorted(
            [p for p in chapter.iterdir() if p.suffix.lower() in IMAGE_EXTS]
        )
        pages.extend(images)

    return pages

# ---------------- MAIN ----------------
for volume in sorted(p for p in MANGA_ROOT.iterdir() if p.is_dir()):
    pages = collect_images_from_volume(volume)

    if not pages:
        print(f"Skipping {volume.name} (no images found)")
        continue

    output_pdf = OUTPUT_DIR / f"{volume.name}_A5_CMYK_PRINT.pdf"
    pdf = canvas.Canvas(str(output_pdf), pagesize=A5)

    print(f"\nProcessing {volume.name}")
    page_num = 1

    for img_path in pages:
        img = Image.open(img_path)

        # Auto-rotate landscape scans
        if AUTO_ROTATE and is_landscape(img):
            img = img.rotate(90, expand=True)

        # Convert to CMYK
        if FORCE_CMYK:
            img = convert_to_cmyk(img)

        # -------- Spread Detection --------
        if DETECT_SPREADS and is_landscape(img):
            w, h = img.size
            half = w // 2

            # Manga order: RIGHT page first, then LEFT
            spread_pages = [
                img.crop((half, 0, w, h)),
                img.crop((0, 0, half, h))
            ]

            for sub_img in spread_pages:
                side = page_side(page_num)
                draw_w, draw_h = fit_image(
                    sub_img.width, sub_img.height,
                    PAGE_WIDTH, PAGE_HEIGHT
                )

                x = (PAGE_WIDTH - draw_w) / 2
                y = (PAGE_HEIGHT - draw_h) / 2

                x += gutter_offset(side)
                x += spine_compensation(page_num)

                pdf.drawInlineImage(
                    sub_img,
                    x, y,
                    width=draw_w,
                    height=draw_h
                )

                print(f"Page {page_num:03d} | {side} | SPREAD")
                pdf.showPage()
                page_num += 1

            continue

        # -------- Normal Page --------
        side = page_side(page_num)
        draw_w, draw_h = fit_image(
            img.width, img.height,
            PAGE_WIDTH, PAGE_HEIGHT
        )

        x = (PAGE_WIDTH - draw_w) / 2
        y = (PAGE_HEIGHT - draw_h) / 2

        x += gutter_offset(side)
        x += spine_compensation(page_num)

        pdf.drawInlineImage(
            img,
            x, y,
            width=draw_w,
            height=draw_h
        )

        print(f"Page {page_num:03d} | {side}")
        pdf.showPage()
        page_num += 1

    pdf.save()

print("\nAll volumes completed.")
