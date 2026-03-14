"""
SERVICE_NAME: _PdfEngineMS
ENTRY_POINT: _PdfEngineMS.py
DEPENDENCIES: pymupdf, Pillow
"""
import fitz  # PyMuPDF
import io
import os
import re
from PIL import Image, ImageTk
from typing import Optional, Dict, Any, Tuple, List
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="PdfEngine",
    version="3.0.0",
    description="Handles PDF loading, rendering, optimization, splitting, reordering, and merging.",
    tags=["pdf", "engine", "core"],
    capabilities=["pdf:read", "pdf:render", "pdf:write", "pdf:edit"]
)
class PdfEngineMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.doc: Optional[fitz.Document] = None
        self.current_path: Optional[str] = None

    @service_endpoint(
        inputs={"path": "str"},
        outputs={"page_count": "int"},
        description="Opens a PDF file from disk.",
        tags=["io", "load"]
    )
    def load_pdf(self, path: str) -> int:
        try:
            self.doc = fitz.open(path)
            self.current_path = path
            return self.doc.page_count
        except Exception as e:
            print(f"Engine Error: {e}")
            return 0

    # --- MANIPULATION METHODS (NEW) ---

    @service_endpoint(
        inputs={"page_idx": "int"},
        outputs={"success": "bool", "new_count": "int"},
        description="Deletes a single page.",
        tags=["edit", "delete"]
    )
    def delete_page(self, page_idx: int) -> Tuple[bool, int]:
        if not self.doc: return False, 0
        try:
            self.doc.delete_page(page_idx)
            return True, self.doc.page_count
        except Exception as e:
            print(f"Delete Error: {e}")
            return False, self.doc.page_count

    @service_endpoint(
        inputs={"path": "str", "at_index": "int"},
        outputs={"success": "bool", "new_count": "int"},
        description="Inserts another PDF file at the specified index.",
        tags=["edit", "insert"]
    )
    def insert_file(self, path: str, at_index: int) -> Tuple[bool, int]:
        if not self.doc: return False, 0
        try:
            src = fitz.open(path)
            # PyMuPDF insert_pdf merges 'src' into 'doc'
            # start_at: index in 'doc' where insertion happens (default -1 is end)
            # We want to insert *before* the current page usually, or after.
            # Let's map 'at_index' directly.
            self.doc.insert_pdf(src, start_at=at_index)
            return True, self.doc.page_count
        except Exception as e:
            print(f"Insert Error: {e}")
            return False, self.doc.page_count

    @service_endpoint(
        inputs={"path": "str", "reverse_second": "bool"},
        outputs={"success": "bool", "new_count": "int"},
        description="Interleaves an external PDF with the current one (A1, B1, A2, B2...).",
        tags=["edit", "interleave"]
    )
    def interleave_file(self, path: str, reverse_second: bool = False) -> Tuple[bool, int]:
        if not self.doc: return False, 0
        try:
            doc_b = fitz.open(path)
            
            # Create a new destination doc to rebuild cleanly
            new_doc = fitz.open()
            
            len_a = self.doc.page_count
            len_b = doc_b.page_count
            max_len = max(len_a, len_b)
            
            for i in range(max_len):
                # Add Page from A (Current)
                if i < len_a:
                    new_doc.insert_pdf(self.doc, from_page=i, to_page=i)
                
                # Add Page from B (External)
                if i < len_b:
                    # Calculate index for B
                    idx_b = (len_b - 1 - i) if reverse_second else i
                    new_doc.insert_pdf(doc_b, from_page=idx_b, to_page=idx_b)
            
            # Swap current doc with new interleaved one
            self.doc = new_doc
            return True, self.doc.page_count
            
        except Exception as e:
            print(f"Interleave Error: {e}")
            return False, self.doc.page_count

    # --- EXISTING METHODS ---

    @service_endpoint(
        inputs={"from_idx": "int", "to_idx": "int"},
        outputs={"success": "bool"},
        description="Moves a page.",
        tags=["edit", "reorder"]
    )
    def move_page(self, from_idx: int, to_idx: int) -> bool:
        if not self.doc: return False
        try:
            self.doc.move_page(from_idx, to_idx)
            return True
        except: return False

    @service_endpoint(
        inputs={"path": "str", "page_string": "str"},
        outputs={"success": "bool", "message": "str"},
        description="Saves a subset.",
        tags=["io", "save", "extract"]
    )
    def save_subset(self, path: str, page_string: str) -> Tuple[bool, str]:
        if not self.doc: return False, "No doc"
        if self.current_path and os.path.abspath(path) == os.path.abspath(self.current_path):
            return False, "Cannot overwrite open file."
        try:
            indices = self._parse_page_string(page_string, self.doc.page_count)
            if not indices: return False, "No valid pages."
            new_doc = fitz.open()
            for idx in indices: new_doc.insert_pdf(self.doc, from_page=idx, to_page=idx)
            new_doc.save(path, garbage=4, deflate=True)
            new_doc.close()
            return True, f"Saved {len(indices)} pages."
        except Exception as e: return False, str(e)

    def _parse_page_string(self, range_str: str, max_pages: int) -> List[int]:
        indices = []
        cleaned = re.sub(r'[;\s]+', ',', range_str)
        for part in cleaned.split(','):
            part = part.strip()
            if not part: continue
            try:
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    step = 1 if e >= s else -1
                    for i in range(s, e + step, step):
                        if 0 <= i-1 < max_pages: indices.append(i-1)
                else:
                    i = int(part)
                    if 0 <= i-1 < max_pages: indices.append(i-1)
            except: continue
        return indices

    @service_endpoint(
        inputs={"base_path": "str", "max_mb": "int"},
        outputs={"created_files": "List[str]"},
        description="Splits PDF by size.",
        tags=["io", "save", "split"]
    )
    def save_split_by_size(self, base_path: str, max_mb: int) -> Tuple[bool, List[str]]:
        if not self.doc: return False, []
        target = max_mb * 1024 * 1024
        files = []
        folder, fname = os.path.split(base_path)
        name, ext = os.path.splitext(fname)
        chunk_start = 0
        curr = fitz.open()
        try:
            for i in range(self.doc.page_count):
                curr.insert_pdf(self.doc, from_page=i, to_page=i)
                buf = io.BytesIO()
                curr.save(buf, garbage=4, deflate=True)
                if buf.tell() > target:
                    if curr.page_count == 1:
                        out = f"{name}_Part{len(files)+1}_{chunk_start+1}-{i+1}{ext}"
                        curr.save(os.path.join(folder, out), garbage=4)
                        files.append(out)
                        curr.close(); curr = fitz.open(); chunk_start = i+1
                    else:
                        curr.delete_page(-1)
                        out = f"{name}_Part{len(files)+1}_{chunk_start+1}-{i}{ext}"
                        curr.save(os.path.join(folder, out), garbage=4)
                        files.append(out)
                        curr.close(); curr = fitz.open(); curr.insert_pdf(self.doc, from_page=i, to_page=i)
                        chunk_start = i
            if curr.page_count > 0:
                out = f"{name}_Part{len(files)+1}_{chunk_start+1}-{self.doc.page_count}{ext}"
                curr.save(os.path.join(folder, out), garbage=4)
                files.append(out)
            return True, files
        except Exception as e: return False, [str(e)]

    @service_endpoint(
        inputs={"path": "str", "settings": "Dict"},
        outputs={"success": "bool"},
        description="Advanced Save.",
        tags=["io", "save", "advanced"]
    )
    def save_advanced(self, path: str, settings: Dict[str, Any]) -> bool:
        if not self.doc: return False
        try:
            if settings.get("optimize_images", False): self._optimize_images_granular(settings)
            garbage = 4 if settings.get("deduplicate", True) else 0
            deflate = settings.get("compress_streams", True)
            clean = settings.get("clean_structure", True)
            self.doc.save(path, garbage=garbage, deflate=deflate, clean=clean)
            return True
        except: return False

    def _optimize_images_granular(self, settings):
        dpi = settings.get("target_dpi", 150)
        qual = settings.get("jpeg_quality", 75)
        gray = settings.get("grayscale", False)
        flat = settings.get("flatten_transparency", True)
        max_d = int(dpi * 11.0)
        visited = set()
        for i in range(self.doc.page_count):
            for img in self.doc[i].get_images():
                xref = img[0]
                if xref in visited: continue
                visited.add(xref)
                try:
                    if self.doc.xref_object(xref, "ImageMask") == "true" and not settings.get("process_masks", False): continue
                    pix = fitz.Pixmap(self.doc, xref)
                    if pix.width < 100 or pix.height < 100: continue
                    if pix.n - pix.alpha > 3: pix = fitz.Pixmap(fitz.csRGB, pix, 0)
                    pil = Image.open(io.BytesIO(pix.tobytes()))
                    if flat:
                        if pil.mode in ('RGBA', 'LA') or (pil.mode == 'P' and 'transparency' in pil.info):
                            pil = pil.convert('RGBA')
                            bg = Image.new('RGB', pil.size, (255,255,255))
                            bg.paste(pil, mask=pil.split()[3])
                            pil = bg
                        elif pil.mode != 'RGB': pil = pil.convert('RGB')
                    if gray: pil = pil.convert("L")
                    if pil.width > max_d or pil.height > max_d: pil.thumbnail((max_d, max_d), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    pil.save(buf, "JPEG", quality=qual, optimize=True)
                    self.doc.update_stream(xref, buf.getvalue())
                except: pass

    @service_endpoint(
        inputs={"page_num": "int", "clockwise": "bool"},
        outputs={"new_rotation": "int"},
        description="Rotates page.",
        tags=["edit", "rotate"]
    )
    def rotate_page(self, page_num: int, clockwise: bool = True) -> int:
        if not self.doc: return 0
        p = self.doc.load_page(page_num)
        p.set_rotation((p.rotation + (90 if clockwise else -90)) % 360)
        return p.rotation

    @service_endpoint(
        inputs={"page_num": "int", "zoom": "float"},
        outputs={"image": "ImageTk.PhotoImage"},
        description="Renders page.",
        tags=["render"]
    )
    def render_page(self, page_num: int, zoom: float = 1.0) -> Tuple[Any, int, int]:
        if not self.doc or not (0 <= page_num < self.doc.page_count): return None, 0, 0
        pix = self.doc.load_page(page_num).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return ImageTk.PhotoImage(img), pix.width, pix.height

    @service_endpoint(
        inputs={"page_num": "int", "max_size": "Tuple"},
        outputs={"image": "ImageTk.PhotoImage"},
        description="Renders thumbnail.",
        tags=["render", "thumbnail"]
    )
    def render_thumbnail_fit(self, page_num: int, max_size: Tuple[int, int] = (200, 200)) -> Tuple[Any, int, int]:
        if not self.doc: return None, 0, 0
        p = self.doc.load_page(page_num)
        s = min(max_size[0]/p.rect.width, max_size[1]/p.rect.height)
        pix = p.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return ImageTk.PhotoImage(img), pix.width, pix.height

    def get_metadata(self): return self.doc.metadata if self.doc else {}