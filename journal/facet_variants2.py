# -*- coding: utf-8 -*-
"""Facet variants lab: STL -> facet body (Psm / Nx / Jt), smooth, convert.

usage: run_journal facet_variants2.py -args <in.stl> <out.prt> <resp.json>
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
    stl, out_prt, resp = [os.path.abspath(x) for x in sys.argv[1:4]]
    R = {"ok": False, "steps": {}, "log": []}
    F = NXOpen.Facet

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

    if os.path.exists(out_prt):
        os.remove(out_prt)
    b = s.Parts.FileNew()
    b.TemplateFileName = "model-plain-1-mm-template.prt"
    b.NewFileName = out_prt
    b.MakeDisplayedPart = True
    b.Units = NXOpen.Part.Units.Millimeters
    b.Commit()
    b.Destroy()
    part = s.Parts.Work

    def fsnap():
        out = []
        for f in part.FacetedBodies:
            d = {"tag": str(f.Tag)}
            try:
                d["facets"] = int(f.GetNumberOfFacets(0))
            except Exception:
                pass
            out.append(d)
        return out

    def bsnap():
        out = []
        for x in part.Bodies:
            d = {"tag": str(x.Tag)}
            for k, a in (("solid", "IsSolidBody"), ("sheet", "IsSheetBody"),
                         ("convergent", "IsConvergentBody")):
                try:
                    d[k] = bool(getattr(x, a))
                except Exception:
                    pass
            try:
                d["facets"] = int(x.GetNumberOfFacets())
            except Exception:
                pass
            out.append(d)
        return out

    def import_stl(kind, enum_value):
        b = part.FacetedBodies.CreateSTLImportBuilder()
        b.File = stl
        b.STLFileUnits = F.STLImportBuilder.STLFileUnitsTypes.Millimeters
        b.FacetBodyType = enum_value
        try:
            b.ShowInformationWindow = False
        except Exception:
            pass
        b.Commit()
        b.Destroy()
        return {"kind": kind, "facetBodies": fsnap(), "bodies": bsnap()}

    E = F.STLImportBuilder.FacetBodyTypes
    run_step("import_psm", lambda: import_stl("Psm", E.Psm))
    run_step("import_nx", lambda: import_stl("Nx", E.Nx))
    run_step("import_jt", lambda: import_stl("Jt", E.Jt))

    R["allFacetBodies"] = fsnap()
    R["allBodies"] = bsnap()
    fbs = list(part.FacetedBodies)
    target = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))
    log("target facet body tag=%s facets=%d" % (target.Tag, target.GetNumberOfFacets(0)))

    def attach(builder, body):
        errs = []
        for attr in ("FacetBodies", "Bodies"):
            try:
                lst = getattr(builder, attr)
                if lst is not None:
                    lst.Add(body)
                    return attr
                errs.append("%s=None" % attr)
            except Exception as exc:
                errs.append("%s: %s" % (attr, exc))
        raise RuntimeError("no usable body list: " + "; ".join(errs))

    def do_smooth():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.CreateSmoothFacetBodyBuilder()
        used = attach(b, target)
        b.NumberOfIterations = 2
        try:
            b.SmoothFactor = 0.3
        except Exception:
            pass
        b.Commit()
        b.Destroy()
        new = [f for f in part.FacetedBodies if str(f.Tag) not in tags]
        return {"listUsed": used,
                "newBodies": [{"tag": str(f.Tag), "facets": int(f.GetNumberOfFacets(0))} for f in new],
                "facetBodies": fsnap()}

    run_step("smooth", do_smooth)

    def do_convert():
        before = {x["tag"] for x in bsnap()}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(target)
        b.OutputType = F.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = F.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = True
        b.Commit()
        b.Destroy()
        return {"newBodies": [x for x in bsnap() if x["tag"] not in before], "bodies": bsnap()}

    run_step("convert", do_convert)

    def do_decimate():
        b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
        b.FacetBodies.Add(target)
        b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = 50.0
        b.Commit()
        b.Destroy()
        return {"facetBodies": fsnap(), "bodies": bsnap()}

    run_step("decimate", do_decimate)

    def do_save():
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                  NXOpen.BasePart.CloseAfterSave.FalseValue)
        time.sleep(0.5)
        return {"bytes": os.path.getsize(out_prt) if os.path.exists(out_prt) else 0}

    run_step("save", do_save)

    def do_probe():
        c = s.DexManager.CreateStlCreator()
        names = [n for n in dir(c) if not n.startswith("_")]
        try:
            c.Destroy()
        except Exception:
            pass
        keep = [n for n in names if any(k in n for k in ("File", "Export", "Output", "Input", "Selection"))]
        return {"members": keep, "all": names[:60]}

    run_step("probe_stl_creator", do_probe)

    R["ok"] = bool(R["steps"].get("save", {}).get("ok"))
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)