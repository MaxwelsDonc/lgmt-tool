"""Sphinx configuration for the LGMT docs."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "LGMT"
copyright = "2026, LGMT authors"
author = "LGMT authors"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

autosummary_generate = True
autodoc_member_order = "bysource"
autoclass_content = "both"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = ["_templates"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    # design assets that live alongside the Sphinx sources (README links
    # to them); they are not part of the documentation build
    "*.md",
    "*.png",
    "*.tex",
]

html_theme = "furo"
html_title = "LGMT"
html_static_path = []
