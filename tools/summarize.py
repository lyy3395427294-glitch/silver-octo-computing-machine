import collections
import json
import sys

p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
for part in d["parts"]:
    print("=" * 70)
    print(part["path"], "| bodies:", part.get("bodyCount"),
          "| facetBodies:", part.get("facetedBodyCount"),
          "| feats:", part.get("featureCount"))
    for i, f in enumerate(part.get("facetedBodies", [])):
        print(" facet#%02d facets=%-14s faces=%-7s lods=%-2s vol=%-12s area=%-12s type=%s" % (
            i, f.get("facetsPerLod"), f.get("faces"), f.get("lods"),
            str(f.get("volume"))[:12], str(f.get("area"))[:12], f.get("bodyType")))
    print(" bodies(solid,sheet,facetCount):",
          [(b.get("isSolid"), b.get("isSheet"), b.get("facetCountBody")) for b in part.get("bodies", [])])
    c = collections.Counter(x["type"] for x in part.get("features", []))
    print(" top features:", c.most_common(10))