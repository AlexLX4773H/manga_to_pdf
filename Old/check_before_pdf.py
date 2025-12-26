from pathlib import Path
from PIL import Image, ImageStat
import imagehash
import pandas as pd
from natsort import natsorted
from tqdm import tqdm
import shutil

# ---------------- CONFIG ----------------
MANGA_ROOT = Path("input2")
DUPLICATE_OUTPUT = Path("duplicate_pages")
REPORT_DIR = Path("reports")

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
PHASH_DUP_THRESHOLD = 5
ASPECT_TOLERANCE = 0.03  # ±3%

TARGET_RATIOS = {
    "5:7": 5 / 7,
    "7:5": 7 / 5,
}

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


def copy_with_structure(src: Path, root: Path, dest_root: Path):
    relative = src.relative_to(root)
    dest = dest_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def scan_manga():
    records = []
    hash_db = []

    DUPLICATE_OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    image_files = natsorted(
        p for p in MANGA_ROOT.rglob("*") if p.suffix.lower() in SUPPORTED_EXT
    )

    for img_path in tqdm(image_files, desc="Scanning pages"):
        try:
            with Image.open(img_path) as img:
                img.load()

                phash = imagehash.phash(img)
                w, h = img.size
                ratio, ratio_label, ratio_ok = aspect_ratio_info(w, h)
                color_pct = is_color_page(img)

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
                copy_with_structure(img_path, MANGA_ROOT, DUPLICATE_OUTPUT)
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
            "closest_ratio": ratio_label,
            "ratio_within_tolerance": ratio_ok,
            "color_percentage": round(color_pct, 2),
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


if __name__ == "__main__":
    df = scan_manga()
    write_volume_reports(df)

    print(f"\nVolume-wise reports written to: {REPORT_DIR.resolve()}")
    print(f"Duplicate pages copied to: {DUPLICATE_OUTPUT.resolve()}")
