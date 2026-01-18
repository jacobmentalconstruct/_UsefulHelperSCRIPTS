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
    version="2.2.0",
    description="Handles PDF loading, rendering, advanced optimization, and page extraction.",
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

    @service_endpoint(
        inputs={"path": "str", "page_string": "str"},
        outputs={"success": "bool", "message": "str"},
        description="Saves a new PDF containing only the specified pages in order.",
        tags=["io", "save", "extract"]
    )
    def save_subset(self, path: str, page_string: str) -> Tuple[bool, str]:
        print(f"[Engine] Attempting to save subset to: {path}")
        if not self.doc: 
            return False, "No document loaded"
        
        # Guard against overwriting the open file (Windows Permission Error)
        if self.current_path and os.path.abspath(path) == os.path.abspath(self.current_path):
            return False, "Cannot overwrite the currently open file.\nPlease save as a new name."

        try:
            # 1. Parse indices
            indices = self._parse_page_string(page_string, self.doc.page_count)
            print(f"[Engine] Parsed Pages to Extract: {indices}")
            
            if not indices:
                return False, "No valid pages found in range string. Try formats like '1, 3, 5-8'."

            # 2. Create new empty PDF
            new_doc = fitz.open()

            # 3. Copy pages
            for idx in indices:
                new_doc.insert_pdf(self.doc, from_page=idx, to_page=idx)

            # 4. Save
            # garbage=4 removes unused objects, deflate=True compresses
            new_doc.save(path, garbage=4, deflate=True)
            new_doc.close()
            
            print(f"[Engine] Success! Saved {len(indices)} pages.")
            return True, f"Saved {len(indices)} pages to {path}"
            
        except Exception as e:
            print(f"[Engine] Extraction Error: {e}")
            return False, f"Error: {str(e)}"

    def _parse_page_string(self, range_str: str, max_pages: int) -> List[int]:
        """Parses '1, 3-5, 2' or '1;3;5' into [0, 2, 3, 4, 1]"""
        indices = []
        # Replace common delimiters with commas
        cleaned = re.sub(r'[;\s]+', ',', range_str)
        parts = cleaned.split(',')
        
        for part in parts:
            part = part.strip()
            if not part: continue
            
            try:
                if '-' in part:
                    # Range: "3-5"
                    start_s, end_s = part.split('-')
                    start = int(start_s)
                    end = int(end_s)
                    step = 1 if end >= start else -1
                    # Range is inclusive in UI terms (1-3 means 1,2,3)
                    for i in range(start, end + step, step):
                        idx = i - 1 
                        if 0 <= idx < max_pages:
                            indices.append(idx)
                else:
                    # Single Number: "3"
                    i = int(part)
                    idx = i - 1
                    if 0 <= idx < max_pages:
                        indices.append(idx)
            except ValueError:
                print(f"[Engine] Skipping invalid token: {part}")
                continue
                    
        return indices

    @service_endpoint(
        inputs={"path": "str", "settings": "Dict"},
        outputs={"success": "bool"},
        description="Saves with granular compression settings.",
        tags=["io", "save", "advanced"]
    )
    def save_advanced(self, path: str, settings: Dict[str, Any]) -> bool:
        if not self.doc: return False
        try:
            if settings.get("optimize_images", False):
                self._optimize_images_granular(settings)

            garbage = 4 if settings.get("deduplicate", True) else 0
            deflate = settings.get("compress_streams", True)
            clean = settings.get("clean_structure", True)

            self.doc.save(path, garbage=garbage, deflate=deflate, clean=clean)
            return True
        except Exception as e:
            print(f"Save Error: {e}")
            return False

    def _optimize_images_granular(self, settings):
        target_dpi = settings.get("target_dpi", 150)
        jpeg_quality = settings.get("jpeg_quality", 75)
        grayscale = settings.get("grayscale", False)
        flatten_transparency = settings.get("flatten_transparency", True)
        max_dim = int(target_dpi * 11.0)
        visited_xrefs = set()

        for page_num in range(self.doc.page_count):
            page = self.doc[page_num]
            image_list = page.get_images()
            
            for img_info in image_list:
                xref = img_info[0]
                if xref in visited_xrefs: continue
                visited_xrefs.add(xref)

                try:
                    is_mask = self.doc.xref_object(xref, "ImageMask") == "true"
                    if is_mask and not settings.get("process_masks", False): continue

                    pix = fitz.Pixmap(self.doc, xref)
                    if pix.width < 100 or pix.height < 100: continue

                    if pix.n - pix.alpha > 3: pix = fitz.Pixmap(fitz.csRGB, pix, 0)

                    img_data = pix.tobytes()
                    pil_img = Image.open(io.BytesIO(img_data))

                    if flatten_transparency:
                        if pil_img.mode in ('RGBA', 'LA') or (pil_img.mode == 'P' and 'transparency' in pil_img.info):
                            pil_img = pil_img.convert('RGBA')
                            bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                            bg.paste(pil_img, mask=pil_img.split()[3])
                            pil_img = bg
                        elif pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')

                    if grayscale: pil_img = pil_img.convert("L")

                    if pil_img.width > max_dim or pil_img.height > max_dim:
                        pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                    out_buffer = io.BytesIO()
                    pil_img.save(out_buffer, format="JPEG", quality=jpeg_quality, optimize=True)
                    new_data = out_buffer.getvalue()
                    self.doc.update_stream(xref, new_data)
                except Exception as e:
                    print(f"Skipping xref {xref}: {e}")

    @service_endpoint(
        inputs={"page_num": "int", "clockwise": "bool"},
        outputs={"new_rotation": "int"},
        description="Rotates a single page 90 degrees CW or CCW.",
        tags=["edit", "rotate"]
    )
    def rotate_page(self, page_num: int, clockwise: bool = True) -> int:
        if not self.doc: return 0
        page = self.doc.load_page(page_num)
        delta = 90 if clockwise else -90
        new_rot = (page.rotation + delta) % 360
        page.set_rotation(new_rot)
        return new_rot

    @service_endpoint(
        inputs={"page_num": "int", "zoom": "float"},
        outputs={"image": "ImageTk.PhotoImage", "width": "int", "height": "int"},
        description="Renders a specific page to a Tkinter-compatible image.",
        tags=["render"]
    )
    def render_page(self, page_num: int, zoom: float = 1.0) -> Tuple[Any, int, int]:
        if not self.doc or not (0 <= page_num < self.doc.page_count):
            return None, 0, 0
        page = self.doc.load_page(page_num)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        tk_img = ImageTk.PhotoImage(img_data)
        return tk_img, pix.width, pix.height

    @service_endpoint(
        inputs={"page_num": "int", "max_size": "Tuple[int, int]"},
        outputs={"image": "ImageTk.PhotoImage", "width": "int", "height": "int"},
        description="Renders a thumbnail that fits WITHIN the given box.",
        tags=["render", "thumbnail"]
    )
    def render_thumbnail_fit(self, page_num: int, max_size: Tuple[int, int] = (200, 200)) -> Tuple[Any, int, int]:
        if not self.doc: return None, 0, 0
        page = self.doc.load_page(page_num)
        rect = page.rect
        scale = min(max_size[0] / rect.width, max_size[1] / rect.height)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        tk_img = ImageTk.PhotoImage(img_data)
        return tk_img, pix.width, pix.height

    def get_metadata(self):
        if not self.doc: return {}
        return self.doc.metadata