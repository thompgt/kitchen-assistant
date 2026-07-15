import json

nb = json.load(open("notebooks/04_app_demo.ipynb", encoding="utf-8"))
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    outs = cell.get("outputs", [])
    print(f"--- cell {i} ---")
    for o in outs:
        if "text" in o:
            print("".join(o["text"])[:1000])
        elif o.get("output_type") == "error":
            print("ERROR:", o.get("ename"), o.get("evalue"))
    print()
