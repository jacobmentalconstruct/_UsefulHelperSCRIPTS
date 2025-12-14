from __future__ import annotations
import argparse, contextlib, http.server, json, mimetypes, os, socket, socketserver, sys, threading, time, webbrowser, ast, hashlib
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

# ---------- helpers ----------
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

# ---------------------------- Core Application ------------------------- #
class App:
    MAX_TEXT_BYTES = 400_000

    def __init__(self, directory: Path, host: str, port: int,
                 open_browser: bool, keep_index: bool,
                 headless: bool, write_report: bool) -> None:
        self.root_dir = Path(directory).resolve()
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.keep_index = keep_index
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

    def _gather_files(self) -> list[Path]:
        files: list[Path] = []
        for p in self.root_dir.rglob("*"):
            if not p.is_file():
                continue
            if any(part.startswith('.') for part in p.parts) or self.logs_dir in p.parents or p.name == "app.py":
                continue
            files.append(p)
        files.sort()
        return files

    def _file_record(self, p: Path) -> dict:
        rel = str(p.relative_to(self.root_dir))
        size = p.stat().st_size
        mtype, _ = mimetypes.guess_type(rel)
        mtype = mtype or "application/octet-stream"
        rec: dict[str, object] = {"path": rel, "size": size, "mime": mtype}
        if (mtype.startswith("text/") or size <= self.MAX_TEXT_BYTES):
            try:
                data = p.read_bytes()
                if b"\x00" not in data[:4096]:
                    rec["text"] = data[:self.MAX_TEXT_BYTES].decode("utf-8", errors="replace")
            except Exception:
                pass
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



    def generate_populated_html(self) -> str:
        if not self.template_path.exists():
            return "<html><body><h1>Error</h1><p>index.html not found in the root directory.</p></body></html>"
        files = [self._file_record(p) for p in self._gather_files()]
        meta = {"generated_at": now_iso(), "root": str(self.root_dir), "file_count": len(files), "total_bytes": sum(f.get("size", 0) for f in files)}
        def safe_json(obj: object) -> str:
            return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
        template_content = self.template_path.read_text(encoding="utf-8")
        populated_html = template_content.replace('<script id="meta-json" type="application/json"></script>', f'<script id="meta-json" type="application/json">{safe_json(meta)}</script>')
        populated_html = populated_html.replace('<script id="files-json" type="application/json"></script>', f'<script id="files-json" type="application/json">{safe_json(files)}</script>')
        return populated_html

    def write_ai_report(self) -> None:
        if not self.write_report_flag:
            return
        files = [self._file_record(p) for p in self._gather_files()]
        meta = {"generated_at": now_iso(), "root": str(self.root_dir), "file_count": len(files), "total_bytes": sum(f.get("size", 0) for f in files)}
        lines = [json.dumps(meta, ensure_ascii=False)]
        for f in files:
            lines += ["\n" + "=" * 80, f"FILE: {f['path']}", "-" * 80, f.get("text") if isinstance(f.get("text"), str) else "[binary or omitted]"]
        self.report_path.write_text("\n".join(lines), encoding="utf-8")

    def refresh(self) -> None:
        self.write_ai_report()
        self._log("Refreshed AI report")

    def _make_server(self) -> tuple[QuietTCPServer, str]:
        os.chdir(self.root_dir)
        port = self.port if self.port != 0 else pick_free_port(self.host)
        app_ref = self

        class Handler(http.server.SimpleHTTPRequestHandler):
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
                b = text.encode('utf-8')
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

            def do_POST(self):
                if self.path.startswith('/__api__/refresh'):
                    app_ref.refresh()
                    return self._send_json({"ok": True, "url": app_ref.url, "root": str(app_ref.root_dir)})
                if self.path.startswith('/__api__/shutdown'):
                    self._send_json({"ok": True})
                    threading.Thread(target=app_ref.shutdown, daemon=True).start()
                    return
                return super().do_POST()

            def do_GET(self):
                if self.path.startswith('/__api__/'):
                    # Project Codebase Log (JSONL)
                    if self.path.startswith('/__api__/report/project-codebase-log'):
                        # parse query
                        q = parse_qs(urlparse(self.path).query)
                        max_bytes = int(q.get("max_bytes", ["0"])[0] or "0")
                        include_binaries = q.get("include_binaries", ["0"])[0] == "1"

                        text = build_project_codebase_log(app_ref.root_dir.resolve(), max_bytes=max_bytes, include_binaries=include_binaries)
                        # served as plain text; client names the file
                        return self._send_text(text, 200, 'text/plain; charset=utf-8')

                    # AST Tree Log (JSONL)
                    if self.path.startswith('/__api__/report/ast-tree-log'):
                        text = build_ast_tree_log(app_ref.root_dir.resolve())
                        return self._send_text(text, 200, 'text/plain; charset=utf-8')

                    # AST Endpoint
                    if self.path.startswith('/__api__/ast'):
                        q = parse_qs(urlparse(self.path).query)
                        raw = q.get("path", [""])[0]
                        rel = unquote(raw)

                        # force relative path under the served root
                        abs_p = (app_ref.root_dir / rel).resolve()
                        root = app_ref.root_dir.resolve()
                        if not str(abs_p).startswith(str(root) + os.sep) and abs_p != root:
                            return self._send_json({"error": "path outside root"}, 400)

                        if abs_p.suffix != ".py":
                            return self._send_json({"error": "Only .py files are supported"}, 400)
                        if not abs_p.is_file():
                            return self._send_json({"error": "File not found"}, 404)

                        ast_data = app_ref._parse_ast(abs_p)
                        return self._send_json(ast_data)


                    if self.path == '/__api__/ping':
                        return self._send_json({"ok": True, "time": now_iso()})
                    if self.path == '/__api__/meta':
                        files = [app_ref._file_record(p) for p in app_ref._gather_files()]
                        meta = {"generated_at": now_iso(), "root": str(app_ref.root_dir), "file_count": len(files), "total_bytes": sum(f.get('size', 0) for f in files)}
                        return self._send_json(meta)
                    if self.path == '/__api__/files':
                        files = [app_ref._file_record(p) for p in app_ref._gather_files()]
                        return self._send_json(files)
                    return self._send_json({"error": "not found"}, 404)

                if self.path == '/' or self.path == '/index.html':
                    html_content = app_ref.generate_populated_html()
                    return self._send_text(html_content, ctype='text/html; charset=utf-8')

                return super().do_GET()

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
        self._log("Server stopped")

    def _log(self, msg: str) -> None:
        line = f"[{now_iso()}] {msg}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def run_headless(self) -> int:
        self.start()
        print(f"[info] Serving {self.root_dir} at {self.url}")
        try:
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
        root = tk.Tk()
        root.title("Temp Server Maker")
        status_var = tk.StringVar(value=f"Directory: {self.root_dir}")
        tk.Label(root, textvariable=status_var, anchor='w', padx=10, pady=5).pack(fill='x')
        ctrls = tk.Frame(root, padx=10, pady=5)
        ctrls.pack(fill='x')
        def start_server():
            print("Server is starting...")
            self.start()
            status_var.set(f"Server running at {self.url}")
        def stop_server():
            self.shutdown()
            status_var.set("Server stopped.")
        for text, cmd in (("Start", start_server), ("Stop", stop_server), ("Open", lambda: webbrowser.open(self.url)), ("Quit", root.destroy)):
            tk.Button(ctrls, text=text, command=cmd).pack(side='left')
        root.mainloop()
        return 0

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Temp Server Maker — simple HTTP server with rich HTML index")
    p.add_argument('-d', '--directory', default='.', help='Directory to serve (default: .)')
    p.add_argument('--host', default='127.0.0.1', help='Host/IP to bind (default: 127.0.0.1)')
    p.add_argument('-p', '--port', type=int, default=8000, help='Port (0 = random; default: 8000)')
    p.add_argument('--open', action='store_true', help='Open default browser to the server URL')
    p.add_argument('--no-gui', action='store_true', help='Run headless (no Tk window)')
    p.add_argument('--report', action='store_true', help='Also write ai_report.txt to _logs/_temp-server/')
    p.add_argument('--keep-file', action='store_true', help='Keep generated files on exit (deprecated)')
    return p.parse_args(argv)

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    directory = (Path(__file__).resolve().parent if args.directory == '.' else Path(os.path.expanduser(args.directory)).resolve())
    if not directory.is_dir():
        print(f"[error] directory does not exist: {directory}")
        return 2
    app = App(directory=directory, host=args.host, port=args.port, open_browser=args.open, headless=args.no_gui, write_report=args.report, keep_index=args.keep_file)
    return app.run_headless() if app.headless else app.run_gui()

if __name__ == "__main__":
    raise SystemExit(main())