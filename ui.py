"""
ui.py — CodePackerApp UI
Depends on: utils.py, config.ini, pyperclip
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

from utils import (  # noqa: E402
    get_default_folder,
    get_ignore_list,
    get_main_keywords,
    get_main_paths,
    get_supported_extensions,
    is_in_main_list,
    load_config,
    scan_files,
)

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class CodePackerApp:
    CONFIG_FILENAME = "config.ini"

    def __init__(self, root: tk.Tk, config_path: str):
        self.root = root
        self.root.title("🧠 NotebookLM Packager")
        self.root.geometry("480x750")
        self.root.minsize(400, 500)

        # Config
        self.config_path = config_path
        self._reload_config()

        # State
        default = get_default_folder(load_config(self.config_path))
        self.target_folder = os.path.abspath(default if default and os.path.isdir(default) else ".")
        self.all_files: list[tuple[str, str]] = []
        self.file_states: dict[str, bool] = {}   # rel_path → selected
        self.node_to_path: dict[str, tuple[str, bool]] = {}
        self.path_to_node: dict[str, str] = {}

        self.is_dragging = False
        self.drag_state = True
        self.drag_visited: set[str] = set()

        self._build_ui()
        self.rescan(init_mode=True)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _reload_config(self):
        cfg = load_config(self.config_path)
        self.ignore_list = get_ignore_list(cfg)
        self.supported_extensions = get_supported_extensions(cfg)
        self.main_keywords = get_main_keywords(cfg)
        self.main_paths = get_main_paths(cfg)

    def _is_main(self, rel_path: str) -> bool:
        return is_in_main_list(rel_path, self.main_keywords, self.main_paths)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Folder selector
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)
        ttk.Label(top, text="📁 โฟลเดอร์:").pack(side=tk.LEFT)
        self.lbl_folder = ttk.Label(top, text=self.target_folder, font=("Arial", 9, "bold"), anchor="w")
        self.lbl_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(top, text="เลือก...", width=8, command=self.browse_folder).pack(side=tk.RIGHT)

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
        ttk.Button(reload_bar, text="🔄 Reload Script (ui + utils)",
                   command=self._reload_app).pack(fill=tk.X, ipady=2)

    # ------------------------------------------------------------------
    # Scanning & filtering
    # ------------------------------------------------------------------

    def rescan(self, init_mode: bool = False):
        old_states = dict(self.file_states)
        self.file_states.clear()
        self.all_files = scan_files(self.target_folder, self.ignore_list, self.supported_extensions)

        for rel, _ in self.all_files:
            if self._is_main(rel):
                # MAIN files are ALWAYS selected — user cannot deselect them
                self.file_states[rel] = True
            elif init_mode:
                self.file_states[rel] = False
            else:
                self.file_states[rel] = old_states.get(rel, False)

        self.apply_filter()
        if not init_mode:
            self.lbl_status.config(
                text=f"🔄 อัปเดตโครงสร้างไฟล์สำเร็จ — {len(self.all_files)} ไฟล์",
                foreground="blue",
            )

    def apply_filter(self):
        query = self.search_var.get().lower().strip()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.node_to_path.clear()
        self.path_to_node.clear()

        filtered = [
            item for item in self.all_files
            if not query
            or query in item[0].lower()
            or query in os.path.basename(item[0]).lower()
        ]

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
            locked = self._is_main(rel_path)
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
            locked = self._is_main(rel_path)
            is_checked = self.file_states.get(rel_path, False)

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
            child_files = [f for f in self.file_states if f.startswith(dir_path + os.sep)]
            if not child_files:
                continue
            states = [self.file_states.get(cf, False) for cf in child_files]
            dir_name = dir_path.split(os.sep)[-1]
            if all(states):
                sym, tags = "☑", ("checked",)
            elif any(states):
                sym, tags = "☒", ("partial",)
            else:
                sym, tags = "☐", ()
            self.tree.item(dir_node, text=f"{sym} 📁 {dir_name}", tags=tags)

    # ------------------------------------------------------------------
    # Toggle helpers  (respect locked files)
    # ------------------------------------------------------------------

    def _set_file_state(self, rel_path: str, state: bool):
        """Set selection state — MAIN files are always forced True."""
        if self._is_main(rel_path):
            self.file_states[rel_path] = True
        else:
            self.file_states[rel_path] = state

    def _get_nested_files(self, dir_path: str) -> list[str]:
        return [f for f in self.file_states if f.startswith(dir_path + os.sep)]

    # ------------------------------------------------------------------
    # Drag selection
    # ------------------------------------------------------------------

    def on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id or item_id not in self.node_to_path:
            return
        path_key, is_dir = self.node_to_path[item_id]
        self.is_dragging = True
        self.drag_visited.clear()

        if is_dir:
            child_files = self._get_nested_files(path_key)
            non_locked = [cf for cf in child_files if not self._is_main(cf)]
            all_checked = all(self.file_states.get(cf, False) for cf in non_locked) if non_locked else False
            self.drag_state = not all_checked
            for cf in child_files:
                self._set_file_state(cf, self.drag_state)
        else:
            if not self._is_main(path_key):
                self.drag_state = not self.file_states.get(path_key, False)
                self._set_file_state(path_key, self.drag_state)
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
                for cf in self._get_nested_files(path_key):
                    self._set_file_state(cf, self.drag_state)
            else:
                self._set_file_state(path_key, self.drag_state)
            self.refresh_checkbox_symbols()

    def on_tree_release(self, event):
        self.is_dragging = False
        self.drag_visited.clear()

    # ------------------------------------------------------------------
    # Shortcut buttons
    # ------------------------------------------------------------------

    def select_all(self):
        for path in self.file_states:
            self._set_file_state(path, True)
        self.refresh_checkbox_symbols()

    def deselect_all(self):
        for path in self.file_states:
            self._set_file_state(path, False)   # locked files stay True internally
        self.refresh_checkbox_symbols()

    def select_only_main(self):
        for path in self.file_states:
            self._set_file_state(path, self._is_main(path))
        self.refresh_checkbox_symbols()

    def select_git_changes(self):
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.target_folder,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=True,
            )
            git_files = [
                line[3:].strip().replace("/", os.sep)
                for line in result.stdout.splitlines()
                if len(line) > 3
            ]
            if not git_files:
                self.lbl_status.config(text="🌿 Git Clean: ไม่พบไฟล์ที่มีการอัปเดต", foreground="orange")
                return
            count = 0
            for path in self.file_states:
                state = path in git_files
                self._set_file_state(path, state)
                if state:
                    count += 1
            self.refresh_checkbox_symbols()
            self.lbl_status.config(text=f"🌿 เลือก Git Changes สำเร็จ ({count} ไฟล์)", foreground="green")
        except FileNotFoundError:
            self.lbl_status.config(text="❌ ไม่พบคำสั่ง git", foreground="red")
        except subprocess.CalledProcessError:
            self.lbl_status.config(text="❌ โฟลเดอร์นี้ไม่ใช่ Git Repository", foreground="red")

    # ------------------------------------------------------------------
    # Folder browser
    # ------------------------------------------------------------------

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.target_folder)
        if folder:
            self.target_folder = os.path.abspath(folder)
            self.lbl_folder.config(text=self.target_folder)
            self.search_var.set("")
            self.rescan(init_mode=True)

    def refresh(self):
        self._reload_config()
        self.rescan(init_mode=False)

    # ------------------------------------------------------------------
    # Clipboard export
    # ------------------------------------------------------------------

    def process_and_copy(self):
        # Snapshot state now so a concurrent rescan can't mutate it mid-build
        all_files_snap = list(self.all_files)
        file_states_snap = dict(self.file_states)
        selected = [(r, fp) for r, fp in all_files_snap if file_states_snap.get(r, False)]

        if not selected:
            self.lbl_status.config(text="⚠️ กรุณาติ๊กเลือกไฟล์อย่างน้อย 1 ไฟล์!", foreground="red")
            return

        self.btn_copy.config(state="disabled")
        self.lbl_status.config(text="⏳ กำลังสร้างเนื้อหา...", foreground="gray")

        def _build():
            md = [f"# 🧠 Knowledge Base: {os.path.basename(self.target_folder) or 'Root'}\n---\n"]

            # Table of contents
            md.append("## 📁 สารบัญโครงสร้างไฟล์ทั้งหมด")
            for rel_path, _ in all_files_snap:
                anchor = "".join(c if c.isalnum() else "" for c in rel_path.lower())
                is_copied = file_states_snap.get(rel_path, False)
                sym = "☑" if is_copied else "☐"
                if is_copied:
                    md.append(f"* {sym} [{rel_path}](#{anchor})")
                else:
                    md.append(f"* {sym} ~~{rel_path}~~ *(ไม่ได้เลือกคัดลอก)*")
            md.append("\n---\n")

            # File contents
            for rel, fp in selected:
                anchor = "".join(c if c.isalnum() else "" for c in rel.lower())
                md.append(f'<a name="{anchor}"></a>')
                md.append(f"## 📄 File: {os.path.basename(fp)}\n**Path:** `{rel}`\n")
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read().strip()
                    ext = os.path.splitext(fp)[1][1:]
                    md.append(f"```{ext if ext not in ('txt', 'md') else ''}\n{content}\n```\n")
                except Exception as e:
                    md.append(f"⚠️ *[Error: {e}]*\n")
                md.append("---")

            full_text = "\n".join(md)
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
                        text=f"✅ คัดลอกเรียบร้อย! ({len(selected)} ไฟล์ | {line_count:,} บรรทัด | {char_count:,} ตัวอักษร)",
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

        saved_folder = self.target_folder
        config_path = self.config_path
        root = self.root

        for widget in root.winfo_children():
            widget.destroy()

        importlib.reload(sys.modules["utils"])
        importlib.reload(sys.modules["ui"])

        new_app = sys.modules["ui"].CodePackerApp(root, config_path=config_path)

        # Restore the folder the user had open before reload
        if saved_folder != new_app.target_folder:
            new_app.target_folder = saved_folder
            new_app.lbl_folder.config(text=saved_folder)
            new_app.rescan(init_mode=True)