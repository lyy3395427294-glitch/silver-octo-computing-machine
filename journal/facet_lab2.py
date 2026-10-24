# -*- coding: utf-8 -*-
"""Facet lab v2 on a real part: decimate the scan mesh, then convert to a
convergent body; falls back to a small facet body as an API control.

usage: run_journal facet_lab2.py -args <src.prt> <out.prt> <resp.json> [decimate_pct]
"""
import json
import os
import sys
import time
import traceback

import NXOpen


def now():
    return time.strftime("%H:%M:%S")


def main():
    src, out_prt, resp = [os.path.abspath(x) for x in sys.argv[1:4]]
    pct = float(sys.argv[4]) if len(sys.argv) > 4 else 50.0
    R = {"ok": False, "src": src, "out": out_prt, "steps": {}, "log": []}

    def log(m):
        R["log"].append("%s %s" % (now(), m))

    s = NXOpen.Session.GetSession()

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
                d["area"] = round(float(f.SurfaceArea), 2)
            except Exception:
                pass
            try:
                d["volume"] = round(float(f.Volume), 2)
            except Exception:
                pass
            out.append(d)
        return out

    def bsnap():
        out = []
        for b in part.Bodies:
            d = {"tag": str(b.Tag)}
            for k, a in (("solid", "IsSolidBody"), ("convergent", "IsConvergentBody")):
                try:
                    d[k] = bool(getattr(b, a))
                except Exception:
                    pass
            try:
                d["facets"] = int(b.GetNumberOfFacets())
            except Exception:
                pass
            out.append(d)
        return out

    R["inputFacetBodies"] = fsnap()
    fbs = list(part.FacetedBodies)
    big = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))
    small = [f for f in fbs if 1000 < int(f.GetNumberOfFacets(0)) < 20000]
    log("picked tag=%s facets=%d" % (big.Tag, big.GetNumberOfFacets(0)))

    state = {"body": big}

    def do_decimate():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
        b.FacetBodies.Add(state["body"])
        b.DecimateMethod = NXOpen.Facet.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = pct
        b.AngleThreshold = 15.0
        b.Commit()
        b.Destroy()
        new = [f for f in part.FacetedBodies if str(f.Tag) not in tags]
        if new:
            state["body"] = max(new, key=lambda f: int(f.GetNumberOfFacets(0)))
            log("new facet body tag=%s" % state["body"].Tag)
        return {"facetBodies": fsnap()}

    run_step("decimate", do_decimate)
    R["afterDecimate"] = fsnap()

    def convert(body):
        before = {str(b.Tag) for b in part.Bodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(body)
        b.OutputType = NXOpen.Facet.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = NXOpen.Facet.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = False
        b.Commit()
        b.Destroy()
        return [x for x in bsnap() if x["tag"] not in before]

    run_step("convert_big", lambda: {"newBodies": convert(state["body"])})

    if not R["steps"]["convert_big"]["ok"] and small:
        ctrl = max(small, key=lambda f: int(f.GetNumberOfFacets(0)))
        log("control: converting small facet body tag=%s facets=%d"
            % (ctrl.Tag, ctrl.GetNumberOfFacets(0)))
        run_step("convert_control", lambda: {"newBodies": convert(ctrl)})

    def do_save():
        if os.path.exists(out_prt):
            os.remove(out_prt)
        part.SaveAs(out_prt)
        time.sleep(1.0)
        return {"bytes": os.path.getsize(out_prt) if os.path.exists(out_prt) else 0}

    run_step("save", do_save)
    R["finalFacetBodies"] = fsnap()
    R["finalBodies"] = bsnap()
    R["ok"] = bool(R["steps"].get("save", {}).get("ok"))
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)