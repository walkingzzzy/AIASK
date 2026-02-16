from pathlib import Path
md = Path('功能借鉴与参考报告_AlphaGPT_2026-02-15.md').read_text(encoding='utf-8')
bt = chr(96)
parts = md.split(bt)
refs=[]
for i in range(1, len(parts), 2):
    t=parts[i]
    if '.py:' in t:
        p,ln=t.rsplit(':',1)
        ln=ln.strip()
        if ln.isdigit():
            refs.append((p.strip(), int(ln)))
seen=set(); uniq=[]
for r in refs:
    if r in seen: continue
    seen.add(r); uniq.append(r)
print('TOTAL_REFS', len(refs))
print('UNIQ_REFS', len(uniq))
for p,l in uniq:
    fp=Path(p)
    if not fp.exists():
        print(f'MISSING|{p}|{l}')
        continue
    lines = fp.read_text(encoding='utf-8', errors='ignore').splitlines()
    if not (1 <= l <= len(lines)):
        print(f'OOR|{p}|{l}|LEN={len(lines)}')
        continue
    line = lines[l-1].strip().replace('|','｜')
    print(f'OK|{p}|{l}|LEN={len(lines)}|LINE={line[:120]}')
