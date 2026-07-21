"""
run.py — entry point for NotebookLM Packager
Usage: python run.py
"""

import os
import sys
import tkinter as tk

from interface.main_window import CodePackerApp

# When frozen (PyInstaller onefile), __file__ resolves inside the ephemeral
# _MEIPASS extraction folder — anchor to the .exe's own folder instead so
# config.ini / history.json persist across runs.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(APP_DIR, "config.ini")

if __name__ == "__main__":
    root = tk.Tk()
    app = CodePackerApp(root, config_path=CONFIG_PATH)
    root.mainloop()