# -*- coding: utf-8 -*-
"""Truth table: which facet-body flavour supports convert / decimate.

usage: run_journal facet_truth.py -args <in.stl> <workdir> <resp.json>
Creates fresh parts (one per flavour) so body identity is unambiguous.
"""
import json
import os
import sys
import time
import traceback

import NXOpen
import NXOpen.Facet


def main():
    stl, workdir, resp = [os.path.abspath(x) for x in sys.argv[1:4]]
    R = {"ok": False, "cases": {}, "log": []}
    F = NXOpen.Facet
    s = NXOpen.Session.GetSession()

    def log(m):
        R["log"].append(m)

    def new_part(path):
        if os.path.exists(path):
            os.remove(path)
        b = s.Parts.FileNew()
        b.TemplateFileName = "model-plain-1-mm-template.prt"
        b.NewFileName = path
        b.MakeDisplayedPart = True
        b.Units = NXOpen.Part.Units.Millimeters
        b.Commit()
        b.Destroy()
        return s.Parts.Work

    def fsnap(part):
        out = []
        for f in part.FacetedBodies:
            d = {"tag": str(f.Tag)}
            try:
                d["facets"] = int(f.GetNumberOfFacets(0))
            except Exception:
                pass
            try:
                a = f.AssociatedBody
                d["associated"] = str(a.Tag) if a is not None else None
            except Exception:
                pass
            out.append(d)
        return out

    def bsnap(part):
        out = []
        for x in part.Bodies:
            d = {"tag": str(x.Tag)}
            try:
                d["convergent"] = bool(x.IsConvergentBody)
                d["solid"] = bool(x.IsSolidBody)
            except Exception:
                pass
            try:
                d["facets"] = int(x.GetNumberOfFacets())
            except Exception:
                pass
            out.append(d)
        return out

    def imp(part, kind):
        b = part.FacetedBodies.CreateSTLImportBuilder()
        b.File = stl
        b.STLFileUnits = F.STLImportBuilder.STLFileUnitsTypes.Millimeters
        b.FacetBodyType = kind
        try:
            b.ShowInformationWindow = False
        except Exception:
            pass
        b.Commit()
        b.Destroy()

    def try_convert(part, body):
        before = {x["tag"] for x in bsnap(part)}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(body)
        b.OutputType = F.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = F.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = True
        b.Commit()
        b.Destroy()
        return {"newBodies": [x for x in bsnap(part) if x["tag"] not in before],
                "bodies": bsnap(part)}

    def try_decimate(part, body, pct=50.0):
        b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
        b.FacetBodies.Add(body)
        b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = pct
        b.Commit()
        b.Destroy()
        return {"facetBodies": fsnap(part), "bodies": bsnap(part)}

    E = F.STLImportBuilder.FacetBodyTypes

    # ---------- case 1: NX facet body -> convert, then decimate ----------
    case = {}
    try:
        part = new_part(os.path.join(workdir, "truth_nx.prt"))
        imp(part, E.Nx)
        case["afterImport"] = {"facetBodies": fsnap(part), "bodies": bsnap(part)}
        body = list(part.FacetedBodies)[0]
        try:
            case["convert"] = try_convert(part, body)
            case["convertOk"] = True
        except Exception:
            case["convertOk"] = False
            case["convertError"] = traceback.format_exc()
        try:
            case["decimate"] = try_decimate(part, body)
        except Exception:
            case["decimateError"] = traceback.format_exc()
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                  NXOpen.BasePart.CloseAfterSave.FalseValue)
    except Exception:
        case["fatal"] = traceback.format_exc()
    R["cases"]["nx_facet"] = case

    # ---------- case 2: JT facet body -> convert ----------
    case = {}
    try:
        part = new_part(os.path.join(workdir, "truth_jt.prt"))
        imp(part, E.Jt)
        case["afterImport"] = {"facetBodies": fsnap(part), "bodies": bsnap(part)}
        body = list(part.FacetedBodies)[0]
        try:
            case["convert"] = try_convert(part, body)
            case["convertOk"] = True
        except Exception:
            case["convertOk"] = False
            case["convertError"] = traceback.format_exc()
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                  NXOpen.BasePart.CloseAfterSave.FalseValue)
    except Exception:
        case["fatal"] = traceback.format_exc()
    R["cases"]["jt_facet"] = case

    # ---------- case 3: PSM -> decimate the display facet body ----------
    case = {}
    try:
        part = new_part(os.path.join(workdir, "truth_psm.prt"))
        imp(part, E.Psm)
        case["afterImport"] = {"facetBodies": fsnap(part), "bodies": bsnap(part)}
        body = list(part.FacetedBodies)[0]
        try:
            case["decimate"] = try_decimate(part, body)
        except Exception:
            case["decimateError"] = traceback.format_exc()
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                  NXOpen.BasePart.CloseAfterSave.FalseValue)
    except Exception:
        case["fatal"] = traceback.format_exc()
    R["cases"]["psm_facet"] = case

    R["ok"] = True
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)