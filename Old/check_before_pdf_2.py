from pathlib import Path
from PIL import Image, ImageStat
import imagehash
import pandas as pd
from natsort import natsorted
from tqdm import tqdm
import shutil
import math

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input")

REPORT_DIR = Path("reports")
DUPLICATE_ROOT = Path("duplicate_pages")
THUMBNAIL_ROOT = Path("duplicate_thumbnails")

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

PHASH_DUP_THRESHOLD = 5
ASPECT_TOLERANCE = 0.03
COLOR_THRESHOLD = 20.0  # percent

TARGET_RATIOS = {
    "5:7": 5 / 7,
    "7:5": 7 / 5,
}

THUMB_WIDTH = 300
# ---------------------------------------


def is_color_page(img: Image.Image) -> float:
    if img.mode != "RGB":
        img = img.convert("RGB")

    stat = ImageStat.Stat(img)
    r, g, b = stat.mean

    diff_rg = abs(r - g)
    diff_rb = abs(r - b)
    diff_gb = abs(g - b)

    color_strength = (diff_rg + diff_rb + diff_gb) / 3
    return min((color_strength / 20) * 100, 100)


def aspect_ratio_info(w: int, h: int):
    ratio = w / h
    closest = None
    min_diff = float("inf")

    for label, target in TARGET_RATIOS.items():
        diff = abs(ratio - target) / target
        if diff < min_diff:
            min_diff = diff
            closest = label

    return ratio, closest, min_diff <= ASPECT_TOLERANCE


def aspect_ratio_label(w: int, h: int) -> str:
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def copy_with_structure(src: Path, root: Path, dest_root: Path):
    relative = src.relative_to(root)
    dest = dest_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def create_thumbnail(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail((THUMB_WIDTH, 9999))
        img.save(dest, quality=90)


def scan_manga():
    records = []
    hash_db = []

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DUPLICATE_ROOT.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)

    image_files = natsorted(
        p for p in MANGA_ROOT.rglob("*") if p.suffix.lower() in SUPPORTED_EXT
    )

    for img_path in tqdm(image_files, desc="Scanning pages"):
        try:
            with Image.open(img_path) as img:
                img.load()

                phash = imagehash.phash(img)
                w, h = img.size
                ratio, ratio_label_close, ratio_ok = aspect_ratio_info(w, h)
                ratio_text = aspect_ratio_label(w, h)
                color_pct = is_color_page(img)
                is_color = color_pct >= COLOR_THRESHOLD

        except Exception as e:
            records.append({
                "file": str(img_path),
                "error": str(e),
            })
            continue

        duplicate_of = None
        duplicate_distance = None

        for entry in hash_db:
            dist = phash - entry["phash"]
            if dist <= PHASH_DUP_THRESHOLD:
                duplicate_of = entry["file"]
                duplicate_distance = dist

                # Copy both original and duplicate
                orig_path = Path(entry["file"])
                copy_with_structure(
                    orig_path,
                    MANGA_ROOT,
                    DUPLICATE_ROOT / "original"
                )
                copy_with_structure(
                    img_path,
                    MANGA_ROOT,
                    DUPLICATE_ROOT / "duplicate"
                )

                # Thumbnails
                rel = img_path.relative_to(MANGA_ROOT)
                thumb_base = THUMBNAIL_ROOT / rel.parent

                create_thumbnail(
                    orig_path,
                    thumb_base / f"{orig_path.stem}__ORIGINAL.jpg"
                )
                create_thumbnail(
                    img_path,
                    thumb_base / f"{img_path.stem}__DUPLICATE.jpg"
                )

                break

        hash_db.append({
            "file": str(img_path),
            "phash": phash,
        })

        parts = img_path.relative_to(MANGA_ROOT).parts
        volume = parts[0] if len(parts) > 0 else "UNKNOWN"
        chapter = parts[1] if len(parts) > 1 else None

        records.append({
            "file": str(img_path),
            "volume": volume,
            "chapter": chapter,
            "width": w,
            "height": h,
            "aspect_ratio": round(ratio, 4),
            "aspect_ratio_label": ratio_text,
            "closest_ratio": ratio_label_close,
            "ratio_within_tolerance": ratio_ok,
            "color_percentage": round(color_pct, 2),
            "is_color_page": is_color,
            "phash": str(phash),
            "is_duplicate": duplicate_of is not None,
            "duplicate_of": duplicate_of,
            "duplicate_distance": duplicate_distance,
        })

    return pd.DataFrame(records)


def write_volume_reports(df: pd.DataFrame):
    for volume, vol_df in df.groupby("volume"):
        report_path = REPORT_DIR / f"{volume}_report.csv"
        vol_df.sort_values(["chapter", "file"], inplace=True)
        vol_df.to_csv(report_path, index=False)

        dup_df = vol_df[vol_df["is_duplicate"] == True]
        if not dup_df.empty:
            dup_report = REPORT_DIR / f"{volume}_duplicates.csv"
            dup_df.to_csv(dup_report, index=False)


if __name__ == "__main__":
    df = scan_manga()
    write_volume_reports(df)

    print("\nProcessing complete.")
    print(f"Reports: {REPORT_DIR.resolve()}")
    print(f"Duplicate pages: {DUPLICATE_ROOT.resolve()}")
    print(f"Duplicate thumbnails: {THUMBNAIL_ROOT.resolve()}")
