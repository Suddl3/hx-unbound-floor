# Custom model names

The Floor build can show your own names for the stock amps, cabs and effects instead of Line 6's. Text only:
model ids, presets and code are unchanged.

This repository ships only the mechanism and a neutral example (`helix-floor/names/names.example.csv`).
It does not ship a list of real-gear names; make your own list locally.

## Use

1. Copy `names.example.csv` to `names.csv` (git ignores it) and edit the `real_name` column.
   - `internal` is the model's internal name and picks the row. Keep it as is.
   - `floor_name` is Line 6's name, for reference only.
   - `real_name` is what the unit shows: ASCII only, at most 16 characters.
2. Build with `NAM_NAMES` pointing at your file:

   ```
   set NAM_NAMES=helix-floor\names\names.csv
   set PYTHONUTF8=1
   python helix-floor\floor\build_floor2.py path\to\Helix_Floor_v3.80.0_0x7d01f5efb.hxf -o Helix_Floor_v3.80.0_NAM2.hxf
   ```

Names are written into the main program's Table 2 short name (16 bytes) and the browser list item (25 usable
bytes), so the same name appears in the add-block catalog and in a path.

## Drafting a full list (optional)

`helix-floor/names/draft_names.py` drafts a `real_name` for every model from two files you supply. It ships no
data, and its output goes to a folder of your choice (point `--out` at git-ignored space; `names.csv` is ignored).

```
python helix-floor/names/draft_names.py --stock models_stock.csv --based-on line6_based_on.csv ^
       [--overrides overrides.csv] --out my_names
```

- `models_stock.csv`: `internal,category,subcategory,db_display,table2_short,browser,browser_cats`, one row per
  model in your Floor's firmware. The generator uses `internal`, `category` and the first `browser` name.
- `line6_based_on.csv`: `section,line6_name,based_on,subcat`, taken from Line 6's public model list ("Based on").
  Models without a match, and Line 6 originals, keep their names.
- `overrides.csv` (optional): `floor_name,real_name`, wins over the draft.
- Output: `names_map.csv` (give it to `NAM_NAMES`) and `real_names_draft.csv` (one row per display name; review
  the flagged rows: names cut to 16 characters, duplicates, non-ASCII).

This repository does not ship a list of real-gear names, the model dump or Line 6's page.

## Cost labels (experiment)

`NAM_COST_LABELS=1` appends each model's DSP cost as a percentage of one DSP, for example `Some Drive 10%`.
Not hardware-verified for the 16-character limit in every list.
