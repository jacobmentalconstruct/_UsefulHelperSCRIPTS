from __future__ import annotations
import argparse, http.server, json, mimetypes, os, socket, socketserver, sys, threading, time, webbrowser, hashlib, ast
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

try:
    import tkinter as tk
    import tkinter.filedialog as fd
except Exception:
    tk = None
    fd = None

# ------------------------------ Utilities ------------------------------ #
class QuietTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

# ------------------------------ JSONL Report Builder (From app_OG.py) ------------------------------ #

def build_project_codebase_log(root: Path, max_bytes: int = 0, include_binaries: bool = False) -> str:
    """
    Assemble a JSONL stream (as a single string) with:
      - meta
      - file_tree section (dir/file entries)
      - files section (per-file headers + content)
    """
    lines = []
    lines.append(_jsonl({
        "type": "meta",
        "root": str(root),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "format": "jsonl",
        "sections": ["file_tree","files"],
    }))

    # file tree
    lines.append(_jsonl({"type": "section", "name": "file_tree"}))
    for p in _iter_all_paths(root):
        lines.append(_jsonl({
            "type": "dir" if p.is_dir() else "file",
            "path": _rel(root, p),
        }))

    # files
    lines.append(_jsonl({"type": "section", "name": "files"}))
    for p in _iter_all_paths(root):
        if p.is_dir():
            continue
        rel = _rel(root, p)
        lang = _guess_lang(p)
        try:
            raw = p.read_bytes()
        except Exception as e:
            lines.append(_jsonl({"type": "file_error", "path": rel, "error": str(e)}))
            continue

        if lang == "binary" and not include_binaries:
            try:
                st = p.stat()
                lines.append(_jsonl({
                    "type": "file_header",
                    "path": rel,
                    "size": st.st_size,
                    "sha256": _sha256_bytes(raw),
                    "language": lang,
                    "skipped": "binary"
                }))
            except Exception:
                lines.append(_jsonl({"type": "file_header", "path": rel, "language": lang, "skipped": "binary"}))
            continue

        text = raw.decode("utf-8", errors="replace")
        truncated = False
        if max_bytes and len(text.encode("utf-8")) > max_bytes:
            # rough truncation by characters (OK for logs)
            text = text[:max_bytes]
            truncated = True

        try:
            st = p.stat()
            size = st.st_size
        except Exception:
            size = len(raw)

        lines.append(_jsonl({
            "type": "file",
            "path": rel,
            "size": size,
            "sha256": _sha256_bytes(raw),
            "language": lang,
            "truncated": truncated,
            "content": text
        }))

    return "".join(lines)


def build_ast_tree_log(root: Path) -> str:
    """
    Assemble a JSONL stream (as a single string) for *.py files:
      - meta
      - ast_file header per file
      - ast_node records (flat walk)
    """
    lines = []
    lines.append(_jsonl({
        "type": "meta",
        "root": str(root),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "format": "jsonl",
        "scope": "*.py only",
    }))

    for p in _iter_all_paths(root):
        if p.is_dir() or p.suffix != ".py":
            continue
        rel = _rel(root, p)
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            lines.append(_jsonl({"type": "ast_error", "path": rel, "error": str(e)}))
            continue

        lines.append(_jsonl({"type": "ast_file", "path": rel}))
        for item in _iter_ast_nodes(src, rel):
            lines.append(_jsonl(item))

    return "".join(lines)


def _iter_all_paths(root: Path):
    for p in sorted(root.rglob("*")):
        # skip junky dirs if you like:
        if any(part in {".git", "__pycache__", ".venv", "venv", "node_modules"} for part in p.parts):
            continue
        yield p

def _rel(root: Path, p: Path) -> str:
    return str(p.relative_to(root)).replace("\\", "/")

def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def _guess_lang(path: Path) -> str:
    mt = (mimetypes.guess_type(str(path))[0] or "")
    if path.suffix == ".py": return "python"
    if path.suffix in {".js", ".mjs", ".cjs"}: return "javascript"
    if path.suffix == ".ts": return "typescript"
    if path.suffix in {".json"}: return "json"
    if path.suffix in {".css"}: return "css"
    if path.suffix in {".html", ".htm"}: return "html"
    if mt.startswith("text/"): return "text"
    return "binary"

def _iter_ast_nodes(py_source: str, relpath: str):
    try:
        tree = ast.parse(py_source)
    except Exception as e:
        yield {"type": "ast_error", "path": relpath, "error": str(e)}
        return
    for node in ast.walk(tree):
        # core shape that’s useful yet compact
        item = {
            "type": "ast_node",
            "path": relpath,
            "node": type(node).__name__,
        }
        # common fields (best-effort)
        for attr in ("name", "id", "arg", "attr"):
            if hasattr(node, attr):
                item["name"] = getattr(node, attr)
                break
        if hasattr(node, "lineno"):
            item["lineno"] = getattr(node, "lineno")
        if hasattr(node, "col_offset"):
            item["col"] = getattr(node, "col_offset")
        if hasattr(node, "end_lineno"):
            item["end_lineno"] = getattr(node, "end_lineno")
        yield item

def _jsonl(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"

# ------------------------------ Built-in HTML (blue theme renderer) ------------------------------ #
DEFAULT_INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Temp Server Maker</title>
  <style>
    :root { --bg:#0b1220; --panel:#0f1b31; --panel-2:#132240; --text:#e8f1ff; --muted:#a7c1ff; --accent:#4da3ff; --accent-2:#72b6ff; --border:#21406e; --chip:#0d1a33; }
    html,body{height:100%}
    body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Arial}
    .topbar{display:flex;align-items:center;gap:.5rem;padding:.75rem 1rem;background:linear-gradient(180deg,#0e1a31,#0a1325);position:sticky;top:0;z-index:2;border-bottom:1px solid var(--border)}
    .title{font-weight:700;letter-spacing:.3px;margin-right:auto}
    .btn{background:var(--panel);color:var(--text);border:1px solid var(--border);padding:.45rem .7rem;border-radius:10px;cursor:pointer}
    .btn:hover{background:var(--panel-2);border-color:var(--accent)}
    .btn.primary{background:#12407e;border-color:#2f6eb9}
    .btn.primary:hover{background:#15519f}
    .grid{display:grid;grid-template-columns:320px 1fr;height:calc(100vh - 52px)}
    .pane{overflow:auto}
    .left{background:var(--panel);border-right:1px solid var(--border)}
    .right{background:var(--panel-2)}
    .section{padding:.75rem 1rem;border-bottom:1px solid var(--border)}
    .meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.35rem .75rem;font-size:13px;color:var(--muted)}
    .chip{display:inline-block;background:var(--chip);border:1px solid var(--border);border-radius:999px;padding:.15rem .5rem;margin-right:.35rem}
    .tree{padding:.5rem 0 1rem 0}
    .node{user-select:none}
    .entry{display:flex;align-items:center;gap:.5rem;padding:.25rem .5rem;cursor:pointer;border-radius:8px}
    .entry:hover{background:rgba(114,182,255,.08)}
    .twist{width:1rem;text-align:center;font-weight:700;color:var(--accent-2)}
    .folder{color:var(--accent)}
    .file{color:#cbd9f3}
    .viewer{padding:1rem 1.25rem}
    .path{font-weight:700;margin-bottom:.25rem;color:#d9e6ff}
    .meta-line{font-size:12px;color:var(--muted);margin-bottom:.75rem}
    pre{white-space:pre-wrap;word-wrap:break-word;background:#0a1529;border:1px solid var(--border);border-radius:10px;padding:.75rem}
  </style>
</head>
<body>
  <div class=\"topbar\"> <div class=\"title\">Temp Server Maker</div>
    <button class=\"btn\" id=\"btn-refresh\">Refresh</button>
    <a class=\"btn\" id=\"btn-export\" href=\"#\">Export JSONL</a>
    <button class=\"btn\" id=\"btn-copy\">Copy Snapshot</button>
    <button class=\"btn primary\" id=\"btn-open\">Open in New Tab</button>
  </div>
  <div class=\"grid\">
    <div class=\"pane left\">
      <div class=\"section\" id=\"meta\"></div>
      <div class=\"section\"><div class=\"chip\" id=\"count\"></div><div class=\"chip\" id=\"bytes\"></div></div>
      <div class=\"pane tree\" id=\"tree\"></div>
    </div>
    <div class=\"pane right viewer\" id=\"viewer\"><div style=\"opacity:.7\">Select a file to preview its contents.</div></div>
  </div>
  <script id=\"meta-json\" type=\"application/json\"></script>
  <script id=\"files-json\" type=\"application/json\"></script>
  <script>
    function $(id){return document.getElementById(id)}
    function jget(id){const el=$(id);try{return JSON.parse(el.textContent||'{}')}catch{return{}}}
    const meta=jget('meta-json');
    const files=jget('files-json');
    const metaEl=$('meta');
    metaEl.innerHTML=`<div class=meta><div><b>Root:</b> ${meta.root||'?'} </div><div><b>Generated:</b> ${meta.generated_at||'?'}</div></div>`;
    $('count').textContent = `files: ${meta.count ?? meta.file_count ?? (files?.length || 0)}`;
    $('bytes').textContent = `bytes: ${new Intl.NumberFormat().format(meta.total_bytes || 0)}`;

    const exportUrl='/__api__/report/project-codebase-log?max_bytes=0';
    $('btn-export').href=exportUrl;
    $('btn-open').onclick=()=>window.open('/', '_blank');
    $('btn-refresh').onclick=async()=>{try{await fetch('/__api__/refresh',{method:'POST'});location.reload()}catch{location.reload()}}
    $('btn-copy').onclick=async()=>{try{const r=await fetch(exportUrl);const t=await r.text();await navigator.clipboard.writeText(t);$('btn-copy').textContent='Copied!';setTimeout(()=>$('btn-copy').textContent='Copy Snapshot',1200)}catch(e){alert('Copy failed: '+e)}}

    function buildTree(paths){const root={name:'',children:new Map(),files:[]};for(const f of paths){const parts=f.path.split('/');let cur=root;for(let i=0;i<parts.length-1;i++){const seg=parts[i];if(!cur.children.has(seg))cur.children.set(seg,{name:seg,children:new Map(),files:[]});cur=cur.children.get(seg)}cur.files.push(f)}return root}
    function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
    function renderTree(container,node,depth=0){for(const [name,child] of [...node.children.entries()].sort()){const row=el('div','node');const entry=el('div','entry');const twist=el('div','twist','▸');const label=el('div','folder',name);entry.style.paddingLeft=(depth*12+6)+'px';entry.append(twist,label);const body=el('div');body.style.display='none';entry.onclick=()=>{const open=body.style.display==='none';body.style.display=open?'block':'none';twist.textContent=open?'▾':'▸'};row.append(entry,body);container.append(row);renderTree(body,child,depth+1)}for(const f of node.files.sort((a,b)=>a.path.localeCompare(b.path))){const row=el('div','node');const entry=el('div','entry');entry.style.paddingLeft=(depth*12+24)+'px';const dot=el('div','twist','•');const label=el('div','file',f.path.split('/').pop());entry.append(dot,label);entry.onclick=()=>showFile(f);row.append(entry);container.append(row)}}

    async function loadChunk(relPath, offset){const v=$('viewer');const limit=200000;const res=await fetch(`/__api__/file?path=${encodeURIComponent(relPath)}&offset=${offset}&limit=${limit}`);const j=await res.json();if(!j.ok){v.append(el('div',null,j.error||'Preview failed.'));return}if(offset===0){v.innerHTML='';v.append(el('div','path',j.path));v.append(el('div','meta-line',`size=${j.size} mime=${j.mime||'?'} (${j.chunk_start}-${j.chunk_end})`))}if(typeof j.text==='string'){const pre=el('pre');pre.textContent=j.text;v.append(pre)}else{v.append(el('div',null,'Binary file — no text preview.'))}if(j.more){const btn=el('button','btn','Load more…');btn.onclick=()=>loadChunk(j.path,j.chunk_end);v.append(btn)}}

    function showFile(f){const v=$('viewer');v.innerHTML='';v.append(el('div','path',f.path));v.append(el('div','meta-line',`size=${f.size} mime=${f.mime||'?'}${f.truncated?' (truncated)':''}`));if(typeof f.text==='string'){v.append(el('pre',null,f.text));if(f.truncated){const loadMore=el('button','btn','Load more…');loadMore.onclick=()=>{loadChunk(f.path,(f.text||'').length)};v.append(loadMore)}}else{loadChunk(f.path,0)}}

    const treeRoot=buildTree(files||[]);renderTree($('tree'),treeRoot);
  </script>
</body>
</html>"""

# ------------------------------ Core Application ------------------------- #
class App:
    MAX_TEXT_BYTES = 400_000  # inline preview cap

    def __init__(self, directory: Path, host: str, port: int,
                 open_browser: bool, keep_index: bool,
                 headless: bool, write_report: bool) -> None:
        self.root_dir = Path(directory).resolve()
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.keep_index = keep_index  # if True and no index.html, write DEFAULT_INDEX_HTML to disk
        self.headless = headless
        self.write_report_flag = write_report
        self.httpd: QuietTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.url: str = ""
        self.template_path = self.root_dir / "index.html"
        self.logs_dir = self.root_dir / "_logs" / "_temp-server"
        ensure_dir(self.logs_dir)
        self.log_path = self.logs_dir / f"server_{int(time.time())}.log"
        self.report_path = self.logs_dir / "ai_report.txt"

    def set_root_dir(self, new_root: Path) -> None:
        new_root = Path(new_root).resolve()
        if not new_root.is_dir():
            raise FileNotFoundError(f"directory does not exist: {new_root}")
        self.root_dir = new_root
        self.template_path = self.root_dir / "index.html"
        self.logs_dir = self.root_dir / "_logs" / "_temp-server"
        ensure_dir(self.logs_dir)
        self.log_path = self.logs_dir / f"server_{int(time.time())}.log"
        self.report_path = self.logs_dir / "ai_report.txt"
        self._log(f"Root changed to: {self.root_dir}")

    def _file_record(self, p: Path) -> dict:
        rel = str(p.relative_to(self.root_dir))
        size = p.stat().st_size
        mtype, _ = mimetypes.guess_type(rel)
        mtype = mtype or "application/octet-stream"
        rec: dict[str, object] = {"path": rel, "size": size, "mime": mtype}
        # Text sniff with bounded preview; no reliance on mimetype
        try:
            with p.open('rb') as f:
                chunk = f.read(self.MAX_TEXT_BYTES + 1)
            is_text_like = b"\x00" not in chunk[:4096]
            if is_text_like:
                preview = chunk[: self.MAX_TEXT_BYTES]
                try:
                    rec["text"] = preview.decode("utf-8")
                except UnicodeDecodeError:
                    rec["text"] = preview.decode("latin-1", errors="replace")
                if size > self.MAX_TEXT_BYTES or len(chunk) > self.MAX_TEXT_BYTES:
                    rec["truncated"] = True
            else:
                rec["binary"] = True
        except Exception:
            rec["binary"] = True
        return rec

    def _parse_ast(self, p: Path) -> list:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            nodes = []
            for node in ast.walk(tree):
                nodes.append({
                    "type": node.__class__.__name__,
                    "lineno": getattr(node, "lineno", None),
                    "col_offset": getattr(node, "col_offset", None),
                    "end_lineno": getattr(node, "end_lineno", None),
                    "end_col_offset": getattr(node, "end_col_offset", None),
                    "fields": {field: getattr(node, field, None).__class__.__name__ for field in node._fields}
                })
            return nodes
        except Exception as e:
            return [{"error": str(e)}]

    def _gather_files(self) -> list[Path]:
        files: list[Path] = []
        for p in self.root_dir.rglob("*"):
            if not p.is_file():
                continue
            if any(part.startswith('.') for part in p.parts) or self.logs_dir in p.parents or p.name == "app.py" or p.name == "app_merged.py":
                continue
            files.append(p)
        files.sort()
        return files

    def _load_template(self) -> str:
        if self.template_path.exists():
            return self.template_path.read_text(encoding="utf-8")
        # Fallback to built-in
        self._log("index.html not found in root — serving built-in template.")
        if self.keep_index:
            try:
                self.template_path.write_text(DEFAULT_INDEX_HTML, encoding="utf-8")
                self._log("Wrote built-in template to disk because --keep-index is set.")
            except Exception as e:
                self._log(f"[warn] Failed to write built-in template: {e}")
        return DEFAULT_INDEX_HTML

    def generate_populated_html(self) -> str:
        files = [self._file_record(p) for p in self._gather_files()]
        meta = {"generated_at": now_iso(), "root": str(self.root_dir), "count": len(files), "total_bytes": sum(f.get("size", 0) for f in files)}
        def safe_json(obj: object) -> str:
            return json.dumps(obj, ensure_ascii=False).replace("</", "<\/").replace("<\\/", "<\\/")
        template_content = self._load_template()
        populated_html = template_content.replace('<script id="meta-json" type="application/json"></script>', f'<script id="meta-json" type="application/json">{safe_json(meta)}</script>')
        populated_html = populated_html.replace('<script id="files-json" type="application/json"></script>', f'<script id="files-json" type="application/json">{safe_json(files)}</script>')
        return populated_html

    def write_ai_report(self) -> None:
        if not self.write_report_flag:
            return
        files = [self._file_record(p) for p in self._gather_files()]
        meta = {"generated_at": now_iso(), "root": str(self.root_dir), "count": len(files), "total_bytes": sum(f.get("size", 0) for f in files)}
        lines = [json.dumps(meta, ensure_ascii=False)]
        for f in files:
            lines += ["\n" + "=" * 80, f"FILE: {f['path']}", "-" * 80, f.get("text", "[binary or omitted]") if isinstance(f.get("text"), str) else "[binary or omitted]"]
        self.report_path.write_text("\n".join(lines), encoding="utf-8")

    def refresh(self) -> None:
        self.write_ai_report()
        self._log("Refreshed AI report")

    # --------------------------- Server ----------------------------- #
    def _make_server(self) -> tuple[QuietTCPServer, str]:
        # Change to root_dir for SimpleHTTPRequestHandler to find files
        try:
            os.chdir(self.root_dir)
        except Exception as e:
            self._log(f"[error] Failed to change directory to {self.root_dir}: {e}")
            # Don't crash, but log the error.
        
        port = self.port if self.port != 0 else pick_free_port(self.host)
        app_ref = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            # Use the 'directory' attribute for SimpleHTTPRequestHandler
            def __init__(self, *args, **kwargs):
                kwargs['directory'] = str(app_ref.root_dir)
                super().__init__(*args, **kwargs)

            def _set_cors(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')

            def _send_json(self, obj: object, code: int = 200):
                data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self._set_cors()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_text(self, text: str, code: int = 200, ctype: str = 'text/plain; charset=utf-8'):
                b = text.encode('utf-8', errors='replace')
                self.send_response(code)
                self._set_cors()
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_OPTIONS(self):
                self.send_response(204)
                self._set_cors()
                self.end_headers()

            def do_GET(self):
                if self.path.startswith('/__api__/status'):
                    tpl_exists = app_ref.template_path.exists()
                    return self._send_json({
                        "ok": True,
                        "root": str(app_ref.root_dir),
                        "host": app_ref.host,
                        "port": app_ref.port,
                        "url": app_ref.url,
                        "template_path": str(app_ref.template_path),
                        "template_exists": tpl_exists,
                        "keep_index": app_ref.keep_index,
                    })

                if self.path.startswith('/__api__/'):
                    # Project Codebase Log (JSONL) - From app_OG.py
                    if self.path.startswith('/__api__/report/project-codebase-log'):
                        q = parse_qs(urlparse(self.path).query)
                        max_bytes = int(q.get("max_bytes", ["0"])[0] or "0")
                        include_binaries = q.get("include_binaries", ["0"])[0] == "1"

                        text = build_project_codebase_log(app_ref.root_dir.resolve(), max_bytes=max_bytes, include_binaries=include_binaries)
                        return self._send_text(text, 200, 'text/plain; charset=utf-8')

                    # AST Tree Log (JSONL) - From app_OG.py
                    if self.path.startswith('/__api__/report/ast-tree-log'):
                        text = build_ast_tree_log(app_ref.root_dir.resolve())
                        return self._send_text(text, 200, 'text/plain; charset=utf-8')

                    # AST Endpoint - From app_OG.py
                    if self.path.startswith('/__api__/ast'):
                        q = parse_qs(urlparse(self.path).query)
                        raw = q.get("path", [""])[0]
                        rel = unquote(raw)

                        # force relative path under the served root
                        abs_p = (app_ref.root_dir / rel).resolve()
                        root = app_ref.root_dir.resolve()
                        try:
                            abs_p.relative_to(root)
                        except ValueError:
                             return self._send_json({"error": "path outside root"}, 400)

                        if abs_p.suffix != ".py":
                            return self._send_json({"error": "Only .py files are supported"}, 400)
                        if not abs_p.is_file():
                            return self._send_json({"error": "File not found"}, 404)

                        ast_data = app_ref._parse_ast(abs_p)
                        return self._send_json(ast_data)

                    # Chunked File Loader - From app_newUI.py
                    if self.path.startswith('/__api__/file'):
                        q = parse_qs(urlparse(self.path).query)
                        rel = (q.get('path', [''])[0] or '').strip()
                        try:
                            offset = int(q.get('offset', ['0'])[0] or '0')
                            limit = int(q.get('limit', [str(app_ref.MAX_TEXT_BYTES)])[0])
                            if limit <= 0 or limit > 2_000_000:
                                limit = app_ref.MAX_TEXT_BYTES
                        except Exception:
                            offset, limit = 0, app_ref.MAX_TEXT_BYTES
                        if not rel:
                            return self._send_json({"ok": False, "error": "missing path"}, 400)
                        abs_path = (app_ref.root_dir / rel).resolve()
                        try:
                            abs_path.relative_to(app_ref.root_dir)
                        except Exception:
                            return self._send_json({"ok": False, "error": "path outside root"}, 400)
                        if not abs_path.exists() or not abs_path.is_file():
                            return self._send_json({"ok": False, "error": "not a file"}, 404)
                        total = abs_path.stat().st_size
                        mtype, _ = mimetypes.guess_type(abs_path.name)
                        mtype = mtype or 'application/octet-stream'
                        with abs_path.open('rb') as f:
                            f.seek(max(0, offset))
                            chunk = f.read(max(0, limit))
                        is_text_like = b"\x00" not in chunk[:4096]
                        payload = {
                            "ok": True,
                            "path": rel,
                            "size": total,
                            "mime": mtype,
                            "chunk_start": max(0, offset),
                            "chunk_end": max(0, offset) + len(chunk),
                            "more": (max(0, offset) + len(chunk)) < total,
                        }
                        if is_text_like:
                            try:
                                payload["text"] = chunk.decode('utf-8')
                            except UnicodeDecodeError:
                                payload["text"] = chunk.decode('latin-1', errors='replace')
                        return self._send_json(payload)
                    
                    # Fallback for other /__api__/ calls
                    return self._send_json({"error": "API endpoint not found"}, 404)

                if self.path == '/' or self.path == '/index.html':
                    html_content = app_ref.generate_populated_html()
                    return self._send_text(html_content, ctype='text/html; charset=utf-8')

                # Use SimpleHTTPRequestHandler's default file serving
                # (which now correctly uses the 'directory' kwarg)
                return super().do_GET()

            def do_POST(self):
                if self.path.startswith('/__api__/refresh'):
                    app_ref.refresh()
                    return self._send_json({"ok": True, "url": app_ref.url, "root": str(app_ref.root_dir)})
                if self.path.startswith('/__api__/shutdown'):
                    self._send_json({"ok": True})
                    threading.Thread(target=app_ref.shutdown, daemon=True).start()
                    return
                return super().do_POST()

        httpd = QuietTCPServer((self.host, port), Handler)
        url = f"http://{self.host}:{port}/"
        return httpd, url

    def start(self) -> None:
        self.write_ai_report()
        self.httpd, self.url = self._make_server()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self._log(f"Serving {self.root_dir} at {self.url}")
        if self.open_browser:
            webbrowser.open(self.url)

    def shutdown(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread:
            self.thread.join(timeout=1.0)
        self._log("Server stopped")

    def _log(self, msg: str) -> None:
        line = f"[{now_iso()}] {msg}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def run_headless(self) -> int:
        try:
            self.start()
            while self.thread and self.thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n[info] Keyboard interrupt received, shutting down.")
        finally:
            self.shutdown()
        return 0

    def run_gui(self) -> int:
        if tk is None:
            print("[error] Tkinter is not available on this system.")
            return 1
        
        # Store the original CWD
        original_cwd = Path.cwd()
        
        root = tk.Tk()
        root.title("Temp Server Maker")
        status_var = tk.StringVar(value=f"Directory: {self.root_dir}")
        tk.Label(root, textvariable=status_var, anchor='w', padx=10, pady=5).pack(fill='x')

        dir_row = tk.Frame(root, padx=10, pady=5); dir_row.pack(fill='x')
        tk.Label(dir_row, text="Root:", width=6, anchor='w').pack(side='left')
        dir_var = tk.StringVar(value=str(self.root_dir))
        dir_entry = tk.Entry(dir_row, textvariable=dir_var); dir_entry.pack(side='left', fill='x', expand=True, padx=(0,8))
        def choose_dir():
            path = fd.askdirectory(initialdir=dir_var.get() or str(self.root_dir))
            if not path:
                return
            was_running = self.httpd is not None
            if was_running:
                self.shutdown()
            try:
                self.set_root_dir(Path(path))
            except Exception as e:
                status_var.set(f"[error] {e}")
                if was_running: # Try to restart in the old dir
                    try: self.start()
                    except Exception: pass
                return
            dir_var.set(str(self.root_dir))
            status_var.set(f"Directory: {self.root_dir}")
            if was_running:
                try: self.start()
                except Exception as e: status_var.set(f"[error] Restart failed: {e}")
        tk.Button(dir_row, text="Choose Folder…", command=choose_dir).pack(side='left')

        net_row = tk.Frame(root, padx=10, pady=5); net_row.pack(fill='x')
        auto_port_var = tk.BooleanVar(value=(self.port == 0))
        def toggle_port_state():
            if auto_port_var.get(): port_entry.configure(state='disabled')
            else: port_entry.configure(state='normal')
        tk.Checkbutton(net_row, text="Auto port", variable=auto_port_var, command=toggle_port_state).pack(side='left')
        tk.Label(net_row, text="Port:", padx=6).pack(side='left')
        port_var = tk.StringVar(value=str(self.port or 8000))
        port_entry = tk.Entry(net_row, width=8, textvariable=port_var); port_entry.pack(side='left')
        toggle_port_state()

        ctrls = tk.Frame(root, padx=10, pady=5); ctrls.pack(fill='x')
        def start_server():
            try:
                self.port = 0 if auto_port_var.get() else int(port_var.get())
                if not (0 <= self.port <= 65535):
                    raise ValueError("port out of range")
            except Exception:
                status_var.set("[error] Invalid port")
                return
            typed_root = Path(os.path.expanduser(dir_var.get() or "."))
            if typed_root.resolve() != self.root_dir:
                try:
                    self.set_root_dir(typed_root)
                except Exception as e:
                    status_var.set(f"[error] {e}")
                    return
            if self.httpd:
                self.shutdown()
            try:
                self.start()
                status_var.set(f"Server running at {self.url}")
            except Exception as e:
                status_var.set(f"[error] Start failed: {e}")
                
        def stop_server():
            self.shutdown(); status_var.set("Server stopped.")
        def restart_server():
            stop_server(); start_server()
        def open_browser_now():
            if self.httpd and self.url: webbrowser.open(self.url)
            else: status_var.set("Server not running.")
        def quit_app():
            try: self.shutdown()
            finally: root.destroy()
            
        root.protocol("WM_DELETE_WINDOW", quit_app) # Handle window close button
            
        for text_label, cmd in (("Start", start_server),("Stop", stop_server),("Restart", restart_server),("Open", open_browser_now),("Quit", quit_app)):
            tk.Button(ctrls, text=text_label, command=cmd).pack(side='left', padx=(0,6))
        
        try:
            root.mainloop()
        except KeyboardInterrupt:
            print("\n[info] GUI interrupted, shutting down.")
            quit_app()
        finally:
            # Restore original CWD on exit
            try: os.chdir(original_cwd)
            except Exception: pass
            
        return 0

# ------------------------------ CLI ------------------------------ #

def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description='Serve a folder quickly with a minimal UI')
    p.add_argument('-d', '--directory', default='.', help='Directory to serve (default: .)')
    p.add_argument('--host', default='127.0.0.1', help='Host/IP to bind (default: 127.0.0.1)')
    p.add_argument('-p', '--port', type=int, default=8000, help='Port to bind (0 for auto)')
    p.add_argument('--open', dest='open_browser', action='store_true', help='Open browser on start')
    p.add_argument('--no-open', dest='open_browser', action='store_false', help='Do not open browser')
    p.set_defaults(open_browser=True)
    p.add_argument('--no-gui', dest='no_gui', action='store_true', help='Run headless (no Tk)')
    p.add_argument('--keep-index', action='store_true', help='If no index.html exists, write built-in template to disk')
    p.add_argument('--report', action='store_true', help='Also write ai_report.txt to _logs/_temp-server/')
    p.add_argument('--keep-file', action='store_true', help='Keep generated files on exit (deprecated)')
    return p.parse_args(argv)

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    
    # Store CWD at startup
    original_cwd = Path.cwd()
    
    try:
        directory = (Path(__file__).resolve().parent if args.directory == '.' else Path(os.path.expanduser(args.directory)).resolve())
        if not directory.is_dir():
            print(f"[error] directory does not exist: {directory}")
            return 2
        
        app = App(directory=directory, host=args.host, port=args.port, open_browser=args.open_browser, keep_index=args.keep_index, headless=args.no_gui, write_report=args.report)
        
        return app.run_headless() if app.headless else app.run_gui()

    finally:
        # Ensure CWD is restored even on headless exit
        try: os.chdir(original_cwd)
        except Exception: pass


if __name__ == "__main__":
    raise SystemExit(main())