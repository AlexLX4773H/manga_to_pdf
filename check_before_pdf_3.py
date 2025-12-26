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

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

PHASH_DUP_THRESHOLD = 5
ASPECT_TOLERANCE = 0.03
COLOR_THRESHOLD = 20.0  # percent

TARGET_RATIOS = {
    "5:7": 5 / 7,
    "7:5": 7 / 5,
}
# ---------------------------------------


def color_percentage(img: Image.Image) -> float:
    if img.mode != "RGB":
        img = img.convert("RGB")

    stat = ImageStat.Stat(img)
    r, g, b = stat.mean

    diff_rg = abs(r - g)
    diff_rb = abs(r - b)
    diff_gb = abs(g - b)

    strength = (diff_rg + diff_rb + diff_gb) / 3
    return min((strength / 20) * 100, 100)


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
    if not dest.exists():
        shutil.copy2(src, dest)


def scan_manga():
    records = []
    hash_db = []  # stores dicts that also reference record index

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DUPLICATE_ROOT.mkdir(parents=True, exist_ok=True)

    image_files = natsorted(
        p for p in MANGA_ROOT.rglob("*") if p.suffix.lower() in SUPPORTED_EXT
    )

    for img_path in tqdm(image_files, desc="Scanning pages"):
        try:
            with Image.open(img_path) as img:
                img.load()

                phash = imagehash.phash(img)
                w, h = img.size
                ratio, ratio_close, ratio_ok = aspect_ratio_info(w, h)
                ratio_text = aspect_ratio_label(w, h)

                color_pct = color_percentage(img)
                is_color = color_pct >= COLOR_THRESHOLD

        except Exception as e:
            records.append({
                "file": str(img_path),
                "error": str(e),
            })
            continue

        is_duplicate = False
        duplicate_of = None
        duplicate_distance = None

        for entry in hash_db:
            dist = phash - entry["phash"]
            if dist <= PHASH_DUP_THRESHOLD:
                is_duplicate = True
                duplicate_of = entry["file"]
                duplicate_distance = dist

                # Mark the ORIGINAL record as duplicate too
                records[entry["record_index"]]["is_duplicate"] = True

                # Copy both pages
                copy_with_structure(Path(entry["file"]), MANGA_ROOT, DUPLICATE_ROOT)
                copy_with_structure(img_path, MANGA_ROOT, DUPLICATE_ROOT)
                break

        parts = img_path.relative_to(MANGA_ROOT).parts
        volume = parts[0] if len(parts) > 0 else "UNKNOWN"
        chapter = parts[1] if len(parts) > 1 else None

        record = {
            "file": str(img_path),
            "volume": volume,
            "chapter": chapter,
            "width": w,
            "height": h,
            "aspect_ratio": round(ratio, 4),
            "aspect_ratio_label": ratio_text,
            "closest_ratio": ratio_close,
            "ratio_within_tolerance": ratio_ok,
            "color_percentage": round(color_pct, 2),
            "is_color_page": is_color,
            "phash": str(phash),
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "duplicate_distance": duplicate_distance,
        }

        records.append(record)

        hash_db.append({
            "file": str(img_path),
            "phash": phash,
            "record_index": len(records) - 1,
        })

    return pd.DataFrame(records)


def write_volume_reports(df: pd.DataFrame):
    for volume, vol_df in df.groupby("volume"):
        vol_df = vol_df.sort_values(["chapter", "file"])

        report_path = REPORT_DIR / f"{volume}_report.csv"
        vol_df.to_csv(report_path, index=False)

        dup_df = vol_df[vol_df["is_duplicate"] == True]
        if not dup_df.empty:
            dup_report = REPORT_DIR / f"{volume}_duplicates.csv"
            dup_df.to_csv(dup_report, index=False)


if __name__ == "__main__":
    df = scan_manga()
    write_volume_reports(df)

    print("Processing complete.")
    print(f"Reports written to: {REPORT_DIR.resolve()}")
    print(f"Duplicate pages copied to: {DUPLICATE_ROOT.resolve()}")
