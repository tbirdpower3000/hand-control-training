"""The collector bot. Runs when an issue labelled training-result is opened: reads the JSON block from the issue, checks that it
is a plausible training result (numbers only, in sensible ranges), adds it to data/results.jsonl, recomputes data/defaults.json
(the shared starting settings the atlas loads), and closes the issue with a thank-you. Anything that doesn't validate is
closed with a note and nothing is stored."""
import hashlib, json, os, re, sys, statistics as st

ISSUE_BODY = os.environ.get('ISSUE_BODY', '')
ISSUE_NUM = os.environ.get('ISSUE_NUMBER', '0')
# the GitHub username of whoever opened the issue, only to make a one-way code so each person counts once in the shared
# defaults; the username itself is never stored
ISSUE_AUTHOR = os.environ.get('ISSUE_AUTHOR', '')
OUT = 'data/results.jsonl'
DEF = 'data/defaults.json'
SALT = 'hand-control-training/contributor/v1'
MIN_PEOPLE = 5  # shared defaults are published only once this many different people have shared results


def contributor(login):
    login = (login or '').strip().lower()
    return hashlib.sha256((SALT + ':' + login).encode()).hexdigest()[:12] if login else None

LIM = {'snap': (28, 72), 'minCut': (0.25, 0.8), 'beta': (1, 3), 'pOn': (0.15, 0.45), 'pOff': (0.3, 0.7)}
CHOICES = {'hand': {'right', 'left', 'either', 'both'}, 'steady': {'steady', 'some', 'shaky'}, 'sit': {'close', 'arm', 'far'}}


def med(vals, lo, hi):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(min(hi, max(lo, st.median(vals))), 4) if vals else None


def summarise(rs):
    # smoothing and button pull carry over as they are. Pinch thresholds are only shared in the atlas's 3D world space
    # (kW, from training v0.20 on): the older image-space numbers don't mean the same thing to the atlas's 3D pinch.
    out = {n: med([r['k'][n] for r in rs], lo, hi) for n, (lo, hi) in LIM.items() if n not in ('pOn', 'pOff')}
    w = [r for r in rs if isinstance(r.get('kW'), dict)]
    if len(w) >= MIN_PEOPLE:
        out['pOn'] = med([r['kW'].get('pOn') for r in w], *LIM['pOn'])
        out['pOff'] = med([r['kW'].get('pOff') for r in w], *LIM['pOff'])
    return out | {'n': len(rs), 'n3d': len(w)}


DEFAULTS_READY = False


def write_defaults():
    """data/defaults.json from each person's latest result only (results shared before v0.40 carry no person code and count as
    one person together), published only when at least MIN_PEOPLE different people are in a group; until then it says
    ready: false and the atlas keeps its built-in starting settings."""
    global DEFAULTS_READY
    rows = [json.loads(l) for l in open(OUT) if l.strip()] if os.path.exists(OUT) else []
    latest = {}
    for r in rows:
        who = r.get('who') or 'before-v0.40'
        if who not in latest or r.get('issue', 0) >= latest[who].get('issue', 0):
            latest[who] = r
    people = list(latest.values())
    groups = {'all': people}
    for s_ in CHOICES['steady']:
        groups[s_] = [r for r in people if (r.get('answers') or {}).get('steady') == s_]
    ready = {g: rs for g, rs in groups.items() if len(rs) >= MIN_PEOPLE}
    DEFAULTS_READY = 'all' in ready
    d = {
        'format': 'hand-control-defaults',
        'version': 2,
        'note': 'Shared starting settings for hand control: the medians of the latest result of each person who chose to share from the training page. Published once at least %d different people have shared; until then ready is false and the atlas keeps its built-in settings. A personal profile always overrides them.' % MIN_PEOPLE,
        'ready': DEFAULTS_READY,
        'people': len(people),
        'needed': MIN_PEOPLE,
        'results': len(rows),
    }
    if DEFAULTS_READY:
        d['groups'] = {g: summarise(rs) for g, rs in ready.items()}
    os.makedirs('data', exist_ok=True)
    json.dump(d, open(DEF, 'w'), indent=1)
    return rows


if '--defaults-only' in sys.argv:
    write_defaults()
    print('defaults', 'ready' if DEFAULTS_READY else 'not ready')
    sys.exit(0)


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
for n in ('wobble', 'open', 'closed', 'tries', 'time', 'tremorHz', 'noise', 'fastPeak', 'fastLag', 'fastOver', 'fastSettle'):
    v = meas.get(n)
    if v is not None and (not isinstance(v, (int, float)) or v < 0 or v > 1e6):
        fail(f'{n} out of range')
rat = p.get('ratings') or {}
for n, r in (rat.items() if isinstance(rat, dict) else []):
    if not isinstance(r, dict) or r.get('score') not in (1, 2, 3, 4, 5, 6, 7):
        fail('ratings malformed')
    if r.get('effort') is not None and r.get('effort') not in (1, 2, 3, 4, 5, 6, 7):
        fail('effort rating malformed')


def num(v, lo=0, hi=1e6):
    """a finite number in range, else None"""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not (lo <= v <= hi):
        return None
    return round(float(v), 3)


CAM_LIM = {'dArm': (0, 80), 'palmCm': (5, 15), 'sphereR': (15, 80)}
# the room's light during a round, measured from the camera picture (numbers only), and how well the hand was tracked
LIGHT_LIM = {'luma': (0, 255), 'contrast': (0, 128), 'clipped': (0, 1), 'dark': (0, 1), 'backlight': (0, 10), 'handLuma': (0, 255), 'handContrast': (0, 255), 'bOverR': (0, 5), 'flicker': (0, 100)}
TRACK_LIM = {'drop': (0, 1), 'score': (0, 1), 'jitter': (0, 200)}


def cam_numbers(hands):
    """the camera models' calibration per hand: three numbers in sensible ranges, nothing else (no face data)"""
    if not isinstance(hands, dict):
        return None
    out = {}
    for h in ('Right', 'Left'):
        q = hands.get(h)
        cm = q.get('cam') if isinstance(q, dict) else None
        if not isinstance(cm, dict):
            continue
        rec_ = {}
        for n, (lo, hi) in CAM_LIM.items():
            v = cm.get(n)
            rec_[n] = round(float(v), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None
        if any(v is not None for v in rec_.values()):
            out[h] = rec_
    return out or None


def game_rows(gs):
    """the shared game rounds: a short list of known numbers only. Anything malformed drops the whole list."""
    if not isinstance(gs, list) or len(gs) > 12:
        return None
    out = []
    for g in gs:
        if not isinstance(g, dict) or g.get('kind') not in ('game', 'carry', 'fruit') or g.get('hand') not in ('Right', 'Left'):
            return None
        o = {'kind': g['kind'], 'hand': g['hand'], 't': str(g.get('t', ''))[:10], 'score': num(g.get('score')), 'trained': bool(g.get('trained'))}
        # which hand model the round used (a short id), and for adaptive rounds how often each was chosen
        mdl = g.get('model')
        o['model'] = mdl[:12] if isinstance(mdl, str) and mdl else None
        # which camera model the round used (a short id)
        mp = g.get('mapping')
        o['mapping'] = mp[:8] if isinstance(mp, str) and mp else None
        ch = g.get('choices')
        o['choices'] = {str(k)[:12]: int(v) for k, v in list(ch.items())[:8] if isinstance(v, (int, float)) and 0 <= v <= 1e6} if isinstance(ch, dict) else None
        # which features were on this round (short ids), and how often each model and feature was in play (per episode)
        ft = g.get('features')
        o['features'] = [str(x)[:12] for x in ft[:12] if isinstance(x, str)] if isinstance(ft, list) else []
        us = g.get('use')
        o['use'] = {str(k)[:12]: int(v) for k, v in list(us.items())[:16] if isinstance(v, (int, float)) and 0 <= v <= 1e6} if isinstance(us, dict) else None
        lt = g.get('light')
        o['light'] = {n: num(lt.get(n), *lim) for n, lim in LIGHT_LIM.items()} if isinstance(lt, dict) else None
        tr = g.get('track')
        o['track'] = {n: num(tr.get(n), *lim) for n, lim in TRACK_LIM.items()} if isinstance(tr, dict) else None
        # how far the person sat from the camera this round (cm, from the gap between the pupils)
        o['distCm'] = num(g.get('distCm'), 20, 300)
        vv = g.get('v')
        o['v'] = vv[:8] if isinstance(vv, str) and re.fullmatch(r'[0-9.]{1,8}', vv[:8] or '') else None
        if g['kind'] == 'game':
            for n in ('pops', 'fell', 'missPress', 'reactMs', 'bestCombo', 'level', 'effW', 'effWHits', 'tp'):
                o[n] = num(g.get(n))
            o['speed'] = num(g.get('speed'), -5, 5)
            o['accuracy'] = num(g.get('accuracy'), 0, 1)
            bs = g.get('bySize')
            if isinstance(bs, dict):
                o['bySize'] = {}
                for z, d in bs.items():
                    if not isinstance(z, str) or len(z) > 16 or not isinstance(d, dict):
                        return None
                    o['bySize'][z] = {n: num(d.get(n)) for n in ('n', 'hit', 'fell', 'miss')}
            else:
                o['bySize'] = None
        elif g['kind'] == 'fruit':
            # the fruit game: counts, swipe speed (px/s), the share of swipes that cut, the cursor's lag in swipes (ms),
            # the overshoot after a swipe (px), frames with the hand lost mid-swipe, gentle mode and the speed a swipe needed
            for n in ('sliced', 'thrown', 'barrelsHit', 'barrelsThrown', 'swipes', 'cutSwipes', 'bestCombo', 'dropsFast', 'fastFrames'):
                o[n] = num(g.get(n), 0, 1e5)
            o['peakV'] = num(g.get('peakV'), 0, 20000)
            o['acc'] = num(g.get('acc'), 0, 1)
            o['lagMs'] = num(g.get('lagMs'), 0, 1000)
            o['overPx'] = num(g.get('overPx'), 0, 2000)
            o['thr'] = num(g.get('thr'), 0, 5000)
            sw = g.get('swipe')
            o['swipe'] = {k: num(sw.get(k), 50, 6000) for k in ('slow', 'mid', 'fast')} if isinstance(sw, dict) else None
            o['gentle'] = bool(g.get('gentle'))
        else:
            for n in ('deliveries', 'slips', 'saves', 'errPx', 'timeMs', 'holdMs'):
                o[n] = num(g.get(n))
            o['eff'] = num(g.get('eff'), 0, 1)
            bp = g.get('bySpot')
            if isinstance(bp, list):
                if len(bp) > 40:
                    return None
                o['bySpot'] = []
                for d in bp:
                    if not isinstance(d, dict) or not isinstance(d.get('spot', ''), str) or len(d.get('spot', '')) > 16:
                        return None
                    o['bySpot'].append({'spot': d.get('spot', ''), 'size': num(d.get('size')), 'errPx': num(d.get('errPx')), 'ms': num(d.get('ms')), 'slips': num(d.get('slips'))})
            else:
                o['bySpot'] = None
        out.append(o)
    return out


# keep only the fields we know, so nothing else from the issue is stored
rec = {
    'issue': int(ISSUE_NUM),
    'who': contributor(ISSUE_AUTHOR),
    'k': {n: round(float(k[n]), 4) for n in LIM},
    'kW': {n: round(float(p['kW'][n]), 4) for n in ('pOn', 'pOff')} if isinstance(p.get('kW'), dict) and all(isinstance(p['kW'].get(n), (int, float)) and LIM[n][0] <= p['kW'][n] <= LIM[n][1] for n in ('pOn', 'pOff')) else None,
    'reach': {a: round(float(p['reach'][a]), 3) for a in ('xs', 'ys')} if isinstance(p.get('reach'), dict) and all(isinstance(p['reach'].get(a), (int, float)) for a in ('xs', 'ys')) else None,
    'answers': {n: ans.get(n) for n in CHOICES},
    'ratings': {n: {'score': r['score'], 'auto': bool(r.get('auto')), 'effort': r.get('effort')} for n, r in rat.items()} if isinstance(rat, dict) else None,
    'measured': {n: (round(float(meas[n]), 4) if isinstance(meas.get(n), (int, float)) else None) for n in ('wobble', 'open', 'closed', 'tries', 'time', 'tremorHz', 'noise', 'fastPeak', 'fastLag', 'fastOver', 'fastSettle')},
    'browser': str(p.get('browser', ''))[:12],
    'touch': bool(p.get('touch')),
    'when': str(p.get('when', ''))[:10],
    'games': game_rows(p.get('games')) if p.get('games') is not None else None,
    'cams': cam_numbers(p.get('hands')),
}
os.makedirs('data', exist_ok=True)
# the same issue twice (opened and labelled) counts once
if any(os.path.exists(f) and any(json.loads(l).get('issue') == rec['issue'] for l in open(f) if l.strip()) for f in (OUT, 'data/archive/results-before-v0.21.jsonl')):
    open('collect_msg.txt', 'w').write('Already stored, thanks.')
    sys.exit(0)
# the same game round shared again (a later share can repeat earlier rounds): keep only rounds not already stored
GAME_KEY = ('kind', 'hand', 't', 'score', 'pops', 'deliveries', 'missPress', 'slips', 'sliced', 'thrown', 'swipes')


def game_key(g):
    return tuple(g.get(n) for n in GAME_KEY)


skipped = 0
if rec['games']:
    seen = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            if l.strip():
                for g in json.loads(l).get('games') or []:
                    seen.add(game_key(g))
    kept = [g for g in rec['games'] if game_key(g) not in seen]
    skipped = len(rec['games']) - len(kept)
    rec['games'] = kept or None
with open(OUT, 'a') as f:
    f.write(json.dumps(rec, separators=(',', ':')) + '\n')

rows = write_defaults()
open('collect_msg.txt', 'w').write(f"Thank you! Your result is number {len(rows)}. " + ("The shared defaults in `data/defaults.json` are updated, and the atlas picks them up within a few minutes." if DEFAULTS_READY else f"The shared defaults start once {MIN_PEOPLE} different people have shared; until then the atlas keeps its built-in starting settings.") + " Only the numbers in your JSON block were stored." + (" Your game rounds were included." if rec['games'] else "") + (f" {skipped} game round{'s' if skipped != 1 else ''} you had shared before {'were' if skipped != 1 else 'was'} skipped." if skipped else ""))
print('OK', len(rows))
