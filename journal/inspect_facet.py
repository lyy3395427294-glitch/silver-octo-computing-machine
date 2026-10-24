# -*- coding: utf-8 -*-
"""Inspect facet bodies in one or more .prt files.

usage: run_journal inspect_facet.py -args <resp.json> <part1.prt> [part2.prt ...]
"""
import json
import sys
import traceback


def _bbox_from_facets(body, limit=4000000):
    lo = [1e30, 1e30, 1e30]
    hi = [-1e30, -1e30, -1e30]
    n = 0
    f = body.GetFirstFacetOnBody()
    while f is not None and n < limit:
        for p in f.GetVertices():
            x, y, z = p.X, p.Y, p.Z
            if x < lo[0]:
                lo[0] = x
            if y < lo[1]:
                lo[1] = y
            if z < lo[2]:
                lo[2] = z
            if x > hi[0]:
                hi[0] = x
            if y > hi[1]:
                hi[1] = y
            if z > hi[2]:
                hi[2] = z
        n += 1
        f = body.GetNextFacet(f)
    if n == 0:
        return None
    return {"min": lo, "max": hi, "size": [hi[i] - lo[i] for i in range(3)], "facets": n}


def inspect(part):
    d = {"fullPath": part.FullPath}
    try:
        d["units"] = str(part.PartUnits)
    except Exception as exc:
        d["units"] = "err: %s" % exc

    bodies = list(part.Bodies)
    d["bodyCount"] = len(bodies)
    d["bodies"] = []
    for b in bodies:
        item = {"name": getattr(b, "Name", "") or "", "tag": str(b.Tag)}
        for key, attr in (("isSolid", "IsSolidBody"), ("isSheet", "IsSheetBody"),
                          ("isConvergent", "IsConvergentBody")):
            try:
                item[key] = bool(getattr(b, attr))
            except Exception as exc:
                item[key] = "err: %s" % exc
        try:
            item["facetCountBody"] = int(b.GetNumberOfFacets())
        except Exception as exc:
            item["facetCountBody"] = "err: %s" % exc
        if item.get("isConvergent"):
            try:
                item["bbox"] = _bbox_from_facets(b)
            except Exception as exc:
                item["bbox"] = "err: %s" % exc
        d["bodies"].append(item)

    try:
        fb = list(part.FacetedBodies)
    except Exception as exc:
        fb = []
        d["facetedBodiesErr"] = str(exc)
    d["facetedBodyCount"] = len(fb)
    d["facetedBodies"] = []
    for f in fb:
        item = {"tag": str(f.Tag)}
        for key, attr in (("bodyType", "BodyType"), ("faces", "NumberOfFaces"),
                          ("lods", "NumberOfLevelsOfDetail"), ("volume", "Volume"),
                          ("area", "SurfaceArea"), ("isSolid", "IsSolidBody"),
                          ("isSheet", "IsSheetBody")):
            try:
                v = getattr(f, attr)
                try:
                    v = str(v)
                except Exception:
                    pass
                item[key] = v
            except Exception as exc:
                item[key] = "err: %s" % exc
        try:
            nlod = int(f.NumberOfLevelsOfDetail)
            item["facetsPerLod"] = [int(f.GetNumberOfFacets(i)) for i in range(min(nlod, 4))]
        except Exception as exc:
            item["facetsPerLod"] = "err: %s" % exc
        d["facetedBodies"].append(item)

    try:
        feats = list(part.Features)
        d["featureCount"] = len(feats)
        d["features"] = [{"name": getattr(x, "Name", "") or "",
                          "type": str(getattr(x, "FeatureType", ""))} for x in feats]
    except Exception as exc:
        d["featureErr"] = str(exc)
    return d


def main():
    resp = sys.argv[1]
    prts = sys.argv[2:]
    res = {"ok": False, "parts": []}
    try:
        import NXOpen
        s = NXOpen.Session.GetSession()
        for prt in prts:
            entry = {"path": prt}
            try:
                r = s.Parts.Open(prt)
                part = r[0] if isinstance(r, tuple) else r
                entry.update(inspect(part))
            except Exception:
                entry["error"] = traceback.format_exc()
            res["parts"].append(entry)
        res["ok"] = all("error" not in p for p in res["parts"])
    except Exception:
        res["fatal"] = traceback.format_exc()

    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()