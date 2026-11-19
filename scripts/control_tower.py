#!/usr/bin/env python3
"""관제탑: 마스터 폴더의 구조와 상태를 한 화면으로 보여 주는 로컬 대시보드. 표준 라이브러리만 사용.

  python3 control_tower.py --root <마스터> [--log <moves_v2.csv>] [--checks <체크기 보고서 폴더>]
                           [--refresh-cmd "<새로고침 때 먼저 돌릴 읽기 전용 명령>"] [--port 8765] [--graph-url URL]

- 보기 전용이다. 이동·삭제·이름 바꾸기 기능이 없다. 파일 열기·Finder에서 보기만 있고, 마스터 안 파일로 제한한다.
- 새로고침은 폴더를 lstat으로만 다시 센다(본문을 읽지 않으므로 클라우드 파일을 내려받지 않는다).
- 이 맥에서만 접속된다(127.0.0.1). 다른 웹사이트·다른 기기의 요청은 거부한다."""
import argparse, csv, json, os, re, subprocess, sys, threading, time, unicodedata, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc, is_dataless, EXCLUDE_DIRS, free_gib

BLOCK_EXT = (".app", ".command", ".sh", ".terminal", ".workflow", ".pkg", ".dmg", ".exe", ".bat", ".cmd", ".ps1", ".lnk", ".scpt")

def scan(root, max_depth=4):
    """폴더 트리: {name, path, files, bytes, zero, cloud, children[]}. 깊이 max_depth 아래는 합계만."""
    root = os.path.abspath(root)
    def node(path, depth):
        n = {"name": nfc(os.path.basename(path)) or path, "path": nfc(os.path.relpath(path, root)), "files": 0, "bytes": 0, "zero": 0, "cloud": 0, "children": []}
        try: entries = list(os.scandir(path))
        except OSError: return n
        for e in entries:
            if e.name.startswith(".") or e.name in EXCLUDE_DIRS: continue
            try:
                if e.is_dir(follow_symlinks=False):
                    c = node(e.path, depth + 1)
                    for k in ("files", "bytes", "zero", "cloud"): n[k] += c[k]
                    if depth < max_depth: n["children"].append(c)
                elif e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    n["files"] += 1; n["bytes"] += st.st_size; n["zero"] += st.st_size == 0; n["cloud"] += is_dataless(e.path)
            except OSError: continue
        n["children"].sort(key=lambda c: -c["bytes"])
        return n
    return node(root, 0)

def zero_list(root, limit=30):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".") and d not in EXCLUDE_DIRS]
        for f in fn:
            if f.startswith("."): continue
            p = os.path.join(dp, f)
            try:
                if os.lstat(p).st_size == 0: out.append(nfc(os.path.relpath(p, root)))
            except OSError: pass
            if len(out) >= limit: return out
    return out

def read_log(path, n=15):
    if not path or not os.path.exists(path): return []
    with open(path, encoding="utf-8", newline="") as f: rows = list(csv.DictReader(f))
    return [{k: nfc(v or "") for k, v in r.items()} for r in rows[-n:]][::-1]

def read_checks(d):
    """체크기 보고서(*_check.md)의 '## 폴더 … → 누락 N'과 경고 CSV(*_warnings.csv)를 읽는다."""
    progs = []
    if not d or not os.path.isdir(d): return progs
    for f in sorted(os.listdir(d)):
        if not f.endswith("_check.md"): continue
        txt = open(os.path.join(d, f), encoding="utf-8").read()
        title = (re.search(r"^# (.+)$", txt, re.M) or [None, f])[1]
        folders = [{"folder": m.group(1), "missing": int(m.group(2))} for m in re.finditer(r"^## (\S+)[^\n]*\n.*?^→ 누락 (\d+)", txt, re.S | re.M)]
        wf = os.path.join(d, f.replace("_check.md", "_warnings.csv")); todo = []
        if os.path.exists(wf):
            with open(wf, encoding="utf-8-sig") as fh:
                todo = [r for r in csv.DictReader(fh) if r.get("status") in ("없음", "부족", "확인 필요", "원본만(정리본 없음)")]
        progs.append({"title": re.sub(r"\s*\(읽기 전용\)\s*$", "", title), "folders": folders, "todo": todo, "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(d, f))))})
    return progs

class Tower:
    def __init__(self, a):
        self.a = a; self.root = os.path.abspath(a.root); self.lock = threading.Lock(); self.state = None; self.busy = False
    def refresh(self):
        if not self.lock.acquire(blocking=False): return {"ok": False, "error": "이미 새로고침 중입니다"}
        try:
            self.busy = True; t0 = time.time(); note = ""
            if self.a.refresh_cmd:
                r = subprocess.run(self.a.refresh_cmd, shell=True, capture_output=True, timeout=600)
                if r.returncode != 0: note = "점검 명령 실패: " + r.stderr.decode("utf-8", "replace")[-200:]
            tree = scan(self.root)
            inbox = next((c for c in tree["children"] if c["name"].startswith("00_INBOX")), None)
            self.state = {"root": nfc(self.root), "tree": tree, "inbox": inbox["files"] if inbox else 0, "zeros": zero_list(self.root) if tree["zero"] else [],
                          "log": read_log(self.a.log), "checks": read_checks(self.a.checks), "free_gib": round(free_gib(os.path.expanduser("~")), 1),   # 클라우드 마운트는 서버 용량을 보고하므로 로컬 디스크를 잰다
                          "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0, 1), "note": note, "graph_url": self.a.graph_url or ""}
            return {"ok": True}
        except Exception as e: return {"ok": False, "error": str(e)}
        finally: self.busy = False; self.lock.release()
    def resolve(self, rel):
        p = os.path.realpath(os.path.join(self.root, rel)); r = os.path.realpath(self.root)
        if not (nfc(p) == nfc(r) or nfc(p).startswith(nfc(r) + os.sep)) or p.lower().endswith(BLOCK_EXT): return None
        if not os.path.exists(p):
            alt = unicodedata.normalize("NFD", p)
            p = alt if os.path.exists(alt) else None
        return p

def make_handler(tw, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def allowed(self, mutating):
            if (self.headers.get("Host") or "").lower() not in (f"localhost:{port}", f"127.0.0.1:{port}"): return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"): return False
            if mutating and self.headers.get("X-Tower") != "1": return False     # 다른 사이트는 이 헤더를 붙일 수 없다
            return True
        def send(self, code, body, ctype="application/json; charset=utf-8"):
            b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            u = urlparse(self.path)
            if not self.allowed(False): return self.send(403, {"ok": False, "error": "forbidden"})
            if u.path == "/": return self.send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/state":
                if tw.state is None: tw.refresh()
                return self.send(200, {"ok": True, "busy": tw.busy, "state": tw.state})
            self.send(404, {"ok": False})
        def do_POST(self):
            u = urlparse(self.path)
            if not self.allowed(True): return self.send(403, {"ok": False, "error": "forbidden"})
            if u.path == "/api/refresh":
                r = tw.refresh(); return self.send(200 if r["ok"] else 409, {**r, "state": tw.state})
            if u.path in ("/api/open", "/api/reveal"):
                p = tw.resolve(parse_qs(u.query).get("path", [""])[0])
                if not p: return self.send(403, {"ok": False, "error": "마스터 밖이거나 실행 파일이라 열지 않습니다"})
                opener = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
                arg = (["-R", p] if sys.platform == "darwin" else ["/select," + p] if sys.platform == "win32" else [os.path.dirname(p)]) if u.path == "/api/reveal" else [p]
                subprocess.Popen(opener + arg); return self.send(200, {"ok": True})
            self.send(404, {"ok": False})
    return H

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>파일정리 관제탑</title>
<style>
:root{--bg:#F5F7F9;--card:#fff;--fg:#1C2430;--muted:#627080;--line:#DDE3EA;--accent:#1F6F8B;--soft:#E4F0F5;--warn:#B7791F;--warn-soft:#FBF1DC;--bad:#B3412A;--bad-soft:#F9E6E1;--ok:#2E7D4F;--ok-soft:#E1F2E7;
--f:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;--m:ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#10171E;--card:#18222D;--fg:#E7EDF3;--muted:#9AA8B8;--line:#2A3846;--accent:#6FB6D1;--soft:#17303B;--warn:#E0B15A;--warn-soft:#3A2E12;--bad:#E58B74;--bad-soft:#3E201A;--ok:#6CC58F;--ok-soft:#163625;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 var(--f)}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center}
h1{font-size:19px;margin:0}h2{font-size:16px;margin:0 0 10px}
.stat{display:flex;flex-direction:column;line-height:1.2}.stat b{font-size:18px;font-variant-numeric:tabular-nums}.stat span{font-size:12px;color:var(--muted)}
.stat.bad b{color:var(--bad)}.stat.warn b{color:var(--warn)}
.sp{flex:1}button,.btn{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:7px 14px;cursor:pointer;text-decoration:none}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}button:disabled{opacity:.6;cursor:wait}
button:focus-visible,.tile:focus-visible{outline:3px solid var(--warn);outline-offset:2px}
.stale{width:100%;background:var(--warn-soft);color:var(--warn);border-radius:8px;padding:6px 12px;font-size:14px}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:16px;padding:16px 20px 40px}
@media (max-width:900px){main{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
.crumbs{font-size:14px;margin-bottom:8px;display:flex;flex-wrap:wrap;gap:4px}.crumbs a{color:var(--accent);cursor:pointer}
#map{position:relative;height:440px;border-radius:8px;overflow:hidden;background:var(--bg)}
.tile{position:absolute;border:2px solid var(--card);border-radius:6px;padding:6px 8px;overflow:hidden;cursor:pointer;color:#fff;font-size:13px;line-height:1.3}
.tile b{display:block;font-size:13.5px;word-break:break-all}.tile small{opacity:.9;font-variant-numeric:tabular-nums}
.tile .z{display:inline-block;background:#fff;color:#B3412A;border-radius:4px;padding:0 4px;font-size:11px;margin-top:2px}
.legend{font-size:12.5px;color:var(--muted);margin-top:8px}
.files{font-size:13.5px;margin-top:8px;color:var(--muted)}
.board .prog{margin-bottom:14px}.board h3{font-size:14.5px;margin:0 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{font-size:12.5px;border-radius:999px;padding:2px 10px;border:1px solid var(--line)}
.chip.ok{background:var(--ok-soft);color:var(--ok);border-color:transparent}.chip.miss{background:var(--bad-soft);color:var(--bad);border-color:transparent}
ul{margin:0;padding-left:18px}li{margin:3px 0;font-size:14px}.muted{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:5px 6px;border-top:1px solid var(--line);vertical-align:top;word-break:break-all}
.act{font-family:var(--m);font-size:12px;border-radius:5px;padding:1px 6px;background:var(--soft);color:var(--accent)}
.wide{grid-column:1/-1}
</style></head><body>
<header>
  <h1>파일정리 관제탑</h1>
  <div class="stat"><b id="sFiles">–</b><span>파일</span></div>
  <div class="stat"><b id="sSize">–</b><span>용량</span></div>
  <div class="stat" id="sZeroBox"><b id="sZero">–</b><span>0바이트</span></div>
  <div class="stat" id="sInboxBox"><b id="sInbox">–</b><span>INBOX 대기</span></div>
  <div class="stat" id="sTodoBox"><b id="sTodo">–</b><span>채울 서류</span></div>
  <div class="stat"><b id="sFree">–</b><span>디스크 여유</span></div>
  <div class="sp"></div>
  <span class="muted" id="sAt">불러오는 중…</span>
  <a class="btn" id="graph" hidden target="_blank" rel="noopener">3D 지식그래프</a>
  <button class="primary" id="refresh">새로고침</button>
  <div class="stale" id="stale" hidden></div>
</header>
<main>
  <section>
    <h2>폴더 지도</h2>
    <div class="crumbs" id="crumbs"></div>
    <div id="map" role="list"></div>
    <div class="legend">타일 크기 = 용량. 빨간 표시 = 0바이트 파일이 있는 폴더. 누르면 안으로 들어가고, Finder 버튼으로 실제 폴더를 엽니다.</div>
    <div class="files" id="here"></div>
  </section>
  <section class="board"><h2>사업 보드</h2><div id="board"><p class="muted">체크기 보고서가 없습니다.</p></div></section>
  <section><h2>채워야 할 서류</h2><div id="todo"><p class="muted">없음</p></div></section>
  <section><h2>주의할 것</h2><div id="warn"></div></section>
  <section class="wide"><h2>최근 기록</h2><div id="log"><p class="muted">로그가 없습니다.</p></div></section>
</main>
<script>
const $=id=>document.getElementById(id);
let S=null, path=[];
const fmtB=b=>b>=2**30?(b/2**30).toFixed(1)+" GiB":b>=2**20?(b/2**20).toFixed(0)+" MB":(b/1024).toFixed(0)+" KB";
const fmtN=n=>n.toLocaleString("ko-KR");
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const COLORS=["#1F6F8B","#2E7D4F","#7A5BA6","#B7791F","#3D6FB6","#A0522D","#2F8F8A","#8A4F7D","#5A7D2E","#6B6B9A"];
async function api(url,post){const r=await fetch(url,post?{method:"POST",headers:{"X-Tower":"1"}}:{});return r.json()}
async function load(){const r=await api("/api/state");S=r.state;render()}
async function refresh(){const b=$("refresh");b.disabled=true;b.textContent="새로 읽는 중…";
  try{const r=await api("/api/refresh",true);if(r.state)S=r.state;if(!r.ok)alertBar(r.error||"실패")}catch(e){alertBar("서버에 연결할 수 없습니다. 관제탑 앱을 다시 실행하세요.")}
  b.disabled=false;b.textContent="새로고침";render()}
function alertBar(t){const s=$("stale");s.hidden=false;s.textContent=t}
function cur(){let n=S.tree;for(const p of path){n=n.children.find(c=>c.name===p)||n}return n}
function squarify(items,x,y,w,h){const out=[];const total=items.reduce((a,b)=>a+b.v,0)||1;let rest=items.map(i=>({...i,a:i.v/total*w*h}));
  while(rest.length){const short=Math.min(w,h);let row=[],best=Infinity;
    for(const it of rest){const r=[...row,it],s=r.reduce((a,b)=>a+b.a,0),mx=Math.max(...r.map(t=>t.a)),mn=Math.min(...r.map(t=>t.a));
      const worst=Math.max(short*short*mx/(s*s),(s*s)/(short*short*mn));if(worst>best&&row.length)break;best=worst;row=r}
    const s=row.reduce((a,b)=>a+b.a,0);
    if(w>=h){const rw=s/h;let yy=y;for(const t of row){const th=t.a/rw;out.push({...t,x,y:yy,w:rw,h:th});yy+=th}x+=rw;w-=rw}
    else{const rh=s/w;let xx=x;for(const t of row){const tw=t.a/rh;out.push({...t,x:xx,y,w:tw,h:rh});xx+=tw}y+=rh;h-=rh}
    rest=rest.slice(row.length)}return out}
function render(){if(!S)return;const t=S.tree;
  $("sFiles").textContent=fmtN(t.files);$("sSize").textContent=fmtB(t.bytes);$("sZero").textContent=fmtN(t.zero);$("sInbox").textContent=fmtN(S.inbox);$("sFree").textContent=S.free_gib+" GiB";
  $("sZeroBox").className="stat"+(t.zero?" bad":"");$("sInboxBox").className="stat"+(S.inbox?" warn":"");
  const todo=S.checks.reduce((a,p)=>a+p.todo.filter(x=>x.status==="없음"||x.status==="부족").length,0);$("sTodo").textContent=fmtN(todo);$("sTodoBox").className="stat"+(todo?" warn":"");
  $("sAt").textContent="마지막 갱신 "+S.scanned_at+" · "+S.seconds+"초";
  const age=(Date.now()-new Date(S.scanned_at.replace(" ","T")).getTime())/3600000;
  if(S.note)alertBar(S.note);else if(age>24)alertBar("마지막 갱신이 하루 넘게 지났습니다. 새로고침을 눌러 주세요.");else $("stale").hidden=true;
  if(S.graph_url){$("graph").hidden=false;$("graph").href=S.graph_url}
  drawMap();drawBoard();drawTodo();drawWarn();drawLog()}
function drawMap(){const n=cur(),m=$("map");m.innerHTML="";
  const cr=$("crumbs");cr.innerHTML="";const parts=[S.tree.name,...path];
  parts.forEach((p,i)=>{const a=document.createElement("a");a.textContent=p;a.onclick=()=>{path=path.slice(0,i);drawMap()};cr.append(a);if(i<parts.length-1)cr.append(" › ")});
  const rv=document.createElement("button");rv.textContent="Finder에서 열기";rv.style.marginLeft="auto";rv.onclick=()=>api("/api/reveal?path="+encodeURIComponent(n.path==="."?"":n.path+"/."),true);cr.append(rv);
  const kids=n.children.filter(c=>c.bytes>0||c.files>0);const W=m.clientWidth,H=m.clientHeight;
  if(!kids.length){m.innerHTML='<p class="muted" style="padding:14px">하위 폴더가 없습니다(또는 지도 깊이 끝). 파일 '+fmtN(n.files)+'개.</p>'}
  squarify(kids.map((c,i)=>({c,v:Math.max(c.bytes,1),i})),0,0,W,H).forEach(r=>{const d=document.createElement("div");d.className="tile";d.tabIndex=0;d.setAttribute("role","listitem");
    Object.assign(d.style,{left:r.x+"px",top:r.y+"px",width:r.w+"px",height:r.h+"px",background:COLORS[r.i%COLORS.length]});
    d.innerHTML=(r.w>60&&r.h>34)?`<b>${esc(r.c.name)}</b><small>${fmtN(r.c.files)}개 · ${fmtB(r.c.bytes)}</small>${r.c.zero?`<br><span class="z">0바이트 ${r.c.zero}</span>`:""}`:"";
    d.title=`${r.c.name}\n파일 ${fmtN(r.c.files)}개 · ${fmtB(r.c.bytes)}${r.c.zero?"\n0바이트 "+r.c.zero:""}`;
    const go=()=>{if(r.c.children.length){path.push(r.c.name);drawMap()}else{api("/api/reveal?path="+encodeURIComponent(r.c.path+"/."),true)}};
    d.onclick=go;d.onkeydown=e=>{if(e.key==="Enter")go()};m.append(d)});
  const direct=n.files-n.children.reduce((a,c)=>a+c.files,0);$("here").textContent=`이 폴더: 파일 ${fmtN(n.files)}개 · ${fmtB(n.bytes)} (바로 아래 파일 ${fmtN(Math.max(direct,0))}개)`}
function drawBoard(){const b=$("board");if(!S.checks.length)return;b.innerHTML="";
  S.checks.forEach(p=>{const d=document.createElement("div");d.className="prog";
    d.innerHTML=`<h3>${esc(p.title.replace(/ 문서세트 완결성 검사.*$/,""))}</h3><div class="chips">${p.folders.map(f=>`<span class="chip ${f.missing?"miss":"ok"}" title="${esc(f.folder)}">${esc(f.folder.replace(/_/g," "))} ${f.missing?"누락 "+f.missing:"완결"}</span>`).join("")}</div><div class="muted">검사 ${esc(p.updated)}</div>`;b.append(d)})}
function drawTodo(){const t=$("todo");const rows=S.checks.flatMap(p=>p.todo.filter(x=>x.status==="없음"||x.status==="부족").map(x=>({...x})));
  if(!rows.length){t.innerHTML='<p class="muted">없음</p>';return}
  const by={};rows.forEach(r=>(by[r.folder]=by[r.folder]||[]).push(r));
  t.innerHTML=Object.entries(by).map(([f,rs])=>`<div class="muted" style="margin-top:6px">${esc(f.replace(/_/g," "))}</div><ul>${rs.map(r=>`<li>${esc(r.item)}</li>`).join("")}</ul>`).join("")}
function drawWarn(){const w=$("warn");const items=[];
  if(S.zeros.length)items.push(`<li>0바이트 파일 ${S.zeros.length}개: ${S.zeros.slice(0,5).map(esc).join(", ")}</li>`);
  if(S.inbox)items.push(`<li>INBOX에 분류 대기 ${fmtN(S.inbox)}개</li>`);
  if(S.free_gib<8)items.push(`<li>디스크 여유가 ${S.free_gib} GiB로 기준(8 GiB)보다 적습니다</li>`);
  const chk=S.checks.flatMap(p=>p.todo.filter(x=>x.status!=="없음"&&x.status!=="부족"));if(chk.length)items.push(`<li>확인 필요 ${chk.length}건 (원본만 있거나 사람이 봐야 하는 것)</li>`);
  w.innerHTML=items.length?`<ul>${items.join("")}</ul>`:'<p class="muted">없음</p>'}
function drawLog(){const l=$("log");if(!S.log.length)return;
  l.innerHTML=`<table>${S.log.map(r=>`<tr><td style="white-space:nowrap">${esc(r.time.replace("T"," "))}</td><td><span class="act">${esc(r.action)}</span></td><td>${esc((r.dst||r.src).split("/").slice(-2).join("/"))}</td><td class="muted">${esc(r.reason.slice(0,80))}</td></tr>`).join("")}</table>`}
$("refresh").onclick=refresh;addEventListener("resize",()=>S&&drawMap());load();
</script></body></html>"""

def main():
    ap = argparse.ArgumentParser(description="파일정리 관제탑(보기 전용 로컬 대시보드)")
    ap.add_argument("--root", required=True); ap.add_argument("--log"); ap.add_argument("--checks")
    ap.add_argument("--refresh-cmd", help="새로고침 때 먼저 실행할 읽기 전용 점검 명령"); ap.add_argument("--graph-url")
    ap.add_argument("--port", type=int, default=8765); ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not a.log:
        g = os.path.join(a.root, "_정리로그", "moves_v2.csv"); a.log = g if os.path.exists(g) else None
    tw = Tower(a); srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(tw, a.port))
    url = f"http://localhost:{a.port}/"; print(f"관제탑: {url}  (이 맥에서만 열림, 끄려면 Ctrl+C)", flush=True)
    if not a.no_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
