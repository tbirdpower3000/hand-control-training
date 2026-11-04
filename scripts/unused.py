"""Lists functions in index.html that nothing else refers to, so unused code can be found and removed. Run it with
`python3 -I scripts/unused.py`; it writes UNUSED.md in the repository root and prints the same list. It uses node with
the acorn parser when both are available (installed into a temporary folder), and falls back to a plain-text scan.
A name listed here is defined but never called from anywhere else in the file: either dead code or a window.* hook."""
import os, re, subprocess, sys, tempfile, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
html = open(SRC, encoding='utf-8').read()
scripts = [m for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)]
js = '\n;\n'.join(m.group(1) for m in scripts)
line_of = {}  # offset in js -> line in index.html
offs = []
pos = 0
for m in scripts:
    start_line = html[: m.start(1)].count('\n') + 1
    offs.append((pos, start_line, m.group(1)))
    pos += len(m.group(1)) + 3


def html_line(js_off):
    for p0, l0, body in offs:
        if p0 <= js_off < p0 + len(body):
            return l0 + js[p0:js_off].count('\n')
    return 0


defs = None
try:
    tmp = tempfile.mkdtemp()
    subprocess.run(['npm', 'i', '--silent', '--no-audit', '--no-fund', 'acorn@8', 'acorn-walk@8'], cwd=tmp, check=True, capture_output=True, timeout=120)
    node = r'''
const acorn=require('acorn'),walk=require('acorn-walk'),fs=require('fs');
const src=fs.readFileSync(process.argv[2],'utf8');
const ast=acorn.parse(src,{ecmaVersion:2022,sourceType:'script',allowReturnOutsideFunction:true});
const defs=[];
walk.full(ast,(n)=>{
  if(n.type==='FunctionDeclaration'&&n.id) defs.push([n.id.name,n.start]);
  if(n.type==='VariableDeclarator'&&n.id.type==='Identifier'&&n.init&&(n.init.type==='ArrowFunctionExpression'||n.init.type==='FunctionExpression')) defs.push([n.id.name,n.start]);
});
const refs={};
walk.full(ast,(n)=>{ if(n.type==='Identifier') refs[n.name]=(refs[n.name]||0)+1; });
console.log(JSON.stringify({defs,refs}));
'''
    open(os.path.join(tmp, 'scan.js'), 'w').write(node)
    jsfile = os.path.join(tmp, 'src.js')
    open(jsfile, 'w', encoding='utf-8').write(js)
    out = subprocess.run(['node', os.path.join(tmp, 'scan.js'), jsfile], check=True, capture_output=True, text=True, timeout=120).stdout
    data = json.loads(out)
    # an identifier that appears only once is its own definition
    defs = [(name, start) for name, start in data['defs'] if data['refs'].get(name, 0) <= 1]
    method = 'acorn'
except Exception as e:  # pragma: no cover - the fallback
    method = 'text scan (%s)' % e.__class__.__name__
    cands = re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', js) + re.findall(r'\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>', js)
    defs = []
    for name in sorted(set(cands)):
        n = len(re.findall(r'(?<![\w$.])' + re.escape(name) + r'(?![\w$])', js))
        if n <= 1:
            m = re.search(r'(?<![\w$.])' + re.escape(name) + r'(?![\w$])', js)
            defs.append((name, m.start() if m else 0))

rows = sorted(((html_line(off), name) for name, off in defs), key=lambda r: r[0])
hooks = [r for r in rows if False]
lines = ['# Unused functions', '', 'Functions in `index.html` that nothing else in the file refers to (scan: %s). A window.* hook that the tests call from outside is expected here; anything else is dead code.' % method, '']
lines += ['- `%s` (line %d)' % (name, ln) for ln, name in rows] or ['- none']
open(os.path.join(ROOT, 'UNUSED.md'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
