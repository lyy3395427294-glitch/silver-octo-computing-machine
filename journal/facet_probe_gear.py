# -*- coding: utf-8 -*-
"""Probe the big scan mesh in a real part: props, decimate at 50/90, convert.

usage: run_journal facet_probe_gear.py -args <src.prt> <resp.json> [facet_tag]
"""
import json
import os
import sys
import time
import traceback

import NXOpen
import NXOpen.Facet


def main():
    src, resp = [os.path.abspath(x) for x in sys.argv[1:3]]
    tag = sys.argv[3] if len(sys.argv) > 3 else None
    R = {"ok": False, "steps": {}, "log": []}
    F = NXOpen.Facet
    s = NXOpen.Session.GetSession()

    def log(m):
        R["log"].append("%s %s" % (time.strftime("%H:%M:%S"), m))

    r = s.Parts.Open(src)
    part = r[0] if isinstance(r, tuple) else r

    fbs = list(part.FacetedBodies)
    body = None
    for f in fbs:
        if tag is not None and str(f.Tag) == str(tag):
            body = f
    if body is None:
        body = max(fbs, key=lambda f: int(f.GetNumberOfFacets(0)))

    props = {"tag": str(body.Tag)}
    for key, attr in (("facets", None), ("faces", "NumberOfFaces"), ("lods", "NumberOfLevelsOfDetail"),
                      ("area", "SurfaceArea"), ("volume", "Volume"),
                      ("assemblyLevel", "IsAssemblyLevel"), ("assocLoaded", "IsAssociatedBodyLoaded")):
        try:
            if attr is None:
                props[key] = int(body.GetNumberOfFacets(0))
            else:
                v = getattr(body, attr)
                props[key] = v if isinstance(v, (int, float, bool)) else str(v)
        except Exception as exc:
            props[key] = "err: %s" % exc
    try:
        a = body.AssociatedBody
        props["associated"] = str(a.Tag) if a is not None else None
    except Exception as exc:
        props["associated"] = "err: %s" % exc
    R["bodyProps"] = props
    log("body %s facets=%s" % (props["tag"], props.get("facets")))

    def decimate(pct):
        t = time.time()
        b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
        b.FacetBodies.Add(body)
        b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
        b.Percentage = float(pct)
        b.AngleThreshold = 180.0
        b.Commit()
        b.Destroy()
        return {"pct": pct, "seconds": round(time.time() - t, 1),
                "facets": int(body.GetNumberOfFacets(0))}

    for pct in (50.0, 90.0):
        try:
            R["steps"]["decimate_%s" % int(pct)] = {"ok": True, "data": decimate(pct)}
        except Exception:
            R["steps"]["decimate_%s" % int(pct)] = {"ok": False, "error": traceback.format_exc()}

    def convert():
        before = {str(x.Tag) for x in part.Bodies}
        b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
        b.FacetedBodiesToConvert.Add(body)
        b.OutputType = F.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
        b.OriginalBodyOption = F.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
        b.CleanUp = True
        b.Commit()
        b.Destroy()
        new = []
        for x in part.Bodies:
            if str(x.Tag) in before:
                continue
            new.append({"tag": str(x.Tag), "solid": bool(x.IsSolidBody),
                        "convergent": bool(x.IsConvergentBody),
                        "facets": int(x.GetNumberOfFacets())})
        return {"newBodies": new}

    try:
        R["steps"]["convert"] = {"ok": True, "data": convert()}
    except Exception:
        R["steps"]["convert"] = {"ok": False, "error": traceback.format_exc()}

    R["ok"] = True
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[2], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)