import re
from pathlib import Path

path = Path('assets/puzzles.json')
lines = path.read_text(encoding='utf-8').splitlines()

# Token pool for replacements (ASCII to avoid overlap with Chinese answers)
TOKENS = [
    "alpha","bravo","charlie","delta","echo","foxtrot","golf","hotel","india","juliet",
    "kilo","lima","mike","november","oscar","papa","quebec","romeo","sierra","tango",
    "uniform","victor","whiskey","xray","yankee","zulu",
]

hunks = []
current_answer = ""
in_hints = False
item_changes = []  # list of (start_idx, end_idx, replacements dict)
replacements = {}
changed_indices = []
token_i = 0

for idx, line in enumerate(lines):
    answer_match = re.search(r'"answer"\s*:\s*"(.*)"', line)
    if answer_match:
        current_answer = answer_match.group(1)
        token_i = 0
        replacements = {}
        changed_indices = []

    if '"hints"' in line and '[' in line:
        in_hints = True
        continue

    if in_hints and line.strip().startswith(']'):
        in_hints = False
        if changed_indices:
            item_changes.append((min(changed_indices), max(changed_indices), dict(replacements)))
            replacements = {}
            changed_indices = []
        continue

    if in_hints:
        m = re.match(r'^(\s*)"(.*)"(,?)\s*$', line)
        if m and current_answer:
            hint = m.group(2)
            answer_chars = set(current_answer)
            if any(ch in answer_chars for ch in hint):
                token = TOKENS[token_i % len(TOKENS)]
                token_i += 1
                new_line = f'{m.group(1)}"{token}"{m.group(3)}'
                replacements[idx] = new_line
                changed_indices.append(idx)

# Build hunks
for start_idx, end_idx, repl in item_changes:
    hunk_start = max(0, start_idx - 3)
    hunk_end = min(len(lines) - 1, end_idx + 3)
    hunk_lines = []
    for i in range(hunk_start, hunk_end + 1):
        if i in repl:
            hunk_lines.append(("-", lines[i]))
            hunk_lines.append(("+", repl[i]))
        else:
            hunk_lines.append((" ", lines[i]))
    hunks.append(hunk_lines)

patch_lines = ["*** Begin Patch", f"*** Update File: {path.resolve()}"]
for hunk_lines in hunks:
    for prefix, text in hunk_lines:
        if prefix == " ":
            patch_lines.append(text)
        else:
            patch_lines.append(prefix + text)
    patch_lines.append("")
patch_lines.append("*** End Patch")

patch_text = "\n".join(patch_lines)
Path('/tmp/puzzles_patch.txt').write_text(patch_text, encoding='utf-8')

print(f"hunks={len(hunks)}")
print("patch_written=/tmp/puzzles_patch.txt")
