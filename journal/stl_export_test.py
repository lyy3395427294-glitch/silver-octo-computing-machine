# -*- coding: utf-8 -*-
"""STL export test: dump the whole part to STL via DexManager STLCreator.

usage: run_journal stl_export_test.py -args <part.prt> <out.stl> <resp.json>
"""
import json
import os
import struct
import sys
import time
import traceback

import NXOpen


def stl_tri_count(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(84)
        if len(head) < 84:
            return None
        n = struct.unpack("<I", head[80:84])[0]
        if os.path.getsize(path) == 84 + n * 50:
            return n
        return "ascii? bytes=%d" % os.path.getsize(path)
    except Exception as exc:
        return "err %s" % exc


def main():
    prt, out_stl, resp = [os.path.abspath(x) for x in sys.argv[1:4]]
    R = {"ok": False, "steps": {}, "log": [], "out": out_stl}
    s = NXOpen.Session.GetSession()

    def log(m):
        R["log"].append(m)

    r = s.Parts.Open(prt)
    part = r[0] if isinstance(r, tuple) else r
    log("opened %s" % part.FullPath)

    if os.path.exists(out_stl):
        os.remove(out_stl)

    try:
        c = s.DexManager.CreateStlCreator()
        c.ExportDestination = NXOpen.BaseCreator.ExportDestinationOption.NativeFileSystem
        c.OutputFile = out_stl
        c.OutputType = NXOpen.STLCreator.OutputTypeEnum.Binary
        try:
            c.ChordalTol = 0.05
            c.AngularTol = 15.0
        except Exception as exc:
            log("tol: %s" % exc)
        blocks = {}
        for name in ("ExportSelectionBlock", "ReferenceSurfaceSelectionBlock"):
            blk = getattr(c, name, None)
            blocks[name] = "None" if blk is None else [n for n in dir(blk) if not n.startswith("_")][:25]
        R["blocks"] = blocks
        c.Commit()
        c.Destroy()
        time.sleep(1.0)
        R["steps"]["export"] = {"ok": True,
                                "exists": os.path.exists(out_stl),
                                "bytes": os.path.getsize(out_stl) if os.path.exists(out_stl) else 0,
                                "triangles": stl_tri_count(out_stl)}
    except Exception:
        R["steps"]["export"] = {"ok": False, "error": traceback.format_exc()}

    R["ok"] = bool(R["steps"].get("export", {}).get("ok")) and os.path.getsize(out_stl) > 100
    with open(resp, "w", encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"ok": False, "fatal": traceback.format_exc()}, fh, ensure_ascii=False, indent=1)