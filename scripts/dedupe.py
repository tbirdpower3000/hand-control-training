"""One-off clean-up: the same game round can have been shared more than once (each share used to repeat the last eight
rounds). This rewrites data/results.jsonl keeping the first occurrence of each round, judged by the same key the
collector now uses (kind, hand, date, score, pops, deliveries, missed pinches, slips). Results themselves are never
removed, only repeated game rounds inside them. Run it by hand, after a look at the dry run:

    python3 scripts/dedupe.py --dry-run      # counts only
    python3 scripts/dedupe.py                # rewrites data/results.jsonl (a copy is kept as results.jsonl.bak)
    python3 scripts/dedupe.py path/to/results.jsonl
"""
import json, os, shutil, sys

GAME_KEY = ('kind', 'hand', 't', 'score', 'pops', 'deliveries', 'missPress', 'slips')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
dry = '--dry-run' in sys.argv
path = args[0] if args else 'data/results.jsonl'
rows = [json.loads(l) for l in open(path) if l.strip()]
seen, before, after = set(), 0, 0
for r in rows:
    gs = r.get('games') or []
    before += len(gs)
    kept = []
    for g in gs:
        k = tuple(g.get(n) for n in GAME_KEY)
        if k not in seen:
            seen.add(k)
            kept.append(g)
    after += len(kept)
    if 'games' in r and r['games'] is not None:
        r['games'] = kept or None
print(f'{len(rows)} results, {before} game rows, {after} distinct rounds, {before - after} repeats {"would be " if dry else ""}removed')
if not dry:
    shutil.copyfile(path, path + '.bak')
    with open(path + '.tmp', 'w') as f:
        for r in rows:
            f.write(json.dumps(r, separators=(',', ':')) + '\n')
    os.replace(path + '.tmp', path)
