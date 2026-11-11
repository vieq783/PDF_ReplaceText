import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import fitz  # PyMuPDF
except ImportError:
    import pymupdf as fitz

# ------------------------------------------------------------------ FONT
# Font mặc định của PyMuPDF (Helvetica) KHÔNG có chữ tiếng Việt có dấu,
# nên chữ mới được vẽ bằng font TrueType có sẵn trong máy.
FONT_DIRS = [
    r"C:\Windows\Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
]
# (regular, bold, italic, bold-italic)
FONT_SETS = {
    "times": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
}
FALLBACKS_SANS = [
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
     "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
     "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
]
FALLBACKS_SERIF = [
    ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
     "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"),
    ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
     "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf"),
]


def _find(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def get_font_path(span_font):
    """Chọn file font gần giống font gốc của đoạn chữ bị thay."""
    n = re.sub(r"[^a-z]", "", span_font.split("+")[-1].lower())
    bold = "bold" in n or n.endswith("bd")
    ital = "italic" in n or "oblique" in n
    idx = 3 if (bold and ital) else 1 if bold else 2 if ital else 0
    key = next((k for k in FONT_SETS if k in n), None)
    if key is None and "roman" in n:
        key = "times"
    if key is None:
        key = "arial"
    p = _find(FONT_SETS[key][idx])
    if p:
        return p
    for fb in (FALLBACKS_SERIF if key == "times" else FALLBACKS_SANS):
        p = _find(fb[idx])
        if p:
            return p
    return None


# ------------------------------------------------------------------ CORE
def replace_text_in_pdf(pdf_path, search_text, replace_text, output_path,
                        align="center", progress=None):
    """align: 'left' | 'center' | 'right' - căn theo mép/tâm của text cũ."""
    doc = fitz.open(pdf_path)
    total_replaced = 0
    font_cache = {}

    for page_num in range(len(doc)):
        page = doc[page_num]

        # 1. Lấy thông tin span (cỡ chữ, màu, font, đường baseline)
        spans = []
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for sp in line["spans"]:
                    spans.append(sp)

        # 2. Tìm vị trí khớp
        matches = page.search_for(search_text)
        if not matches:
            if progress:
                progress(page_num + 1, len(doc))
            continue

        items = []
        for rect in matches:
            total_replaced += 1
            size, color, fname, baseline = 10, (0, 0, 0), "", None
            for sp in spans:
                if fitz.Rect(sp["bbox"]).intersects(rect):
                    size = sp["size"]
                    c = sp["color"]
                    color = (((c >> 16) & 255) / 255.0,
                             ((c >> 8) & 255) / 255.0,
                             (c & 255) / 255.0)
                    fname = sp["font"]
                    baseline = sp["origin"][1]
                    break
            if baseline is None:
                baseline = rect.y1 - rect.height * 0.15
            items.append((rect, size, color, fname, baseline))
            # 3. Xoá chữ cũ, giữ nguyên nền / hình / đường kẻ
            page.add_redact_annot(rect, fill=False)

        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        except TypeError:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # 4. Chèn chữ mới, căn theo vị trí chữ cũ
        for rect, size, color, fname, baseline in items:
            if not replace_text:
                continue
            path = get_font_path(fname)
            if path:
                if path not in font_cache:
                    font_cache[path] = fitz.Font(fontfile=path)
                width = font_cache[path].text_length(replace_text, fontsize=size)
                kw = dict(fontname="F" + re.sub(r"\W", "", os.path.basename(path)),
                          fontfile=path)
            else:
                width = fitz.get_text_length(replace_text, fontname="helv", fontsize=size)
                kw = dict(fontname="helv")

            if align == "left":
                x = rect.x0
            elif align == "right":
                x = rect.x1 - width
            else:
                x = (rect.x0 + rect.x1) / 2 - width / 2

            page.insert_text(fitz.Point(x, baseline), replace_text,
                             fontsize=size, color=color, **kw)

        if progress:
            progress(page_num + 1, len(doc))

    doc.save(output_path, garbage=3, deflate=True)
    doc.close()
    return total_replaced


# ------------------------------------------------------------------ UI
BG = "#F1F5F9"
CARD = "#FFFFFF"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
LABEL = "#1E3A8A"      # màu tiêu đề các ô
TEXT = "#0F172A"
MUTED = "#64748B"
BORDER = "#CBD5E1"
SEG_BG = "#E2E8F0"
FONT = "Segoe UI"
RADIUS = 10


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class RoundedEntry(tk.Canvas):
    """Ô nhập có viền bo tròn, đổi màu viền khi đang focus."""

    def __init__(self, parent, textvariable=None, height=40, bg=CARD):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.entry = tk.Entry(self, textvariable=textvariable, relief="flat", bd=0,
                              bg="#FFFFFF", fg=TEXT, insertbackground=TEXT,
                              font=(FONT, 10), highlightthickness=0)
        self._focus = False
        self._win = self.create_window(RADIUS + 4, height / 2, window=self.entry, anchor="w")
        self.bind("<Configure>", self._draw)
        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<Button-1>", lambda e: self.entry.focus_set())

    def _set_focus(self, v):
        self._focus = v
        self._draw()

    def _draw(self, event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.delete("bg")
        round_rect(self, 1, 1, w - 1, h - 1, RADIUS, fill="#FFFFFF", tags="bg",
                   outline=PRIMARY if self._focus else BORDER, width=2 if self._focus else 1)
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=w - 2 * RADIUS - 8)

    def get(self):
        return self.entry.get()

    def insert(self, index, s):
        self.entry.insert(index, s)


class RoundedButton(tk.Canvas):
    """Nút bo tròn có hiệu ứng hover / disabled."""

    def __init__(self, parent, text, command, width=120, height=40,
                 bg=PRIMARY, hover=PRIMARY_DARK, fg="white",
                 font=(FONT, 10, "bold"), outer=CARD):
        super().__init__(parent, width=width, height=height, bg=outer,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command = text, command
        self.c_bg, self.c_hover, self.c_fg, self.font = bg, hover, fg, font
        self._hover = False
        self._disabled = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _click(self, e):
        if not self._disabled and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.delete("all")
        fill = "#94A3B8" if self._disabled else (self.c_hover if self._hover else self.c_bg)
        round_rect(self, 1, 1, w - 1, h - 1, RADIUS, fill=fill, outline=fill)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.c_fg, font=self.font)

    def state(self, flags):
        if "disabled" in flags:
            self._disabled = True
            self.configure(cursor="arrow")
        elif "!disabled" in flags:
            self._disabled = False
            self.configure(cursor="hand2")
        self._draw()


class Segmented(tk.Frame):
    """Nhóm 3 nút chọn căn lề bo tròn."""

    def __init__(self, parent, variable, options):
        super().__init__(parent, bg=CARD)
        self.var = variable
        self.btns = {}
        for text, val in options:
            b = RoundedButton(self, text, lambda v=val: self._select(v), width=104, height=36,
                              bg=SEG_BG, hover="#CBD5E1", fg=TEXT, font=(FONT, 10))
            b.pack(side="left", padx=(0, 8))
            self.btns[val] = b
        self._select(variable.get())

    def _select(self, val):
        self.var.set(val)
        for v, b in self.btns.items():
            on = v == val
            b.c_bg = PRIMARY if on else SEG_BG
            b.c_hover = PRIMARY_DARK if on else "#CBD5E1"
            b.c_fg = "white" if on else TEXT
            b.font = (FONT, 10, "bold") if on else (FONT, 10)
            b._draw()


class RoundedProgress(tk.Canvas):
    def __init__(self, parent, height=10, bg=BG):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.value = 0
        self.bind("<Configure>", lambda e: self._draw())

    def configure(self, cnf=None, **kw):
        if "value" in kw:
            self.value = kw.pop("value")
            self._draw()
        if cnf or kw:
            super().configure(cnf, **kw)

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.delete("all")
        round_rect(self, 0, 0, w, h, h / 2, fill=SEG_BG, outline=SEG_BG)
        if self.value > 0:
            fw = max(h, w * self.value / 100)
            round_rect(self, 0, 0, fw, h, h / 2, fill=PRIMARY, outline=PRIMARY)


class PDFReplacerApp:
    def __init__(self, root):
        self.root = root
        root.title("PDF Text Replacer")
        root.geometry("640x660")
        root.minsize(600, 640)
        root.configure(bg=BG)

        self.file_path_var = tk.StringVar()
        self.save_name_var = tk.StringVar()
        self.align_var = tk.StringVar(value="center")
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        self._build()

    def _title(self, parent, text, row, pady=(12, 5), columnspan=3):
        """Tiêu đề ô: chữ đậm, cỡ lớn, màu xanh đậm, kèm vạch nhấn bên trái."""
        f = tk.Frame(parent, bg=CARD)
        f.grid(row=row, column=0, columnspan=columnspan, sticky="w", pady=pady)
        tk.Frame(f, bg=PRIMARY, width=4, height=16).pack(side="left", padx=(0, 8))
        tk.Label(f, text=text, bg=CARD, fg=LABEL, font=(FONT, 11, "bold")).pack(side="left")

    def _build(self):
        header = tk.Frame(self.root, bg=PRIMARY, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="PDF Text Replacer", bg=PRIMARY, fg="white",
                 font=(FONT, 16, "bold")).pack(side="left", padx=24)
        tk.Label(header, text="Tìm & thay chữ toàn bộ trang", bg=PRIMARY, fg="#BFDBFE",
                 font=(FONT, 10)).pack(side="left")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        card = tk.Frame(body, bg=CARD, padx=18, pady=10)
        card.pack(fill="x")
        card.columnconfigure(0, weight=1)

        self._title(card, "File PDF", 0, pady=(4, 5))
        RoundedEntry(card, self.file_path_var).grid(row=1, column=0, columnspan=2,
                                                   sticky="ew", padx=(0, 10))
        RoundedButton(card, "Chọn file…", self.browse_file, width=116, bg="#EFF6FF",
                      hover="#DBEAFE", fg=PRIMARY).grid(row=1, column=2)

        self._title(card, "Nội dung tìm", 2)
        self.entry_find = RoundedEntry(card)
        self.entry_find.grid(row=3, column=0, columnspan=3, sticky="ew")

        self._title(card, "Nội dung thay", 4)
        self.entry_replace = RoundedEntry(card)
        self.entry_replace.grid(row=5, column=0, columnspan=3, sticky="ew")

        self._title(card, "Căn chữ mới theo chữ cũ", 6)
        Segmented(card, self.align_var,
                  (("Căn trái", "left"), ("Căn giữa", "center"), ("Căn phải", "right"))
                  ).grid(row=7, column=0, columnspan=3, sticky="w")
        tk.Label(card, bg=CARD, fg=MUTED, font=(FONT, 9),
                 text="Trái/phải: khớp mép trái/phải của chữ cũ.  Giữa: khớp tâm của chữ cũ."
                 ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(5, 0))

        self._title(card, "Tên file lưu", 9)
        RoundedEntry(card, self.save_name_var).grid(row=10, column=0, columnspan=3,
                                                    sticky="ew", pady=(0, 6))

        self.btn_run = RoundedButton(body, "Bắt đầu thay thế toàn bộ", self.process_replace,
                                     height=48, font=(FONT, 11, "bold"), outer=BG)
        self.btn_run.pack(fill="x", pady=(16, 10))

        self.progress = RoundedProgress(body)
        self.progress.pack(fill="x")
        tk.Label(body, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(6, 0))

    # ---- actions
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Chọn file PDF", filetypes=[("PDF files", "*.pdf")])
        if filename:
            self.file_path_var.set(filename)
            base = os.path.splitext(os.path.basename(filename))[0]
            self.save_name_var.set(f"{base}_replaced.pdf")

    def _set_progress(self, done, total):
        self.root.after(0, lambda: (
            self.progress.configure(value=100 * done / total),
            self.status_var.set(f"Đang xử lý trang {done}/{total}…")))

    def process_replace(self):
        pdf_path = self.file_path_var.get().strip()
        find_txt = self.entry_find.get()
        rep_txt = self.entry_replace.get()
        save_name = self.save_name_var.get().strip()

        if not pdf_path or not os.path.isfile(pdf_path):
            return messagebox.showerror("Lỗi", "Vui lòng chọn file PDF hợp lệ!")
        if not find_txt:
            return messagebox.showerror("Lỗi", "Vui lòng nhập nội dung cần tìm!")
        if not save_name:
            return messagebox.showerror("Lỗi", "Vui lòng nhập tên file lưu mới!")
        if not save_name.lower().endswith(".pdf"):
            save_name += ".pdf"
        out_path = os.path.join(os.path.dirname(pdf_path), save_name)
        if os.path.abspath(out_path) == os.path.abspath(pdf_path):
            return messagebox.showerror("Lỗi", "Tên file lưu phải khác file gốc!")

        self.btn_run.state(["disabled"])
        self.progress.configure(value=0)
        self.status_var.set("Đang xử lý…")
        align = self.align_var.get()

        def work():
            try:
                n = replace_text_in_pdf(pdf_path, find_txt, rep_txt, out_path,
                                        align, self._set_progress)
                self.root.after(0, lambda: self._done(n, find_txt, out_path))
            except Exception as e:
                self.root.after(0, lambda: self._fail(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, count, find_txt, out_path):
        self.btn_run.state(["!disabled"])
        if count > 0:
            self.progress.configure(value=100)
            self.status_var.set(f"Xong: thay {count} vị trí.")
            messagebox.showinfo(
                "Thành công",
                f"Đã thay thế {count} vị trí xuất hiện.\nFile đã lưu tại:\n{out_path}")
        else:
            self.progress.configure(value=0)
            self.status_var.set("Không tìm thấy cụm từ.")
            messagebox.showwarning("Kết quả", f"Không tìm thấy cụm từ '{find_txt}' trong file.")

    def _fail(self, msg):
        self.btn_run.state(["!disabled"])
        self.status_var.set("Có lỗi xảy ra.")
        messagebox.showerror("Lỗi xử lý", f"Đã xảy ra lỗi trong quá trình xử lý:\n{msg}")


if __name__ == "__main__":
    try:  # giúp chữ nét hơn trên Windows màn hình độ phân giải cao
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app_root = tk.Tk()
    PDFReplacerApp(app_root)
    app_root.mainloop()