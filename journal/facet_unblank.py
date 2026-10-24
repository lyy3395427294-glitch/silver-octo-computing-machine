# -*- coding: utf-8 -*-
"""Is the big scan mesh blanked / on a hidden layer? Try unblank then decimate.

usage: run_journal facet_unblank.py -args <src.prt> <resp.json> <facet_tag>
"""
import json
import os
import sys
import traceback

import NXOpen
import NXOpen.Facet


def main():
    src, resp, tag = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
    R = {"ok": False, "steps": {}, "log": []}
    F = NXOpen.Facet
    s = NXOpen.Session.GetSession()
    r = s.Parts.Open(src)
    part = r[0] if isinstance(r, tuple) else r

    body = None
    for f in part.FacetedBodies:
        if str(f.Tag) == str(tag):
            body = f
    if body is None:
        R["error"] = "facet body %s not found" % tag
    else:
        R["members"] = [n for n in dir(body) if not n.startswith("_")]
        for key in ("IsBlanked", "Layer", "IsHidden"):
            try:
                v = getattr(body, key)
                R[key] = v if isinstance(v, (int, float, bool, str)) else str(v)
            except Exception as exc:
                R[key] = "err: %s" % exc
        try:
            body.Unblank()
            R["unblank"] = "ok"
        except Exception:
            R["unblank"] = traceback.format_exc()
        try:
            b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
            b.FacetBodies.Add(body)
            b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
            b.Percentage = 50.0
            b.AngleThreshold = 180.0
            b.Commit()
            b.Destroy()
            R["steps"]["decimate"] = {"ok": True, "facets": int(body.GetNumberOfFacets(0)),
                                      "faces": int(body.NumberOfFaces)}
        except Exception:
            R["steps"]["decimate"] = {"ok": False, "error": traceback.format_exc()}
        R["ok"] = True

    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[2], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)