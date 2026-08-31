"""Valide la syntaxe JavaScript des blocs inline de index.html (node vm.Script)."""
import re
import subprocess
import sys

path = "/Users/demba.koita-laha/Documents/livrables/agentia-ia/portail/index.html"
html = open(path, encoding="utf-8").read()
blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
print("blocs inline:", len(blocks))
for i, block in enumerate(blocks):
    tmp = f"/tmp/index_block_{i}.js"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(block)
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERREUR SYNTAXE bloc {i}:")
        print(r.stderr[:2000])
        sys.exit(1)
    print(f"bloc {i}: syntaxe OK ({len(block)} chars)")
print("TOUS LES BLOCS SONT VALIDES")
