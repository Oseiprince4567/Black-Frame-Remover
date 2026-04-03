# -*- coding: utf-8 -*-
"""
Black Frame Remover: QGIS Plugin
Removes black/nodata borders from georeferenced rasters.

Copyright (C) 2026 Prince Osei Boateng
"""

def classFactory(iface):
    from .main import BlackFrameRemover
    return BlackFrameRemover(iface)
