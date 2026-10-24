# -*- coding: utf-8 -*-
"""Facet-body lab: repair -> decimate -> convert to convergent body -> save.

usage: run_journal facet_lab.py -args <src.prt> <out.prt> <resp.json> [decimate_pct]

Every step is isolated: a failing step is recorded and the next one still runs
on the best available facet body. Nothing is written back to <src.prt>.
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

    R = {"ok": False, "src": src, "out": out_prt, "decimatePct": pct, "steps": {}, "log": []}

    def log(msg):
        R["log"].append("%s %s" % (now(), msg))

    def facet_snap(part):
        out = []
        for f in part.FacetedBodies:
            d = {"tag": str(f.Tag)}
            try:
                d["lod0"] = int(f.GetNumberOfFacets(0))
            except Exception as exc:
                d["lod0"] = "err: %s" % exc
            for key, attr in (("area", "SurfaceArea"), ("volume", "Volume")):
                try:
                    d[key] = round(float(getattr(f, attr)), 3)
                except Exception:
                    pass
            try:
                d["type"] = str(f.BodyType)
            except Exception:
                pass
            out.append(d)
        return out

    def body_snap(part):
        out = []
        for b in part.Bodies:
            d = {"tag": str(b.Tag)}
            try:
                d["solid"] = bool(b.IsSolidBody)
                d["sheet"] = bool(b.IsSheetBody)
                d["convergent"] = bool(b.IsConvergentBody)
            except Exception as exc:
                d["err"] = str(exc)
            out.append(d)
        return out

    s = NXOpen.Session.GetSession()
    t0 = time.time()
    r = s.Parts.Open(src)
    part = r[0] if isinstance(r, tuple) else r
    log("opened %s in %.1fs" % (src, time.time() - t0))

    fbs = list(part.FacetedBodies)
    R["inputFacetBodies"] = facet_snap(part)
    big = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))
    log("picked facet body tag=%s facets=%d" % (big.Tag, big.GetNumberOfFacets(0)))

    def newest_facet_body(before_tags):
        cand = [f for f in part.FacetedBodies if str(f.Tag) not in before_tags]
        if not cand:
            return None
        return max(cand, key=lambda f: int(f.GetNumberOfFacets(0)))

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

    target = {"body": big}

    # ---- 1) cleanup / repair -------------------------------------------------
    def do_cleanup():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateCleanupFacetBodyBuilder()
        b.InputBodies.Add(target["body"])
        b.SetAllOptionsToRepair()
        try:
            b.ShowInfo = False
        except Exception:
            pass
        b.Commit()
        b.Destroy()
        new = newest_facet_body(tags)
        if new is not None:
            target["body"] = new
        return {"facets": facet_snap(part)}

    run_step("cleanup", do_cleanup)

    # ---- 2) decimate --------------------------------------------------------
    def do_decimate():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateDecimateFacetBodyBuilder()
        try:
            b.FacetBodies.Add(target["body"])
        except Exception:
            b.Bodies.Add(target["body"])
        b.DecimateMethod = NXOpen.Facet.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = pct
        b.AngleThreshold = 15.0
        b.IsLockBoundary = True
        b.Commit()
        b.Destroy()
        new = newest_facet_body(tags)
        if new is not None:
            target["body"] = new
        return {"facets": facet_snap(part)}

    run_step("decimate", do_decimate)

    # ---- 3) convert facet body -> convergent body ---------------------------
    def do_convert():
        before = {str(b.Tag) for b in part.Bodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(target["body"])
        b.OutputType = NXOpen.Facet.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = NXOpen.Facet.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = True
        b.Commit()
        b.Destroy()
        new = [x for x in part.Bodies if str(x.Tag) not in before]
        data = {"newBodies": len(new), "bodies": []}
        for x in new:
            item = {"tag": str(x.Tag)}
            for key, attr in (("solid", "IsSolidBody"), ("sheet", "IsSheetBody"),
                              ("convergent", "IsConvergentBody")):
                try:
                    item[key] = bool(getattr(x, attr))
                except Exception as exc:
                    item[key] = "err: %s" % exc
            try:
                item["facets"] = int(x.GetNumberOfFacets())
            except Exception as exc:
                item["facets"] = "err: %s" % exc
            data["bodies"].append(item)
        return data

    run_step("convert", do_convert)

    # ---- 4) save ------------------------------------------------------------
    def do_save():
        for path in (out_prt,):
            if os.path.exists(path):
                os.remove(path)
        part.SaveAs(out_prt)
        time.sleep(1.0)
        size = os.path.getsize(out_prt) if os.path.exists(out_prt) else 0
        return {"bytes": size}

    run_step("save", do_save)

    R["finalFacetBodies"] = facet_snap(part)
    R["finalBodies"] = body_snap(part)

    # ---- 5) reopen proves the saved copy is readable ------------------------
    def do_reopen():
        r2 = s.Parts.Open(out_prt)
        p2 = r2[0] if isinstance(r2, tuple) else r2
        return {"facetBodies": len(list(p2.FacetedBodies)),
                "bodies": len(list(p2.Bodies)),
                "convergent": sum(1 for b in p2.Bodies if b.IsConvergentBody)}

    run_step("reopen", do_reopen)

    st = R["steps"]
    R["ok"] = bool(st.get("save", {}).get("ok")) and bool(st.get("reopen", {}).get("ok"))
    R["totalSeconds"] = round(time.time() - t0, 1)
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)