# -*- coding: utf-8 -*-
"""Facet lab v3 (heavy scan mesh): decimate -> cleanup repair -> convert.

usage: run_journal facet_lab3.py -args <src.prt> <out.prt> <resp.json> [pct]
"""
import json
import os
import sys
import time
import traceback

import NXOpen
import NXOpen.Facet


def now():
    return time.strftime("%H:%M:%S")


def main():
    src, out_prt, resp = [os.path.abspath(x) for x in sys.argv[1:4]]
    pct = float(sys.argv[4]) if len(sys.argv) > 4 else 50.0
    R = {"ok": False, "src": src, "out": out_prt, "steps": {}, "log": []}
    F = NXOpen.Facet
    s = NXOpen.Session.GetSession()

    def log(m):
        R["log"].append("%s %s" % (now(), m))

    def run_step(name, fn):
        t = time.time()
        try:
            data = fn()
            R["steps"][name] = {"ok": True, "seconds": round(time.time() - t, 1), "data": data}
            log("%s ok in %.1fs" % (name, time.time() - t))
        except Exception:
            R["steps"][name] = {"ok": False, "seconds": round(time.time() - t, 1),
                                "error": traceback.format_exc()}
            log("%s FAILED in %.1fs" % (name, time.time() - t))
        return R["steps"][name]

    r = s.Parts.Open(src)
    part = r[0] if isinstance(r, tuple) else r

    def fsnap():
        out = []
        for f in part.FacetedBodies:
            d = {"tag": str(f.Tag)}
            try:
                d["facets"] = int(f.GetNumberOfFacets(0))
            except Exception:
                pass
            try:
                d["area"] = round(float(f.SurfaceArea), 1)
            except Exception:
                pass
            try:
                assoc = f.AssociatedBody
                d["associated"] = str(assoc.Tag) if assoc is not None else None
            except Exception as exc:
                d["associated"] = "err: %s" % exc
            try:
                d["assocLoaded"] = bool(f.IsAssociatedBodyLoaded)
            except Exception:
                pass
            out.append(d)
        return out

    R["input"] = fsnap()
    fbs = list(part.FacetedBodies)
    big = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))
    log("big facet body tag=%s facets=%d" % (big.Tag, big.GetNumberOfFacets(0)))
    state = {"body": big}

    def do_decimate():
        b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
        b.FacetBodies.Add(state["body"])
        b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = pct
        b.AngleThreshold = 15.0
        b.IsLockBoundary = True
        b.Commit()
        b.Destroy()
        return {"facetBodies": fsnap()}

    run_step("decimate", do_decimate)

    def do_cleanup():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateCleanupFacetBodyBuilder()
        b.InputBodies.Add(state["body"])
        b.SetAllOptionsToRepair()
        try:
            b.ShowInfo = False
        except Exception:
            pass
        b.Commit()
        b.Destroy()
        new = [f for f in part.FacetedBodies if str(f.Tag) not in tags]
        return {"newBodies": [{"tag": str(f.Tag), "facets": int(f.GetNumberOfFacets(0))} for f in new],
                "facetBodies": fsnap()}

    run_step("cleanup_repair", do_cleanup)

    def do_convert():
        before = {str(x.Tag) for x in part.Bodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(state["body"])
        b.OutputType = F.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = F.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = True
        b.MinimumFacetNumber = 100
        b.Commit()
        b.Destroy()
        new = []
        for x in part.Bodies:
            if str(x.Tag) in before:
                continue
            new.append({"tag": str(x.Tag),
                        "solid": bool(x.IsSolidBody),
                        "convergent": bool(x.IsConvergentBody),
                        "facets": int(x.GetNumberOfFacets())})
        return {"newBodies": new}

    run_step("convert", do_convert)

    def do_save():
        if os.path.exists(out_prt):
            os.remove(out_prt)
        part.SaveAs(out_prt)
        time.sleep(1.0)
        return {"bytes": os.path.getsize(out_prt) if os.path.exists(out_prt) else 0}

    run_step("save", do_save)
    R["finalFacetBodies"] = fsnap()
    R["ok"] = bool(R["steps"].get("save", {}).get("ok"))
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)