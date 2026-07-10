"""
utils.py — shared helpers for NotebookLM Packager
Handles: config loading, ignore rules, main-list matching, file scanning
"""

import configparser
import fnmatch
import os

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(allow_no_value=True)
    cfg.read(config_path, encoding="utf-8")
    return cfg


def parse_csv_option(cfg: configparser.ConfigParser, section: str, key: str) -> list[str]:
    """Return a list of stripped, non-empty strings from a comma-separated config value."""
    raw = cfg.get(section, key, fallback="")
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_ignore_list(cfg: configparser.ConfigParser) -> list[str]:
    return parse_csv_option(cfg, "ignore", "patterns")


def get_supported_extensions(cfg: configparser.ConfigParser) -> tuple[str, ...]:
    exts = parse_csv_option(cfg, "extensions", "supported")
    return tuple(exts) if exts else (".py",)


def get_default_folder(cfg: configparser.ConfigParser) -> str:
    return cfg.get("defaults", "target_folder", fallback="").strip()


def get_main_keywords(cfg: configparser.ConfigParser) -> list[str]:
    return parse_csv_option(cfg, "main_list_keywords", "keywords")


def get_main_paths(cfg: configparser.ConfigParser) -> list[str]:
    return parse_csv_option(cfg, "main_list_paths", "paths")


# ---------------------------------------------------------------------------
# Ignore / main-list logic
# ---------------------------------------------------------------------------

def should_ignore(rel_path: str, ignore_list: list[str]) -> bool:
    rel_unix = rel_path.replace(os.sep, "/")
    base = os.path.basename(rel_path)
    for pattern in ignore_list:
        if (
            fnmatch.fnmatch(rel_unix, pattern)
            or fnmatch.fnmatch(base, pattern)
            or rel_unix.startswith(pattern.rstrip("/") + "/")
        ):
            return True
    return False


def is_in_main_list(
    rel_path: str,
    main_keywords: list[str],
    main_paths: list[str],
) -> bool:
    """
    Return True if *rel_path* matches any main-list rule:
      • main_keywords  — basename match (case-sensitive)
      • main_paths     — exact rel-path match OR folder-prefix match
    """
    base = os.path.basename(rel_path)

    # Keyword match (basename)
    for kw in main_keywords:
        if base == kw:
            return True

    # Path / folder match
    for mp in main_paths:
        mp_os = mp.replace("/", os.sep).replace("\\", os.sep)
        if rel_path == mp_os or rel_path.startswith(mp_os + os.sep):
            return True

    return False


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------

def scan_files(
    root_folder: str,
    ignore_list: list[str],
    supported_extensions: tuple[str, ...],
) -> list[tuple[str, str]]:
    """
    Walk *root_folder* and return a sorted list of (rel_path, full_path) tuples
    for every non-ignored file whose extension is in *supported_extensions*.
    """
    results: list[tuple[str, str]] = []

    for dirpath, dirs, files in os.walk(root_folder):
        # Prune ignored directories in-place so os.walk skips them
        dirs[:] = [
            d for d in dirs
            if not should_ignore(
                os.path.relpath(os.path.join(dirpath, d), root_folder),
                ignore_list,
            )
        ]

        for filename in files:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root_folder)

            if not should_ignore(rel_path, ignore_list) and filename.lower().endswith(supported_extensions):
                results.append((rel_path, full_path))

    results.sort(key=lambda x: x[0])
    return results