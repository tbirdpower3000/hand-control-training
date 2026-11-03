"""The collector bot. Runs when an issue labelled training-result is opened: reads the JSON block from the issue, checks that it
is a plausible training result (numbers only, in sensible ranges), adds it to data/results.jsonl, recomputes data/defaults.json
(the shared starting settings the atlas loads), and closes the issue with a thank-you. Anything that doesn't validate is
closed with a note and nothing is stored."""
import json, os, re, sys, statistics as st

ISSUE_BODY = os.environ.get('ISSUE_BODY', '')
ISSUE_NUM = os.environ.get('ISSUE_NUMBER', '0')
OUT = 'data/results.jsonl'
DEF = 'data/defaults.json'

LIM = {'snap': (28, 72), 'minCut': (0.25, 0.8), 'beta': (1, 3), 'pOn': (0.15, 0.45), 'pOff': (0.3, 0.7)}
CHOICES = {'hand': {'right', 'left', 'either'}, 'steady': {'steady', 'some', 'shaky'}, 'sit': {'close', 'arm', 'far'}}


def fail(why):
    open('collect_msg.txt', 'w').write(f"Thanks, but this couldn't be used: {why}. Nothing was stored. If you ran the training page, try sharing again from its results screen.")
    print('REJECT', why)
    sys.exit(0)


m = re.search(r'```json\s*(\{.*?\})\s*```', ISSUE_BODY, re.S)
if not m:
    fail('no JSON block found')
try:
    p = json.loads(m.group(1))
except Exception as e:
    fail('the JSON could not be read')
if not isinstance(p, dict) or p.get('format') != 'hand-training-result':
    fail('not a training result')
k = p.get('k')
if not isinstance(k, dict):
    fail('no settings')
for n, (lo, hi) in LIM.items():
    v = k.get(n)
    if not isinstance(v, (int, float)) or not (lo <= v <= hi):
        fail(f'{n} out of range')
ans = p.get('answers') or {}
if not isinstance(ans, dict):
    fail('answers malformed')
for n, ok in CHOICES.items():
    if ans.get(n) is not None and ans.get(n) not in ok:
        fail(f'unexpected {n}')
meas = p.get('measured') or {}
if not isinstance(meas, dict):
    fail('measurements malformed')
for n in ('wobble', 'open', 'closed', 'tries', 'time'):
    v = meas.get(n)
    if v is not None and (not isinstance(v, (int, float)) or v < 0 or v > 1e6):
        fail(f'{n} out of range')
rat = p.get('ratings') or {}
for n, r in (rat.items() if isinstance(rat, dict) else []):
    if not isinstance(r, dict) or r.get('score') not in (1, 2, 3, 4, 5, 6, 7):
        fail('ratings malformed')
    if r.get('effort') is not None and r.get('effort') not in (1, 2, 3, 4, 5, 6, 7):
        fail('effort rating malformed')
# keep only the fields we know, so nothing else from the issue is stored
rec = {
    'issue': int(ISSUE_NUM),
    'k': {n: round(float(k[n]), 4) for n in LIM},
    'reach': {a: round(float(p['reach'][a]), 3) for a in ('xs', 'ys')} if isinstance(p.get('reach'), dict) and all(isinstance(p['reach'].get(a), (int, float)) for a in ('xs', 'ys')) else None,
    'answers': {n: ans.get(n) for n in CHOICES},
    'ratings': {n: {'score': r['score'], 'auto': bool(r.get('auto')), 'effort': r.get('effort')} for n, r in rat.items()} if isinstance(rat, dict) else None,
    'measured': {n: (round(float(meas[n]), 4) if isinstance(meas.get(n), (int, float)) else None) for n in ('wobble', 'open', 'closed', 'tries', 'time')},
    'browser': str(p.get('browser', ''))[:12],
    'touch': bool(p.get('touch')),
    'when': str(p.get('when', ''))[:10],
}
os.makedirs('data', exist_ok=True)
# the same issue twice (opened and labelled) counts once
if os.path.exists(OUT) and any(json.loads(l).get('issue') == rec['issue'] for l in open(OUT) if l.strip()):
    open('collect_msg.txt', 'w').write('Already stored, thanks.')
    sys.exit(0)
with open(OUT, 'a') as f:
    f.write(json.dumps(rec, separators=(',', ':')) + '\n')

# shared defaults: medians over everyone, and over each steadiness answer, with the same limits as the page
rows = [json.loads(l) for l in open(OUT) if l.strip()]


def med(vals, lo, hi):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(min(hi, max(lo, st.median(vals))), 4) if vals else None


def summarise(rs):
    return {n: med([r['k'][n] for r in rs], lo, hi) for n, (lo, hi) in LIM.items()} | {'n': len(rs)}


groups = {'all': rows}
for s_ in CHOICES['steady']:
    sub = [r for r in rows if r['answers'].get('steady') == s_]
    if len(sub) >= 3:
        groups[s_] = sub
defaults = {
    'format': 'hand-control-defaults',
    'version': 1,
    'note': 'Shared starting settings for hand control, the medians of results people chose to share from the training page. The atlas loads these as its defaults; a personal profile always overrides them.',
    'groups': {g: summarise(rs) for g, rs in groups.items()},
    'results': len(rows),
}
json.dump(defaults, open(DEF, 'w'), indent=1)
open('collect_msg.txt', 'w').write(f"Thank you! Your result is number {len(rows)}. The shared defaults in `data/defaults.json` are updated, and the atlas picks them up within a few minutes. Only the numbers in your JSON block were stored.")
print('OK', len(rows))
