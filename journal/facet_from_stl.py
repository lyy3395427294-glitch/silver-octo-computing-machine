# -*- coding: utf-8 -*-
"""Facet body from STL -> decimate -> smooth -> convergent body -> STEP.

usage: run_journal facet_from_stl.py -args <in.stl> <out.prt> <out.step> <resp.json> [decimate_pct]

Builds everything in a fresh millimetre part, so it never touches the input
file. Every step is isolated and reported.
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
    stl, out_prt, out_step, resp = [os.path.abspath(x) for x in sys.argv[1:5]]
    pct = float(sys.argv[5]) if len(sys.argv) > 5 else 50.0
    R = {"ok": False, "steps": {}, "log": []}

    def log(msg):
        R["log"].append("%s %s" % (now(), msg))

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

    state = {"part": None, "body": None}

    def snap():
        part = state["part"]
        out = []
        for f in part.FacetedBodies:
            d = {"tag": str(f.Tag)}
            try:
                d["facets"] = int(f.GetNumberOfFacets(0))
            except Exception:
                pass
            for key, attr in (("area", "SurfaceArea"), ("volume", "Volume")):
                try:
                    d[key] = round(float(getattr(f, attr)), 3)
                except Exception:
                    pass
            out.append(d)
        return out

    def body_list():
        part = state["part"]
        out = []
        for b in part.Bodies:
            item = {"tag": str(b.Tag)}
            try:
                item["solid"] = bool(b.IsSolidBody)
                item["convergent"] = bool(b.IsConvergentBody)
            except Exception:
                pass
            try:
                item["facets"] = int(b.GetNumberOfFacets())
            except Exception:
                pass
            out.append(item)
        return out

    # ---- 1) new part --------------------------------------------------------
    def do_new():
        b = s.Parts.FileNew()
        b.TemplateFileName = "model-plain-1-mm-template.prt"
        b.NewFileName = out_prt
        b.MakeDisplayedPart = True
        b.Units = NXOpen.Part.Units.Millimeters
        b.Commit()
        b.Destroy()
        state["part"] = s.Parts.Work
        return {"work": state["part"].FullPath}

    run_step("new_part", do_new)
    if state["part"] is None:
        with open(resp, "w", encoding="utf-8") as fh:
            json.dump(R, fh, ensure_ascii=False, indent=1)
        return

    part = state["part"]

    # ---- 2) import STL as a facet body -------------------------------------
    def do_import():
        b = part.FacetedBodies.CreateSTLImportBuilder()
        b.File = stl
        b.STLFileUnits = NXOpen.Facet.STLImportBuilder.STLFileUnitsTypes.Millimeters
        b.FacetBodyType = NXOpen.Facet.STLImportBuilder.FacetBodyTypes.Psm
        b.AngularTolerance = NXOpen.Facet.STLImportBuilder.AngularToleranceTypes.Fine
        try:
            b.ShowInformationWindow = False
        except Exception:
            pass
        b.Commit()
        b.Destroy()
        fbs = list(part.FacetedBodies)
        if not fbs:
            raise RuntimeError("no facet body created")
        state["body"] = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))
        return {"facetBodies": snap()}

    run_step("import_stl", do_import)

    # ---- 3) decimate --------------------------------------------------------
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
        return {"facetBodies": snap()}

    run_step("decimate", do_decimate)

    # ---- 4) smooth ----------------------------------------------------------
    def do_smooth():
        tags = {str(f.Tag) for f in part.FacetedBodies}
        b = part.FacetedBodies.CreateSmoothFacetBodyBuilder()
        b.FacetBodies.Add(state["body"])
        b.NumberOfIterations = 2
        b.SmoothFactor = 0.3
        b.Commit()
        b.Destroy()
        new = [f for f in part.FacetedBodies if str(f.Tag) not in tags]
        if new:
            state["body"] = max(new, key=lambda f: int(f.GetNumberOfFacets(0)))
        return {"facetBodies": snap()}

    run_step("smooth", do_smooth)

    # ---- 5) convert facet -> convergent body --------------------------------
    def do_convert():
        before = {str(b.Tag) for b in part.Bodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(state["body"])
        b.OutputType = NXOpen.Facet.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = NXOpen.Facet.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = False
        b.Commit()
        b.Destroy()
        return {"newBodies": [x for x in body_list() if x["tag"] not in before]}

    run_step("convert", do_convert)
    R["bodiesAfterConvert"] = body_list()

    # ---- 6) save ------------------------------------------------------------
    def do_save():
        part.SaveAs(out_prt)
        time.sleep(0.5)
        return {"bytes": os.path.getsize(out_prt)}

    run_step("save", do_save)
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

    # ---- 7) STEP AP242 (tessellated geometry) -------------------------------
    def do_step():
        base = os.environ.get("UGII_BASE_DIR", r"E:\Program Files\Siemens\Designcenter2606")
        c = s.DexManager.CreateStepCreator()
        c.SettingsFile = os.path.join(base, "TRANSLATORS", "step242", "step242ug.def")
        c.ExportFrom = NXOpen.StepCreator.ExportFromOption.ExistingPart
        c.InputFile = out_prt
        c.ExportAs = NXOpen.StepCreator.ExportAsOption.Ap242
        c.FileSaveFlag = False
        c.ProcessHoldFlag = True
        c.OutputFile = out_step
        c.Commit()
        c.Destroy()
        deadline = time.time() + 30
        while time.time() < deadline and not os.path.exists(out_step):
            time.sleep(0.3)
        time.sleep(0.5)
        if not os.path.exists(out_step):
            raise RuntimeError("STEP not written")
        txt = open(out_step, "r", errors="ignore").read()
        keys = ("MANIFOLD_SOLID_BREP", "ADVANCED_FACE", "TRIANGULATED_FACE_SET",
                "TESSELLATED_", "CARTESIAN_POINT", "SHELL_BASED_SURFACE_MODEL")
        return {"bytes": os.path.getsize(out_step),
                "counts": {k: txt.count(k) for k in keys}}

    run_step("export_step", do_step)

    R["ok"] = bool(R["steps"].get("save", {}).get("ok"))
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)