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
├── run.py        # Entry point — สร้าง Tk root แล้วส่ง config_path ให้ CodePackerApp
├── ui.py         # CodePackerApp — UI ทั้งหมด, watchdog, drag-select, clipboard export
├── utils.py      # Pure functions — config parsing, ignore rules, file scanning
└── config.ini    # ตั้งค่า ignore patterns, extensions, main-list
```

## Architecture

### `run.py`
- Entry point เดียว — สร้าง `tk.Tk()` root แล้วส่ง `CONFIG_PATH` ให้ `CodePackerApp`

### `ui.py` — `CodePackerApp`
ส่วนประกอบหลัก:
- **`_ChangeHandler`** — Watchdog debounced (500ms) ตรวจไฟล์เปลี่ยนแปลงใน real-time
- **`_reload_config()`** — โหลด config.ini ใหม่ทุกครั้งที่ rescan
- **`rescan(init_mode)`** — สแกนไฟล์ใหม่, รักษา state การเลือกเดิม (ยกเว้น init)
- **`apply_filter()`** — กรองตาม search query แล้วสร้าง Treeview ใหม่
- **`refresh_checkbox_symbols()`** — อัปเดต UI สัญลักษณ์ ☑/☐/☒ และสีพื้นหลัง
- **`process_and_copy()`** — export Markdown (TOC + fenced code blocks) ไป clipboard

State หลัก:
```python
self.file_states: dict[str, bool]          # rel_path → selected
self.node_to_path: dict[str, tuple[str, bool]]  # tree node id → (path, is_dir)
self.path_to_node: dict[str, str]          # path → tree node id
```

### `utils.py`
Pure functions ไม่มี side effects:
- `load_config()` / `parse_csv_option()` — อ่าน config.ini
- `get_ignore_list()` / `get_supported_extensions()` / `get_main_keywords()` / `get_main_paths()`
- `should_ignore(rel_path, ignore_list)` — ใช้ `fnmatch` รองรับ glob patterns
- `is_in_main_list(rel_path, keywords, paths)` — basename match หรือ path prefix match
- `scan_files(root_folder, ignore_list, extensions)` — `os.walk` + prune ignored dirs

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
- ไม่มี `__init__.py` — ไม่ใช่ Blender addon package แต่เป็น standalone script
