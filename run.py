"""
run.py — entry point for NotebookLM Packager
Usage: python run.py
"""

import os
import tkinter as tk

from ui import CodePackerApp

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")

if __name__ == "__main__":
    root = tk.Tk()
    app = CodePackerApp(root, config_path=CONFIG_PATH)
    root.mainloop()