import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
for name,c in d["cases"].items():
    print("="*60); print("CASE", name)
    for k in ("afterImport","convert","decimate"):
        if k not in c: continue
        v=c[k]
        print(" ",k,":", json.dumps(v, ensure_ascii=False)[:600])
    for k in ("convertOk","convertError","decimateError","fatal"):
        if k in c:
            val=str(c[k])
            print(" ",k,":", val.strip().splitlines()[-1] if "\n" in val else val)