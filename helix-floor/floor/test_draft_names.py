"""draft_names.py with tiny made-up inputs: matching, shortening, overrides, Line 6 originals, 16-char limit."""
import csv
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("draft_names", os.path.join(HERE, "..", "names", "draft_names.py"))
dn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dn)


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_draft_and_map(tmp_path):
    stock = tmp_path / "stock.csv"
    based = tmp_path / "based.csv"
    over = tmp_path / "over.csv"
    write(stock, ["internal", "category", "subcategory", "db_display", "table2_short", "browser", "browser_cats"],
          [["HD2_AmpFoo", "Amp", "", "Foo Amp", "Foo Amp", "Foo Amp", ""],
           ["HD2_PreampFoo", "Amp", "", "Foo Amp", "Foo Amp", "Foo Amp", ""],
           ["HD2_DistBar", "Distortion", "", "Bar Drive", "Bar Drive", "Bar Drive", ""],
           ["HD2_DistOwn", "Distortion", "", "Own Thing", "Own Thing", "Own Thing", ""],
           ["HD2_DistHand", "Distortion", "", "Hand Made", "Hand Made", "Hand Made", ""],
           ["HD2_AppDSP0", "", "", "", "", "", ""]])
    write(based, ["section", "line6_name", "based_on", "subcat"],
          [["AMP MODELS", "Foo Amp", "Acme Boxer", "Guitar"],
           ["DISTORTION MODELS", "Bar Drive", "Acme Extremely Long Overdrive Pedal Name", "Guitar"],
           ["DISTORTION MODELS", "Own Thing", "Line 6 Original", "Guitar"],
           ["DISTORTION MODELS", "Hand Made", "Something", "Guitar"]])
    write(over, ["floor_name", "real_name"], [["Hand Made", "Mine"]])
    dn.main(["--stock", str(stock), "--based-on", str(based), "--overrides", str(over), "--out", str(tmp_path)])
    rows = {r["internal"]: r for r in csv.DictReader(open(tmp_path / "names_map.csv", encoding="utf-8"))}
    assert rows["HD2_AmpFoo"]["real_name"] == "Acme Boxer"
    assert rows["HD2_PreampFoo"]["real_name"] == "Acme Boxer"       # same display name -> every internal model
    assert rows["HD2_DistHand"]["real_name"] == "Mine"              # override wins
    assert "HD2_DistOwn" not in rows                                # Line 6 original keeps its name
    assert "HD2_AppDSP0" not in rows
    assert all(len(r["real_name"]) <= 16 and r["real_name"].isascii() for r in rows.values())
    assert (tmp_path / "real_names_draft.csv").exists()


def test_read_based_on(tmp_path):
    spec2 = importlib.util.spec_from_file_location("read_based_on", os.path.join(HERE, "..", "names", "read_based_on.py"))
    rb = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(rb)
    page = """<h3>AMP MODELS</h3><div><table><tr><th><p>AMP MODELS</p></th></tr>
    <tr><td><table><tr><td><img src="x.jpg" /></td><td><p>Foo Amp </p></td></table></td>
        <td><p>Guitar</p></td><td><p style="font-size:0.7em;">Acme<sup>R</sup> Boxer (bright)</p></td><td><p>1.00</p></td></tr>
    </div><h3>CAB MODELS</h3><div><table>
    <tr><td><table><tr><td><img src="y.jpg" /></td><td><p>1x12 Bar</p></td></table></td>
        <td><p>Single</p></td><td><p>Acme 1x12 cab</p></td><td><p>1.00</p></td></tr></div>"""
    assert rb.parse(page) == [("AMP MODELS", "Foo Amp", "Acme Boxer (bright)", "Guitar"),
                              ("CAB MODELS", "1x12 Bar", "Acme 1x12 cab", "Single")]


def test_shipped_real_names_csv():
    """The list the browser builder ships: right columns, 16 ASCII characters at most, one row per model."""
    path = os.path.join(HERE, "..", "names", "real_names.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert rows and list(rows[0]) == ["internal", "floor_name", "real_name"]
    assert all(r["real_name"] and len(r["real_name"]) <= 16 and r["real_name"].isascii() for r in rows)
    assert len({r["internal"] for r in rows}) == len(rows)
