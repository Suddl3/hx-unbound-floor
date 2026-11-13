"""Draft real-gear short names (<= 16 chars, the Floor's name fields) for the Floor's models.

Nothing here is shipped data: you supply the inputs, on your own machine, and the output stays local
(helix-floor/names/names.csv is git-ignored). See helix-floor/docs/CUSTOM_NAMES.md.

usage: draft_names.py --stock models_stock.csv --based-on line6_based_on.csv [--overrides overrides.csv] [--out DIR]
  models_stock.csv    internal,category,subcategory,db_display,table2_short,browser,browser_cats  (your Floor's model list)
  line6_based_on.csv  section,line6_name,based_on,subcat   (Line 6's public "Based on" model list)
  overrides.csv       floor_name,real_name   (optional hand-written names that win over the draft)
out: names_map.csv (what NAM_NAMES reads) and real_names_draft.csv (one row per Floor display name, with review flags)"""
import argparse, csv, re, collections, os
MAX = 16

BRANDS = [("Electro-Harmonix", "EHX"), ("MESA/Boogie", "Mesa"), ("Mesa/Boogie", "Mesa"), ("Mesa Boogie", "Mesa"),
          ("Pro Co", "ProCo"), ("TC Electronic", "TC"), ("Dunlop", "Dunlop"), ("Fulltone", "Fulltone"),
          ("Diezel", "Diezel"), ("Friedman", "Friedman"), ("Matchless", "Matchless"), ("Bogner", "Bogner"),
          ("Soldano", "Soldano"), ("Engl", "ENGL"), ("ENGL", "ENGL"), ("Peavey", "Peavey"), ("Orange", "Orange"),
          ("Gibson", "Gibson"), ("Hiwatt", "Hiwatt"), ("Supro", "Supro"), ("Ampeg", "Ampeg"), ("Gallien-Krueger", "GK"),
          ("Dr. Z", "Dr Z"), ("Divided by 13", "Div/13"), ("Park", "Park"), ("Revv", "Revv"), ("PRS", "PRS"),
          ("Chandler Limited", "Chandler"), ("Teletronix", "Teletronix"), ("Universal Audio", "UA"),
          ("Maestro", "Maestro"), ("Roland", "Roland"), ("Boss", "Boss"), ("BOSS", "Boss"), ("Ibanez", "Ibanez"),
          ("DigiTech", "DigiTech"), ("Eventide", "Eventide"), ("Klon", "Klon"), ("Paul Cochrane", "Cochrane"),
          ("Tech 21", "Tech21"), ("Arbiter", "Arbiter"), ("Vox", "Vox"), ("VOX", "Vox"), ("Fender", "Fender"),
          ("Marshall", "Marshall"), ("Line 6", "Line 6"), ("Dumble", "Dumble"), ("Bad Cat", "Bad Cat"),
          ("Carr", "Carr"), ("Two-Rock", "Two-Rock"), ("Victory", "Victory"), ("EVH", "EVH"), ("Cali", "Mesa")]
# Line 6's channel/voicing suffixes on amp names: kept on the draft (they name the real amp's channel)
SUFFIX = re.compile(r"\s(Nrm|Brt|Bright|Jump|Jmp|Jumped|Norm|Vib|Rhy|Rhythm|Lead|Crunch|Red|Ylw|Yellow|Grn|Green|Blue|"
                    r"Org|Orange|Cln|Clean|Drv|Drive|Ch\d|Crn|Hi|Lo|Mid|Plus|Custom|Nrm\d?|Brt\d?|B|C|D|V\d)$", re.I)
SHORT = [(r"\s*\([^)]*\)", ""), (r"\bversion\b", "v"), (r"\bReverb\b", "Rvb"), (r"\bDeluxe\b", "Dlx"),
         (r"\bChannel\b", "Ch"), (r"\bOverdrive\b", "OD"), (r"\bDistortion\b", "Dist"), (r"\bCompressor\b", "Comp"),
         (r"\bChorus\b", "Chor"), (r"\bFlanger\b", "Flngr"), (r"\bPhaser\b", "Phsr"), (r"\bTremolo\b", "Trem"),
         (r"\bVibrato\b", "Vib"), (r"\bEcho\b", "Echo"), (r"\bDelay\b", "Dly"), (r"\bSuper\b", "Sup"),
         (r"\bExtension\b", "Ext"), (r"\bcombo\b", ""), (r"\bwith\b", "w/"), (r"\bSpecial\b", "Spcl"),
         (r"\bAnniversary\b", "Anniv"), (r"\bModified\b", "Mod"), (r"\s+", " ")]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("line6", "line 6"))


def draft(floor_name, line6_name, based, section):
    if not based or "Line 6 Original" in based or "Line 6" == based.strip():
        return floor_name, "Line 6 original: name kept"
    b = based.replace("×", "x").replace('"', "").replace("″", "")
    for k, v in (("®", ""), ("™", ""), ("÷", "Div"), ("Ü", "U"), ("ü", "u"),
                 ("é", "e"), ("ö", "o"), ("’", "'"), ("“", ""), ("”", ""), ("–", "-")):
        b = b.replace(k, v)
    b = "".join(ch for ch in b if ord(ch) < 127)
    for k, v in BRANDS:
        b = re.sub(r"\b" + re.escape(k) + r"\b", v, b)
    paren = re.findall(r"\(([^)]*)\)", b)
    suf = SUFFIX.search(" " + line6_name) if section == "AMP MODELS" else None
    for pat, rep in SHORT:
        b = re.sub(pat, rep, b, flags=re.I)
    b = b.strip(" ,;")
    if section == "CAB MODELS":
        size = re.match(r"\d+x\d+", floor_name)
        if size and not b.startswith(size.group()):
            b = size.group() + " " + re.sub(r"^\d+x\d+\s*", "", b)
    if suf and not b.lower().endswith(suf.group(1).lower()):
        b = f"{b} {suf.group(1)}"
    note = ("source note: " + "; ".join(paren)) if paren else ""
    for drop in (r"(preamp|head|Portaflex|amplifier|amp|pedal)", ):
        if len(b) > MAX:
            b = re.sub(r"\s+", " ", re.sub(drop, "", b, flags=re.I)).strip()
    brands = {v for _, v in BRANDS} | {"Paul Reed Smith", "Pearce", "Aguilar"}
    if len(b) > MAX:                                   # no room for the brand: the model name alone
        for br in sorted(brands, key=len, reverse=True):
            if b.startswith(br + " "):
                b = b[len(br) + 1:]
                note = (note + "; " if note else "") + f"brand {br} dropped"
                break
    for pat, rep in ((r"Sup Lead (\d+)", r"SL"), (r"AC-(\d+)", r"AC"), (r"JCM-", "JCM"),
                     (r"JTM-", "JTM"), (r"Twin Rvb", "Twin"), (r"Bassman", "Bassman")):
        if len(b) > MAX:
            b = re.sub(pat, rep, b)
    if len(b) > MAX:
        cut = b[:MAX].rstrip()
        return cut, ("TOO LONG, cut from '" + b + "'" + ("; " + note if note else ""))
    return b, note


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draft real-gear short names for the Floor's models")
    ap.add_argument("--stock", required=True)
    ap.add_argument("--based-on", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("--out", default=".")
    a = ap.parse_args(argv)
    HERE = a.out
    floor = list(csv.DictReader(open(a.stock, encoding="utf-8")))
    l6 = list(csv.DictReader(open(a.based_on, encoding="utf-8")))
    by = collections.defaultdict(list)
    for r in l6:
        by[norm(r["line6_name"])].append(r)
    groups = collections.OrderedDict()
    for r in floor:
        if not r["browser"]:
            continue
        name = r["browser"].split("|")[0]
        g = groups.setdefault(name, {"internals": [], "category": r["category"]})
        g["internals"].append(r["internal"])
    rows, unmatched = [], 0
    for name, g in groups.items():
        hit = by.get(norm(name)) or by.get(norm(re.sub(r"\s+(Mono|Stereo)$", "", name)))
        if not hit:                                          # a looser match: Floor names can be shortened
            hit = [r for k, v in by.items() for r in v if k.startswith(norm(name)[:10])][:1]
        if hit:
            h = hit[0]
            d, note = draft(name, h["line6_name"], h["based_on"], h["section"])
            rows.append([g["category"], name, h["line6_name"], h["based_on"], d, len(d), note, " ".join(g["internals"])])
        else:
            unmatched += 1
            rows.append([g["category"], name, "", "", name, len(name), "NO MATCH on line6.com list: kept", " ".join(g["internals"])])
    ov = ({r["floor_name"]: r["real_name"] for r in csv.DictReader(open(a.overrides, encoding="utf-8"))}
          if a.overrides else {})
    for r in rows:
        if r[1] in ov:
            r[4], r[5], r[6] = ov[r[1]], len(ov[r[1]]), "hand-written (overrides)"
    dup = collections.Counter((r[0], r[4]) for r in rows)
    for r in rows:
        assert len(r[4]) <= MAX, r
        flags = []
        if dup[(r[0], r[4])] > 1:
            flags.append("DUPLICATE in category")
        if any(ord(ch) > 126 for ch in r[4]):
            flags.append("NON-ASCII (Floor font?)")
        if flags:
            r[6] = " / ".join(flags) + ("; " + r[6] if r[6] else "")
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(os.path.join(HERE, "names_map.csv"), "w", newline="", encoding="utf-8") as f:   # what the build reads
        w = csv.writer(f)
        w.writerow(["internal", "floor_name", "real_name"])
        w.writerows([i, r[1], r[4]] for r in rows for i in r[7].split() if r[4] != r[1])
    try:
        with open(os.path.join(HERE, "real_names_draft.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "floor_name", "line6_page_name", "based_on (line6.com)", "draft_real_name", "len",
                        "review_note", "internal_models"])
            w.writerows(rows)
    except PermissionError:
        print("real_names_draft.csv is open elsewhere (Excel?): not rewritten; names_map.csv is current")
    c = collections.Counter("TOO LONG" in r[6] for r in rows)
    print(f"{sum('DUPLICATE' in r[6] for r in rows)} duplicates, {sum('NON-ASCII' in r[6] for r in rows)} non-ASCII; {len(rows)} names; {unmatched} without a line6.com match; {c[True]} cut to 16 (review); "
          f"{sum('Line 6 original' in r[6] for r in rows)} Line 6 originals kept")


if __name__ == "__main__":
    main()
