"""Põe a pasta do projeto no sys.path (os módulos da ilha ficam um nível acima)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import gi  # noqa: E402

# o app usa GTK 3: fixa as versões antes de qualquer módulo importar gi.repository
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
