"""Read Line 6's public Helix model list ("Based on*" column) into line6_based_on.csv.

usage: read_based_on.py PAGE.html [-o line6_based_on.csv]
PAGE.html is the model list page saved from Line 6's website in your browser (Helix models page, all sections).
This script reads a file you saved; it does not download anything. Output columns: section,line6_name,based_on,subcat
Each section is an <h3> title followed by a table whose rows are: [picture + model name] [subcategory] [based on] [first appeared]."""
import argparse
import csv
import html
import re
import sys


def text(fragment):
    t = re.sub(r"<sup>.*?</sup>", "", fragment, flags=re.S)         # the (R) / TM marks
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def parse(page):
    """-> [(section, model name, based on, subcategory)]"""
    rows = []
    parts = re.split(r"<h3>(.*?)</h3>", page, flags=re.S)         # [pre, title, body, title, body, ...]
    for title, body in zip(parts[1::2], parts[2::2]):
        section = text(title)
        for tr in re.split(r"<tr>\s*<td>\s*<table>", body)[1:]:       # one model row: starts with the nested name table
            cells = re.findall(r"<td>\s*<p[^>]*>(.*?)</p>\s*</td>", tr, flags=re.S)
            if len(cells) >= 3:
                rows.append((section, text(cells[0]), text(cells[2]), text(cells[1])))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("page")
    ap.add_argument("-o", "--out", default="line6_based_on.csv")
    a = ap.parse_args(argv)
    page = open(a.page, encoding="utf-8", errors="replace").read()
    rows = parse(page)
    if not rows:
        sys.exit("no model rows found: is this the saved Helix models page?")
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "line6_name", "based_on", "subcat"])
        w.writerows(rows)
    print(f"{len(rows)} models -> {a.out}")


if __name__ == "__main__":
    main()
