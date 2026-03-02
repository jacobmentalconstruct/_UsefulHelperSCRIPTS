import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import os
import ast
import hashlib
import threading
import datetime
import json
import sys

# Standard library modules to exclude from requirements.txt
STDLIB_MODULES = {'os', 'sys', 'json', 'hashlib', 'ast', 'argparse', 'typing', 'dataclasses', 're', 'math', 'datetime'}

PYPI_MAPPING = {
    'sklearn': 'scikit-learn',
    'rdflib': 'rdflib',
    'networkx': 'networkx',
    'numpy': 'numpy',
    'gensim': 'gensim',
    'joblib': 'joblib'
}

class MicroStamperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python API Mesh Factory (Orchestration Edition)")
        self.root.geometry("900x650")
        self.root.configure(bg="#121212")

        self.selected_file = None
        self.output_dir = "generated_mesh"
        self.services_manifest = [] # Tracks data for orchestration/docker-compose
        self.current_port = 8000
        
        self.setup_ui()

    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg="#121212")
        header_frame.pack(fill="x", pady=15)
        
        header = tk.Label(header_frame, text="NEURAL CARTRIDGE: SYSTEM COMPILER", 
                         fg="#00ff41", bg="#121212", font=("Consolas", 18, "bold"))
        header.pack()

        sub_header = tk.Label(header_frame, text="Atomizes Python -> Microservices + Orchestration Layer + Docker", 
                             fg="#888888", bg="#121212", font=("Consolas", 10))
        sub_header.pack()

        file_frame = tk.Frame(self.root, bg="#1e1e1e", padx=15, pady=15)
        file_frame.pack(fill="x", padx=30, pady=10)

        self.file_label = tk.Label(file_frame, text="Blueprint Path: [No file selected]", 
                                  fg="#00ff41", bg="#1e1e1e", font=("Consolas", 10), wraplength=600, justify="left")
        self.file_label.pack(side="left")

        btn_browse = tk.Button(file_frame, text="LOAD BLUEPRINT", command=self.browse_file,
                              bg="#333333", fg="white", font=("Consolas", 9, "bold"), 
                              relief="flat", padx=10)
        btn_browse.pack(side="right")

        log_frame = tk.Frame(self.root, bg="#121212")
        log_frame.pack(fill="both", expand=True, padx=30)

        self.log_viewer = scrolledtext.ScrolledText(log_frame, bg="#080808", fg="#00ff41", 
                                                   font=("Consolas", 10), insertbackground="white",
                                                   borderwidth=0, highlightthickness=1, highlightbackground="#333")
        self.log_viewer.pack(fill="both", expand=True)

        ctrl_frame = tk.Frame(self.root, bg="#121212", pady=20)
        ctrl_frame.pack(fill="x", padx=30)

        self.btn_run = tk.Button(ctrl_frame, text="⚡ COMPILE SYSTEM", command=self.start_factory,
                                bg="#008f11", fg="white", font=("Consolas", 12, "bold"), 
                                width=20, relief="flat")
        self.btn_run.pack(side="left")

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_viewer.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_viewer.see(tk.END)
        self.root.update_idletasks()

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Python Files", "*.py")])
        if file_path:
            self.selected_file = file_path
            self.file_label.config(text=f"Blueprint Path: {file_path}")
            self.log(f"Blueprint Loaded: {os.path.basename(file_path)}")

    def start_factory(self):
        if not self.selected_file:
            messagebox.showwarning("Warning", "Please load a Python blueprint file first.")
            return
        
        self.btn_run.config(state="disabled", text="COMPILING...")
        thread = threading.Thread(target=self.run_transformation_pipeline)
        thread.start()

    def get_local_dependencies(self, node, global_imports):
        used_imports = []
        source_code = ast.dump(node)
        for imp in global_imports:
            parts = imp.replace('import ', '').replace('from ', '').split()
            if any(p in source_code for p in parts if len(p) > 2):
                used_imports.append(imp)
        return used_imports

    def extract_pypi_requirements(self, local_imports):
        reqs = set(["fastapi", "uvicorn", "pydantic"])
        for imp in local_imports:
            parts = imp.replace('from ', '').replace('import ', '').split()
            if parts:
                base_module = parts[0].split('.')[0]
                if base_module not in STDLIB_MODULES:
                    pypi_name = PYPI_MAPPING.get(base_module, base_module)
                    reqs.add(pypi_name)
        return list(reqs)

    def run_transformation_pipeline(self):
        try:
            self.log("--- INITIALIZING COMPILATION PIPELINE ---")
            self.services_manifest = []
            self.current_port = 8000
            
            with open(self.selected_file, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            
            # Setup new project architecture
            base_dir = self.output_dir
            src_dir = os.path.join(base_dir, "src")
            ms_dir = os.path.join(src_dir, "microservices")
            os.makedirs(ms_dir, exist_ok=True)
            
            global_imports = []
            entry_point_nodes = []

            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    seg = ast.get_source_segment(source, node) if sys.version_info >= (3, 8) else ast.dump(node)
                    if seg: global_imports.append(seg)
                    entry_point_nodes.append(node)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = node.name
                    node_type = "FUNCTION" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "CLASS"
                    self.log(f"Stamping API Unit: [{node_type}] -> '{name}'")
                    
                    try:
                        logic_segment = ast.get_source_segment(source, node) if sys.version_info >= (3, 8) else "# Version Error"
                    except Exception:
                        logic_segment = "# Extraction Error"

                    logic_hash = hashlib.sha256(logic_segment.encode()).hexdigest()[:12]
                    
                    self.current_port += 1
                    service_id = f"{name.lower()}_{logic_hash}"
                    
                    self.stamp_microservice(name, logic_segment, global_imports, service_id, node_type, node, ms_dir)
                    
                    self.services_manifest.append({
                        "name": name,
                        "id": service_id,
                        "type": node_type,
                        "port": self.current_port
                    })
                else:
                    # Keep module-level code (like if __name__ == "__main__":) for the entry point
                    entry_point_nodes.append(node)

            self.log("Building Orchestration Layer...")
            self.generate_orchestration(src_dir)
            
            self.log("Building Entry Point...")
            self.generate_entry_point(src_dir, source, entry_point_nodes)
            
            self.log("Writing Docker Compose File...")
            self.generate_docker_compose(base_dir)

            self.log("--- SYSTEM COMPILATION COMPLETE ---")
            messagebox.showinfo("Factory Success", f"Successfully compiled distributed system to '{self.output_dir}'")

        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}")
            messagebox.showerror("Factory Error", str(e))
        finally:
            self.btn_run.config(state="normal", text="⚡ COMPILE SYSTEM")

    def stamp_microservice(self, name, logic, imports, service_id, unit_type, ast_node, ms_dir):
        service_path = os.path.join(ms_dir, service_id)
        os.makedirs(service_path, exist_ok=True)

        # Provide orchestration access to the microservice itself
        local_imports = self.get_local_dependencies(ast_node, imports)
        full_logic = "import sys\nsys.path.append('..')\nfrom orchestration import *\n" + "\n".join(local_imports) + "\n\n" + logic
        with open(os.path.join(service_path, "logic.py"), "w", encoding='utf-8') as f:
            f.write(full_logic)

        # Main API Wrapper with Stateful Method Routing
        fastapi_wrapper = f"""from fastapi import FastAPI, Request, HTTPException
        import logic
        import traceback

        app = FastAPI(title="{name} API")

        # Singleton instance to persist state between API calls
        instance_store = {{"instance": None}}

        @app.post("/execute")
        async def execute(request: Request):
            payload = await request.json()
            method_name = payload.get("method")
            args = payload.get("args", [])
            kwargs = payload.get("kwargs", {{}})

            try:
        if "{unit_type}" == "FUNCTION":
            result = logic.{name}(*args, **kwargs)
            return {{"status": "success", "data": result}}
        
        # Handle Class Instantiation
        if not method_name or method_name == "__init__":
            instance_store["instance"] = logic.{name}(*args, **kwargs)
            return {{"status": "success", "message": "{name} initialized"}}

        # Handle Method Routing on Persistent Instance
        if instance_store["instance"]:
            target = getattr(instance_store["instance"], method_name)
            result = target(*args, **kwargs)
            return {{"status": "success", "data": result}}
        else:
            raise HTTPException(status_code=400, detail="Instance not initialized. Call __init__ first.")
            
            except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
        """
        with open(os.path.join(service_path, "main.py"), "w", encoding='utf-8') as f:
            f.write(fastapi_wrapper)

        # Requirements
        reqs = self.extract_pypi_requirements(local_imports)
        with open(os.path.join(service_path, "requirements.txt"), "w", encoding='utf-8') as f:
            f.write("\n".join(sorted(reqs)))

        # Dockerfile
        dockerfile = f"""FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
        with open(os.path.join(service_path, "Dockerfile"), "w", encoding='utf-8') as f:
            f.write(dockerfile)

    def generate_orchestration(self, src_dir):
        orch_code = ["import requests", "import json", "\n"]
        for srv in self.services_manifest:
            name = srv['name']
            sid = srv['id']
            url = f"http://{sid}:8000/execute"
            
            if srv['type'] == 'CLASS':
                orch_code.append(f"class {name}:")
                orch_code.append(f"    def __init__(self, *args, **kwargs):")
                orch_code.append(f"        self._api_url = '{url}'")
                orch_code.append(f"        requests.post(self._api_url, json=kwargs)")
                orch_code.append(f"    def __getattr__(self, name):")
                orch_code.append(f"        # Placeholder for routing method calls to the microservice")
                orch_code.append(f"        def method_proxy(*args, **kwargs):")
                orch_code.append(f"            return requests.post(self._api_url, json={{'method': name, 'args': args, 'kwargs': kwargs}}).json()")
                orch_code.append(f"        return method_proxy\n")
            else:
                orch_code.append(f"def {name}(*args, **kwargs):")
                orch_code.append(f"    url = '{url}'")
                orch_code.append(f"    payload = kwargs if kwargs else (args[0] if args else {{}})")
                orch_code.append(f"    response = requests.post(url, json=payload)")
                orch_code.append(f"    return response.json().get('data')\n")

        with open(os.path.join(src_dir, "orchestration.py"), "w", encoding='utf-8') as f:
            f.write("\n".join(orch_code))

    def generate_entry_point(self, src_dir, original_source, entry_point_nodes):
        # We rewrite the entry point to import from our new orchestration mesh
        ep_code = ["from orchestration import *\n"]
        
        for node in entry_point_nodes:
            # Reconstruct the leftover global logic (like CLI arg parsing and the __main__ block)
            if sys.version_info >= (3, 8):
                ep_code.append(ast.get_source_segment(original_source, node))
            
        with open(os.path.join(src_dir, "app.py"), "w", encoding='utf-8') as f:
            f.write("\n\n".join(ep_code))

    def generate_docker_compose(self, base_dir):
        compose_lines = [
            "version: '3.8'",
            "services:"
        ]
        
        for srv in self.services_manifest:
            sid = srv['id']
            port = srv['port']
            compose_lines.extend([
                f"  {sid}:",
                f"    build: ./src/microservices/{sid}",
                f"    ports:",
                f"      - '{port}:8000'",
                f"    restart: unless-stopped"
            ])
            
        with open(os.path.join(base_dir, "docker-compose.yml"), "w", encoding='utf-8') as f:
            f.write("\n".join(compose_lines))

if __name__ == "__main__":
    root = tk.Tk()
    root.tk_setPalette(background='#121212', foreground='#00ff41', 
                       activeBackground='#333333', activeForeground='#00ff41')
    app = MicroStamperApp(root)
    root.mainloop()
