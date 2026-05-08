from pathlib import Path

src = Path('tmp_hint_update_patch.txt')
text = src.read_text(encoding='utf-8').splitlines()

header = text[0:2]
footer = [text[-1]]
body = text[2:-1]

hunks = []
current = []
for line in body:
    if line.strip() == "" and current:
        hunks.append(current)
        current = []
    else:
        current.append(line)
if current:
    hunks.append(current)

chunk_size = 90
out_dir = Path('patch_chunks')
out_dir.mkdir(exist_ok=True)

for i in range(0, len(hunks), chunk_size):
    chunk_hunks = hunks[i:i+chunk_size]
    lines = header[:]
    for h in chunk_hunks:
        lines.extend(h)
        lines.append("")
    lines.extend(footer)
    out_path = out_dir / f'chunk_{i//chunk_size+1:02d}.txt'
    out_path.write_text("\n".join(lines), encoding='utf-8')

print(f"chunks={len(list(out_dir.glob('chunk_*.txt')))}")
