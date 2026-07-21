"""
core/packer_core.py — business logic for NotebookLM Packager
No Tkinter here — pure state & operations, consumed by interface/main_window.py
"""

import os
import subprocess

from data.history import add_to_history, load_history
from data.utils import (
    get_default_folder,
    get_ignore_list,
    get_main_keywords,
    get_main_paths,
    get_supported_extensions,
    is_in_main_list,
    load_config,
    scan_files,
)


class PackerCore:
    def __init__(self, config_path: str, app_base_dir: str):
        self.config_path = config_path
        self.app_base_dir = app_base_dir
        self.reload_config()

        default = get_default_folder(load_config(self.config_path))
        self.target_folder = os.path.abspath(default if default and os.path.isdir(default) else ".")

        self.all_files: list[tuple[str, str]] = []
        self.file_states: dict[str, bool] = {}   # rel_path → selected

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def reload_config(self):
        cfg = load_config(self.config_path)
        self.ignore_list = get_ignore_list(cfg)
        self.supported_extensions = get_supported_extensions(cfg)
        self.main_keywords = get_main_keywords(cfg)
        self.main_paths = get_main_paths(cfg)

    def is_main(self, rel_path: str) -> bool:
        return is_in_main_list(rel_path, self.main_keywords, self.main_paths)

    # ------------------------------------------------------------------
    # Folder history (Latest Path)
    # ------------------------------------------------------------------

    def get_history(self) -> list[str]:
        return load_history(self.app_base_dir)

    def remember_folder(self, folder: str) -> list[str]:
        return add_to_history(self.app_base_dir, folder)

    # ------------------------------------------------------------------
    # Scanning & filtering
    # ------------------------------------------------------------------

    def rescan(self, init_mode: bool = False) -> int:
        old_states = dict(self.file_states)
        self.file_states.clear()
        self.all_files = scan_files(self.target_folder, self.ignore_list, self.supported_extensions)

        for rel, _ in self.all_files:
            if self.is_main(rel):
                # MAIN files are ALWAYS selected — user cannot deselect them
                self.file_states[rel] = True
            elif init_mode:
                self.file_states[rel] = False
            else:
                self.file_states[rel] = old_states.get(rel, False)

        return len(self.all_files)

    def filtered_files(self, query: str) -> list[tuple[str, str]]:
        query = query.lower().strip()
        if not query:
            return list(self.all_files)
        return [
            item for item in self.all_files
            if query in item[0].lower() or query in os.path.basename(item[0]).lower()
        ]

    # ------------------------------------------------------------------
    # Toggle helpers (respect locked/MAIN files)
    # ------------------------------------------------------------------

    def set_file_state(self, rel_path: str, state: bool):
        """Set selection state — MAIN files are always forced True."""
        self.file_states[rel_path] = True if self.is_main(rel_path) else state

    def get_nested_files(self, dir_path: str) -> list[str]:
        return [f for f in self.file_states if f.startswith(dir_path + os.sep)]

    def select_all(self):
        for path in self.file_states:
            self.set_file_state(path, True)

    def deselect_all(self):
        for path in self.file_states:
            self.set_file_state(path, False)   # locked files stay True internally

    def select_only_main(self):
        for path in self.file_states:
            self.set_file_state(path, self.is_main(path))

    def select_git_changes(self) -> tuple[str, int]:
        """Returns (kind, count) — kind in {'ok', 'clean', 'no_git', 'not_repo'}."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.target_folder,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=True,
            )
        except FileNotFoundError:
            return "no_git", 0
        except subprocess.CalledProcessError:
            return "not_repo", 0

        git_files = [
            line[3:].strip().replace("/", os.sep)
            for line in result.stdout.splitlines()
            if len(line) > 3
        ]
        if not git_files:
            return "clean", 0

        count = 0
        for path in self.file_states:
            state = path in git_files
            self.set_file_state(path, state)
            if state:
                count += 1
        return "ok", count

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def build_markdown(self) -> tuple[str, int]:
        """Build the clipboard Markdown payload. Returns (text, selected_count)."""
        all_files_snap = list(self.all_files)
        file_states_snap = dict(self.file_states)
        selected = [(r, fp) for r, fp in all_files_snap if file_states_snap.get(r, False)]

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
        return full_text, len(selected)
