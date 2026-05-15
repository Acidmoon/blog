"""Pluggable blog modules.

Each child package can expose a manifest.py with a MODULE dict. The loader keeps
module registration centralized so app.py and templates/index.html do not need to
change for every new feature.
"""
