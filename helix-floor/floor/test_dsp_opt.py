#!/usr/bin/env python3
"""The listed DSP groups are the proven ones, whole pairs only, and no two write the same parcels (no firmware needed)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
port = json.load(open(os.path.join(HERE, "dsp_opt_floor.json"), encoding="utf-8"))
names = [g["name"] for g in port["groups"]]
assert len(names) == len(set(names)) == 32, len(names)
assert not set(names) & {"ring_read", "smallk_2719", "smallk_271a"}, "a group known to be broken on the Floor is listed"
for pair in port["together"]:
    assert all(n in names for n in pair), pair
ranges = sorted((g["first"], g["end"], g["name"]) for g in port["groups"])
for (_, end, a), (first, _, b) in zip(ranges, ranges[1:]):
    assert end <= first, f"{a} overlaps {b}"
for g in port["groups"]:
    assert g["set"] and all(g["first"] <= p < g["end"] and 0 <= v <= 0xFFFF for p, v in g["set"]), g["name"]
    assert len(g["stock_sha256"]) == 64
print("dsp_opt list: ok,", len(names), "groups,", sum(len(g["set"]) for g in port["groups"]), "values")
