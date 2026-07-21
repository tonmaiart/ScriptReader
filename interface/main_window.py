"""
interface/main_window.py — CodePackerApp UI (Tkinter)
Depends on: core.packer_core.PackerCore, config.ini, pyperclip
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

# ---------------------------------------------------------------------------
# Auto-install third-party deps
# ---------------------------------------------------------------------------

def _ensure_package(import_name: str, pip_name: str | None = None) -> None:
    try:
        __import__(import_name)
    except ImportError:
        pkg = pip_name or import_name
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg, "--user", "--break-system-packages"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

_ensure_package("pyperclip")

import pyperclip  # noqa: E402

from core.packer_core import PackerCore  # noqa: E402

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class CodePackerApp:
    CONFIG_FILENAME = "config.ini"

    def __init__(self, root: tk.Tk, config_path: str):
        self.root = root
        self.root.title("🧠 NotebookLM Packager")
        self.root.geometry("480x790")
        self.root.minsize(400, 520)

        # Core (business logic — no Tkinter)
        self.config_path = config_path
        app_base_dir = os.path.dirname(os.path.abspath(config_path))
        self.core = PackerCore(config_path, app_base_dir)

        # UI-only state
        self.node_to_path: dict[str, tuple[str, bool]] = {}
        self.path_to_node: dict[str, str] = {}

        self.is_dragging = False
        self.drag_state = True
        self.drag_visited: set[str] = set()

        self._build_ui()
        self.core.remember_folder(self.core.target_folder)
        self._refresh_history_values()
        self.rescan(init_mode=True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Folder selector
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)
        ttk.Label(top, text="📁 โฟลเดอร์:").pack(side=tk.LEFT)
        self.lbl_folder = ttk.Label(top, text=self.core.target_folder, font=("Arial", 9, "bold"), anchor="w")
        self.lbl_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(top, text="เลือก...", width=8, command=self.browse_folder).pack(side=tk.RIGHT)

        # Recent-path history dropdown
        hist = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        hist.pack(fill=tk.X)
        ttk.Label(hist, text="🕘 ล่าสุด:").pack(side=tk.LEFT)
        self.history_var = tk.StringVar()
        self.cmb_history = ttk.Combobox(hist, textvariable=self.history_var, state="readonly")
        self.cmb_history.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.cmb_history.bind("<<ComboboxSelected>>", self._on_history_selected)

        # Search bar
        sf = ttk.Frame(self.root, padding=5)
        sf.pack(fill=tk.X)
        ttk.Label(sf, text="🔍 ค้นหา:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())
        ttk.Entry(sf, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(sf, text="ล้าง", width=5, command=lambda: self.search_var.set("")).pack(side=tk.LEFT, padx=2)

        # Control buttons
        ctrl = ttk.Frame(self.root, padding=5)
        ctrl.pack(fill=tk.X, padx=5)
        row1 = ttk.Frame(ctrl)
        row1.pack(fill=tk.X, pady=2)
        ttk.Button(row1, text="☑️ ทั้งหมด",  command=self.select_all).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(row1, text="🔲 ไม่เลือก", command=self.deselect_all).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(row1, text="⭐ MAIN",      command=self.select_only_main).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        row2 = ttk.Frame(ctrl)
        row2.pack(fill=tk.X, pady=2)
        ttk.Button(row2, text="🔄 Refresh", command=self.refresh).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(row2, text="🌿 Git Changes", command=self.select_git_changes).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        # Treeview
        tf = ttk.LabelFrame(self.root, text=" 📂 โครงสร้างโปรเจกต์ (ลากรูดเพื่อไฮไลท์) ", padding=5)
        tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(tf, show="tree", selectmode="none")
        self.tree.tag_configure("checked", background="#e2f0d9")
        self.tree.tag_configure("partial", background="#f5f5f5")
        self.tree.tag_configure("locked",  background="#fff8dc")   # main-list locked = warm yellow
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<ButtonPress-1>",   self.on_tree_click)
        self.tree.bind("<B1-Motion>",        self.on_tree_drag)
        self.tree.bind("<ButtonRelease-1>",  self.on_tree_release)
        self.tree.bind_all("<MouseWheel>",
            lambda e: self.tree.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Status + copy button
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill=tk.X)
        self.lbl_status = ttk.Label(bottom, text="พร้อมทำงาน", font=("Arial", 9, "italic"),
                                    foreground="gray", anchor="w")
        self.lbl_status.pack(fill=tk.X, pady=(0, 5))
        self.btn_copy = ttk.Button(bottom, text="🚀 คัดลอกลง Clipboard",
                                   command=self.process_and_copy)
        self.btn_copy.pack(fill=tk.X, ipady=4)

        # Reload button — separated by a thin divider
        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=10)
        reload_bar = ttk.Frame(self.root, padding=(10, 6))
        reload_bar.pack(fill=tk.X)
        ttk.Button(reload_bar, text="🔄 Reload Script (interface + core + data)",
                   command=self._reload_app).pack(fill=tk.X, ipady=2)

    # ------------------------------------------------------------------
    # Scanning & filtering
    # ------------------------------------------------------------------

    def rescan(self, init_mode: bool = False):
        count = self.core.rescan(init_mode=init_mode)
        self.apply_filter()
        if not init_mode:
            self.lbl_status.config(
                text=f"🔄 อัปเดตโครงสร้างไฟล์สำเร็จ — {count} ไฟล์",
                foreground="blue",
            )

    def apply_filter(self):
        query = self.search_var.get()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.node_to_path.clear()
        self.path_to_node.clear()

        filtered = self.core.filtered_files(query)

        for rel_path, _ in filtered:
            parts = rel_path.split(os.sep)
            parent = ""

            # Build folder nodes
            for i, part in enumerate(parts[:-1]):
                curr_dir = os.sep.join(parts[: i + 1])
                dir_key = curr_dir + " (Dir)"
                if not self.tree.exists(dir_key):
                    self.tree.insert(parent, "end", iid=dir_key, text=f"☐ 📁 {part}", open=True)
                parent = dir_key
                self.node_to_path[dir_key] = (curr_dir, True)
                self.path_to_node[curr_dir] = dir_key

            # File node
            file_name = parts[-1]
            locked = self.core.is_main(rel_path)
            prefix = "🔒⭐ [MAIN]" if locked else "📄"
            node_id = self.tree.insert(parent, "end", text=f"☑ {prefix} {file_name}" if locked else f"☐ {prefix} {file_name}")
            self.node_to_path[node_id] = (rel_path, False)
            self.path_to_node[rel_path] = node_id

        self.refresh_checkbox_symbols()

    def refresh_checkbox_symbols(self):
        # Files
        for rel_path, node_id in self.path_to_node.items():
            if not self.tree.exists(node_id) or rel_path.endswith(" (Dir)"):
                continue
            locked = self.core.is_main(rel_path)
            is_checked = self.core.file_states.get(rel_path, False)

            file_name = os.path.basename(rel_path)
            if locked:
                label = f"🔒⭐ [MAIN] {file_name}"
                self.tree.item(node_id, text=f"☑ {label}", tags=("locked",))
            else:
                sym = "☑" if is_checked else "☐"
                tags = ("checked",) if is_checked else ()
                self.tree.item(node_id, text=f"{sym} 📄 {file_name}", tags=tags)

        # Folders (bottom-up)
        dir_nodes = [n for n in self.node_to_path if n.endswith(" (Dir)")]
        dir_nodes.sort(key=lambda x: x.count(os.sep), reverse=True)

        for dir_node in dir_nodes:
            dir_path = dir_node.replace(" (Dir)", "")
            child_files = [f for f in self.core.file_states if f.startswith(dir_path + os.sep)]
            if not child_files:
                continue
            states = [self.core.file_states.get(cf, False) for cf in child_files]
            dir_name = dir_path.split(os.sep)[-1]
            if all(states):
                sym, tags = "☑", ("checked",)
            elif any(states):
                sym, tags = "☒", ("partial",)
            else:
                sym, tags = "☐", ()
            self.tree.item(dir_node, text=f"{sym} 📁 {dir_name}", tags=tags)

    # ------------------------------------------------------------------
    # Drag selection
    # ------------------------------------------------------------------

    def on_tree_click(self, event):
        # Clicking the expand/collapse arrow must only toggle the branch,
        # not the file selection underneath it.
        element = self.tree.identify_element(event.x, event.y)
        if "indicator" in element:
            return

        item_id = self.tree.identify_row(event.y)
        if not item_id or item_id not in self.node_to_path:
            return
        path_key, is_dir = self.node_to_path[item_id]
        self.is_dragging = True
        self.drag_visited.clear()

        if is_dir:
            child_files = self.core.get_nested_files(path_key)
            non_locked = [cf for cf in child_files if not self.core.is_main(cf)]
            all_checked = all(self.core.file_states.get(cf, False) for cf in non_locked) if non_locked else False
            self.drag_state = not all_checked
            for cf in child_files:
                self.core.set_file_state(cf, self.drag_state)
        else:
            if not self.core.is_main(path_key):
                self.drag_state = not self.core.file_states.get(path_key, False)
                self.core.set_file_state(path_key, self.drag_state)
            else:
                self.drag_state = True   # locked files stay True

        self.drag_visited.add(item_id)
        self.refresh_checkbox_symbols()

    def on_tree_drag(self, event):
        if not self.is_dragging:
            return
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.node_to_path and item_id not in self.drag_visited:
            path_key, is_dir = self.node_to_path[item_id]
            self.drag_visited.add(item_id)
            if is_dir:
                for cf in self.core.get_nested_files(path_key):
                    self.core.set_file_state(cf, self.drag_state)
            else:
                self.core.set_file_state(path_key, self.drag_state)
            self.refresh_checkbox_symbols()

    def on_tree_release(self, event):
        self.is_dragging = False
        self.drag_visited.clear()

    # ------------------------------------------------------------------
    # Shortcut buttons
    # ------------------------------------------------------------------

    def select_all(self):
        self.core.select_all()
        self.refresh_checkbox_symbols()

    def deselect_all(self):
        self.core.deselect_all()
        self.refresh_checkbox_symbols()

    def select_only_main(self):
        self.core.select_only_main()
        self.refresh_checkbox_symbols()

    def select_git_changes(self):
        kind, count = self.core.select_git_changes()
        if kind == "ok":
            self.refresh_checkbox_symbols()
            self.lbl_status.config(text=f"🌿 เลือก Git Changes สำเร็จ ({count} ไฟล์)", foreground="green")
        elif kind == "clean":
            self.lbl_status.config(text="🌿 Git Clean: ไม่พบไฟล์ที่มีการอัปเดต", foreground="orange")
        elif kind == "no_git":
            self.lbl_status.config(text="❌ ไม่พบคำสั่ง git", foreground="red")
        elif kind == "not_repo":
            self.lbl_status.config(text="❌ โฟลเดอร์นี้ไม่ใช่ Git Repository", foreground="red")

    # ------------------------------------------------------------------
    # Folder browser & history
    # ------------------------------------------------------------------

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.core.target_folder)
        if folder:
            self._switch_folder(os.path.abspath(folder))

    def _on_history_selected(self, event=None):
        folder = self.history_var.get()
        if folder and folder != self.core.target_folder and os.path.isdir(folder):
            self._switch_folder(folder)

    def _switch_folder(self, folder: str):
        self.core.target_folder = folder
        self.lbl_folder.config(text=folder)
        self.search_var.set("")
        self.core.remember_folder(folder)
        self._refresh_history_values()
        self.rescan(init_mode=True)

    def _refresh_history_values(self):
        history = self.core.get_history()
        self.cmb_history["values"] = history
        self.history_var.set(self.core.target_folder if self.core.target_folder in history else "")

    def refresh(self):
        self.core.reload_config()
        self.rescan(init_mode=False)

    # ------------------------------------------------------------------
    # Clipboard export
    # ------------------------------------------------------------------

    def process_and_copy(self):
        if not any(self.core.file_states.values()):
            self.lbl_status.config(text="⚠️ กรุณาติ๊กเลือกไฟล์อย่างน้อย 1 ไฟล์!", foreground="red")
            return

        self.btn_copy.config(state="disabled")
        self.lbl_status.config(text="⏳ กำลังสร้างเนื้อหา...", foreground="gray")

        def _build():
            full_text, selected_count = self.core.build_markdown()
            line_count = full_text.count("\n") + 1
            char_count = len(full_text)
            size_mb = char_count / (1024 * 1024)

            # Copy to clipboard using a hybrid approach
            def _copy_on_main():
                copied_via_tk = False
                try:
                    # 1. Try Native Tkinter Clipboard first (Extremely fast, bypasses subprocess issues)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(full_text)
                    self.root.update_idletasks() # Flush X11 event queue for Linux stability
                    copied_via_tk = True
                except Exception:
                    copied_via_tk = False

                if not copied_via_tk:
                    # 2. Fallback to pyperclip if native fails
                    try:
                        pyperclip.copy(full_text)
                    except Exception as e:
                        self.lbl_status.config(text=f"❌ คัดลอกล้มเหลว: {e}", foreground="red")
                        self.btn_copy.config(state="normal")
                        return

                self.btn_copy.config(state="normal")

                # Check file size payload to warn the user about target app freezes
                if size_mb > 1.5:
                    self.lbl_status.config(
                        text=f"⚠️ คัดลอกสำเร็จ! ขนาดใหญ่มาก ({size_mb:.2f}MB) ระวังแอปปลายทางค้างตอน Paste",
                        foreground="orange",
                    )
                else:
                    self.lbl_status.config(
                        text=f"✅ คัดลอกเรียบร้อย! ({selected_count} ไฟล์ | {line_count:,} บรรทัด | {char_count:,} ตัวอักษร)",
                        foreground="green",
                    )

            self.root.after(0, _copy_on_main)

        threading.Thread(target=_build, daemon=True).start()

    # ------------------------------------------------------------------
    # Hot-reload
    # ------------------------------------------------------------------

    def _reload_app(self):
        import importlib
        import sys

        saved_folder = self.core.target_folder
        config_path = self.config_path
        root = self.root

        for widget in root.winfo_children():
            widget.destroy()

        for mod_name in ("data.utils", "data.history", "core.packer_core", "interface.main_window"):
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])

        new_app = sys.modules["interface.main_window"].CodePackerApp(root, config_path=config_path)

        # Restore the folder the user had open before reload
        if saved_folder != new_app.core.target_folder:
            new_app._switch_folder(saved_folder)
