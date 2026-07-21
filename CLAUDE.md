# ScriptReader — NotebookLM Packager

เครื่องมือ GUI (Tkinter) สำหรับเลือกไฟล์ในโปรเจกต์แล้วคัดลอกเนื้อหาทั้งหมดเป็น Markdown ไปยัง Clipboard เพื่อป้อนเข้า NotebookLM หรือ AI อื่น ๆ

## วิธีรัน

```bash
python run.py
```

ต้องการ Python 3.10+ (ใช้ `str | None` type union)  
`pyperclip` และ `watchdog` ติดตั้งอัตโนมัติเมื่อรันครั้งแรก (via `pip install --user`)

## โครงสร้างไฟล์

```
ScriptReader/
├── run.py                  # Entry point — สร้าง Tk root แล้วส่ง config_path ให้ CodePackerApp
├── interface/
│   └── main_window.py      # CodePackerApp — Tkinter widgets, event bindings, treeview rendering
├── core/
│   └── packer_core.py      # PackerCore — business logic, state (ไม่มี Tkinter import)
├── data/
│   ├── utils.py            # Pure functions — config parsing, ignore rules, file scanning
│   └── history.py          # อ่าน/เขียน history.json (Latest Path list)
├── config.ini               # ตั้งค่า ignore patterns, extensions, main-list
└── history.json             # (gitignored) รายการโฟลเดอร์ล่าสุดที่เปิด — สร้างอัตโนมัติ
```

ไม่มี `__init__.py` ในแต่ละแพ็กเกจ — อาศัย Python namespace packages (PEP 420) เพราะ root ของ ScriptReader อยู่บน `sys.path` อยู่แล้วตอนรัน `python run.py`

## Architecture

### `run.py`
- Entry point เดียว — สร้าง `tk.Tk()` root แล้วส่ง `CONFIG_PATH` ให้ `CodePackerApp` (import จาก `interface.main_window`)

### `core/packer_core.py` — `PackerCore`
Business logic ล้วน ๆ ไม่แตะ Tkinter เลย เพื่อให้ทดสอบ/reload แยกจาก UI ได้:
- **`reload_config()`** — โหลด config.ini ใหม่
- **`rescan(init_mode)`** — สแกนไฟล์ใหม่ (`data.utils.scan_files`), รักษา state การเลือกเดิม (ยกเว้น init)
- **`filtered_files(query)`** — กรองรายการไฟล์ตาม search query
- **`set_file_state()` / `get_nested_files()` / `select_all()` / `deselect_all()` / `select_only_main()` / `select_git_changes()`** — toggle helpers (เคารพ MAIN-locked files เสมอ)
- **`build_markdown()`** — สร้าง Markdown (TOC + fenced code blocks) สำหรับ clipboard
- **`get_history()` / `remember_folder()`** — จัดการ Latest Path history ผ่าน `data.history`

State หลัก (`PackerCore`):
```python
self.target_folder: str
self.all_files: list[tuple[str, str]]
self.file_states: dict[str, bool]          # rel_path → selected
```

### `interface/main_window.py` — `CodePackerApp`
UI ล้วน ๆ — ถือ `self.core: PackerCore` แล้วเรียกใช้ทุก business logic ผ่านมัน:
- **`apply_filter()`** — เรียก `core.filtered_files()` แล้วสร้าง Treeview ใหม่
- **`refresh_checkbox_symbols()`** — อัปเดต UI สัญลักษณ์ ☑/☐/☒ และสีพื้นหลัง
- **`on_tree_click()`** — เช็ค `tree.identify_element()` ก่อนเสมอ ถ้าคลิกโดน indicator (ลูกศรกาง/หุบ) จะ `return` ทันที ไม่ toggle selection — ป้องกันบั๊ก "หุบ/เปิด section แล้วดันไป select"
- **`_switch_folder()` / `_on_history_selected()` / `_refresh_history_values()`** — จัดการ dropdown ประวัติโฟลเดอร์ล่าสุด (ข้างช่องเลือกโฟลเดอร์)
- **`process_and_copy()`** — เรียก `core.build_markdown()` ใน background thread แล้ว copy ไป clipboard

State หลัก (UI เท่านั้น):
```python
self.node_to_path: dict[str, tuple[str, bool]]  # tree node id → (path, is_dir)
self.path_to_node: dict[str, str]               # path → tree node id
```

### `data/utils.py`
Pure functions ไม่มี side effects:
- `load_config()` / `parse_csv_option()` — อ่าน config.ini
- `get_ignore_list()` / `get_supported_extensions()` / `get_main_keywords()` / `get_main_paths()`
- `should_ignore(rel_path, ignore_list)` — ใช้ `fnmatch` รองรับ glob patterns
- `is_in_main_list(rel_path, keywords, paths)` — basename match หรือ path prefix match
- `scan_files(root_folder, ignore_list, extensions)` — `os.walk` + prune ignored dirs

### `data/history.py`
- `load_history()` / `save_history()` / `add_to_history()` — persist รายการโฟลเดอร์ล่าสุด (MRU, สูงสุด 15 รายการ) ลง `history.json` ข้าง `config.ini`

## config.ini

```ini
[ignore]
patterns = .git, __pycache__, node_modules, venv, ...   # glob patterns คั่นด้วย comma

[extensions]
supported = .py, .rs, .json, .md, ...   # นามสกุลที่จะสแกน

[main_list_keywords]
keywords = __init__.py, CLAUDE.md, README.md   # ชื่อไฟล์ที่ auto-select และล็อก

[main_list_paths]
paths = docs   # relative path prefix ที่ auto-select และล็อก
```

**MAIN files** — ไฟล์ที่ตรง `main_list_keywords` หรือ `main_list_paths` จะ:
- แสดงเป็น `🔒⭐ [MAIN]` สีเหลือง
- ถูกเลือกเสมอ ผู้ใช้ยกเลิกไม่ได้
- `_set_file_state()` บังคับ `True` ให้ไฟล์เหล่านี้เสมอ

## ฟีเจอร์หลัก

| ฟีเจอร์ | รายละเอียด |
|---------|-----------|
| Drag-select | ลากเมาส์บน Treeview เพื่อ toggle หลายไฟล์พร้อมกัน |
| Search filter | กรอง real-time ตาม path หรือชื่อไฟล์ |
| Select All / Deselect All / MAIN only | ปุ่มลัดเลือกไฟล์ |
| Git Changes | `git status --porcelain` — เลือกเฉพาะไฟล์ที่แก้ไขใน working tree |
| Watchdog | ตรวจ filesystem อัตโนมัติ rescan เมื่อไฟล์เปลี่ยน |
| Clipboard export | Markdown มี TOC + fenced code block พร้อม syntax hint |
| Latest Path history | Dropdown ข้างช่องเลือกโฟลเดอร์ — จำโฟลเดอร์ล่าสุดที่เคยเปิด (MRU, สูงสุด 15) ลง `history.json` |

## Output format (Clipboard)

```markdown
# 🧠 Knowledge Base: <folder-name>
---
## 📁 สารบัญโครงสร้างไฟล์ทั้งหมด
* ☑ [path/to/file.py](#...)
* ☐ ~~path/to/other.py~~ *(ไม่ได้เลือกคัดลอก)*
---
<a name="anchor"></a>
## 📄 File: file.py
**Path:** `path/to/file.py`
```py
<file content>
```
---
```

## Dependencies

| Package | ใช้ทำอะไร |
|---------|----------|
| `tkinter` | GUI (stdlib) |
| `watchdog` | Filesystem monitoring |
| `pyperclip` | Cross-platform clipboard |
| `configparser` | อ่าน config.ini (stdlib) |
| `fnmatch` | Glob pattern matching (stdlib) |

## หมายเหตุสำคัญ

- Watchdog callback วิ่งใน thread แยก — ต้องใช้ `root.after(0, ...)` ส่งงานกลับ Tk main thread เสมอ
- `dirs[:] = [...]` ใน `scan_files` — prune in-place เพื่อให้ `os.walk` ข้าม ignored dirs
- Directory toggle: คลิกโฟลเดอร์จะ toggle ไฟล์ทั้งหมดข้างใน (ยกเว้น MAIN files)
- `on_tree_click()` เช็ค `tree.identify_element(x, y)` ก่อนเสมอ — ถ้าคลิกโดนลูกศร indicator (กาง/หุบ) จะ `return` ทันทีโดยไม่ toggle selection (เดิมมีบั๊กที่คลิกกาง/หุบ section แล้วดันไป select ไฟล์ข้างในด้วย)
- ไม่มี `__init__.py` ในแพ็กเกจ `interface/`, `core/`, `data/` — ใช้ namespace packages (PEP 420) เพราะ root โปรเจกต์อยู่บน `sys.path` อยู่แล้วตอนรัน `python run.py`
- `interface/` ต้องไม่มี business logic (การ toggle state, markdown building, git, history) — ทุกอย่างต้องอยู่ใน `core/packer_core.py` เพื่อให้ reload/ทดสอบแยกจาก UI ได้
