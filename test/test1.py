from pathlib import Path
from natsort import natsorted
from PIL import Image, ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
import imagehash
import pandas as pd

image_edge_start = 0.002

image_edge_crop = 0.04
image_similarity_threshold = 0.012

image_brightest_cutoff = 250
image_darkest_cutoff = 200

image_pixel_threshold = 200

def detect_page_side(img: Image.Image):
    gray = img.convert("L")
    w, h = gray.size

    left_strip = gray.crop((int(w * 0.01), 0, int(w * 0.04), h))
    right_strip = gray.crop((int(w * 0.96), 0, int(w * 0.99), h))

    left_mean = ImageStat.Stat(left_strip).mean[0]
    right_mean = ImageStat.Stat(right_strip).mean[0]

    print(left_mean, right_mean)

    # left_strip.show(title="Left strip")
    # right_strip.show(title="Right strip")  


    # More white → inner margin
    if left_mean < right_mean:
        return "LEFT"
    return "RIGHT"

from PIL import Image
import numpy as np

def detect_page_side_binary(img: Image.Image, threshold=200):
    gray = img.convert("L")
    w, h = gray.size

    strip_w = int(w * 0.02)
    y1 = int(h * 0.05)
    y2 = int(h * 0.95)

    # left_strip = gray.crop((0, y1, strip_w, y2))
    # right_strip = gray.crop((w - strip_w, y1, w, y2))

    left_strip = gray.crop((int(w * 0.01), 0, int(w * 0.04), h))
    right_strip = gray.crop((int(w * 0.96), 0, int(w * 0.99), h))

    left_pixels = np.array(left_strip)
    right_pixels = np.array(right_strip)

    # Binarize
    left_black_ratio = np.mean(left_pixels < threshold)
    right_black_ratio = np.mean(right_pixels < threshold)

    
    print(abs(left_black_ratio - right_black_ratio) / max(left_black_ratio, right_black_ratio))

    print("LEFT black %:", left_black_ratio)
    print("RIGHT black %:", right_black_ratio)

    # Outer margin = fewer black pixels
    if right_black_ratio > left_black_ratio:
        return "RIGHT"
    return "LEFT"

def detect_page_side23(img: Image.Image, threshold = image_pixel_threshold):
    gray = img.convert("L")
    w, h = gray.size

    left_strip = gray.crop((int(w * image_edge_start), 0, int(w * image_edge_crop), h))
    right_strip = gray.crop((int(w * (1.0 - image_edge_crop)), 0, int(w * ( 1.0 - image_edge_start)), h))

    left_mean = ImageStat.Stat(left_strip).mean[0]
    right_mean = ImageStat.Stat(right_strip).mean[0]

    print("val right:",int(w * ( (1.0 - image_edge_crop) + image_edge_start)), int(w * (1.0 - image_edge_crop)), ( 1.0 - image_edge_start) )
    print("val right:",int(w * image_edge_crop), int(w * image_edge_start))

    diff_ratio = abs(left_mean - right_mean) / max(left_mean, right_mean)

    left_strip.show(title="Left strip")
    right_strip.show(title="Right strip")  

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


# img_path = """G:\\LX\\Git Repos\\Manga_PDF\\input\\Since I’ve Entered the World of Romantic Comedy Manga, I’ll Do My Best to Make the Losing Heroine Happy\\Chapter 1_30eb3a\\012.jpg"""

img_path = """G:\\LX\\Git Repos\\Manga_PDF\\input\\Since I’ve Entered the World of Romantic Comedy Manga, I’ll Do My Best to Make the Losing Heroine Happy\\Chapter 2_89ad85\\018.jpg"""


img = Image.open(img_path)

side = detect_page_side(img)

print(side)

side = detect_page_side_binary(img)

print(side)

side = detect_page_side23(img)

print(side)