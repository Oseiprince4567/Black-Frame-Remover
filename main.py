# -*- coding: utf-8 -*-
"""
Black Frame Remover - main.py  v1.0.0
All plugin logic in one file: toolbar action, dialog UI, and processing.

FIX v1.1: Added morphological closing to prevent valid dark pixels
along image edges from being incorrectly treated as black border.

Copyright (C) 2026 Prince Osei Boateng
Reach out through email please: oseiboateng93@gmail.com
"""

import os
import numpy as np
from osgeo import gdal
gdal.UseExceptions()

import processing  # QGIS Processing framework

from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider,
    QSpinBox, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox, QGroupBox, QFrame
)
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.core import QgsRasterLayer, QgsProject

plugin_dir = os.path.dirname(__file__)


# ── Background Worker Thread ───────────────────────────────────────────────────

class WorkerThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, input_path, output_path, threshold, closing_size, add_alpha):
        super().__init__()
        self.input_path   = input_path
        self.output_path  = output_path
        self.threshold    = threshold
        self.closing_size = closing_size
        self.add_alpha    = add_alpha

    def run(self):
        self.finished.emit(self._process())

    def _report(self, percent, message):
        self.progress.emit(percent, message)

    def _process(self):
        """
        Step 1  — Build initial mask raster (threshold)
        Step 1b — Morphological closing (THE FIX for pixel loss)
        Step 2  — Polygonize mask → vector polygon
        Step 3  — Clip raster by mask layer + alpha channel
        """
        base             = self.output_path.replace('.tif','').replace('.tiff','')
        temp_mask_raster = base + '_temp_mask.tif'
        temp_mask_vector = base + '_temp_mask.gpkg'
        temp_filtered    = base + '_temp_filtered.gpkg'

        try:
            # ── Step 1: Build initial mask ─────────────────────────────────────
            self._report(5, 'Step 1/3 — Detecting black border pixels...')

            ds = gdal.Open(self.input_path, gdal.GA_ReadOnly)
            if ds is None:
                return {'success': False, 'message': 'Cannot open raster. Check the file path.'}

            geo_transform = ds.GetGeoTransform()
            projection    = ds.GetProjection()
            width, height = ds.RasterXSize, ds.RasterYSize
            n_bands       = ds.RasterCount

            # Pixel is valid if ANY band exceeds threshold
            valid_mask = np.zeros((height, width), dtype=bool)
            for b in range(1, n_bands + 1):
                arr = ds.GetRasterBand(b).ReadAsArray().astype(np.float32)
                valid_mask |= (arr > self.threshold)
            ds = None

            # ── Step 1b: Morphological closing (THE FIX) ───────────────────────
            #
            # The problem: historical aerial images have dark pixels near their
            # edges (dark fields, forests, shadows) whose values are close to 0.
            # A simple threshold incorrectly marks these as "black border" and
            # removes them — eating into the real image content.
            #
            # The fix — morphological closing (dilation then erosion):
            #
            #   DILATION:  expands the True (valid) region outward by closing_size.
            #              This "reaches into" the black border and fills dark holes
            #              inside the image content.
            #
            #   EROSION:   shrinks the expanded region back inward by the same amount.
            #              This restores the outer boundary to roughly its original
            #              position, but now the interior holes are filled.
            #
            # Net result: dark pixels SURROUNDED by valid content stay valid.
            #             Only the true outer black border (no valid neighbours)
            #             is correctly removed.
            #
            # Example: closing_size=21 means a 21x21 pixel neighbourhood.
            # A dark forest pixel 10px inside the image edge will be kept.

            self._report(20, 'Refining mask edges (filling dark holes inside image)...')

            from numpy.lib.stride_tricks import sliding_window_view
            pad = self.closing_size // 2

            # Dilation: pixel becomes True if ANY neighbour is True
            padded  = np.pad(valid_mask, pad, mode='constant', constant_values=False)
            windows = sliding_window_view(padded, (self.closing_size, self.closing_size))
            dilated = windows.any(axis=(-2, -1))

            # Erosion: pixel stays True only if ALL neighbours are True
            padded2  = np.pad(dilated, pad, mode='constant', constant_values=False)
            windows2 = sliding_window_view(padded2, (self.closing_size, self.closing_size))
            closed_mask = windows2.all(axis=(-2, -1))

            # Write cleaned mask as GeoTIFF
            driver  = gdal.GetDriverByName('GTiff')
            mask_ds = driver.Create(temp_mask_raster, width, height, 1, gdal.GDT_Byte)
            mask_ds.SetGeoTransform(geo_transform)
            mask_ds.SetProjection(projection)
            band = mask_ds.GetRasterBand(1)
            band.WriteArray(closed_mask.astype(np.uint8))
            band.SetNoDataValue(0)
            mask_ds.FlushCache()
            mask_ds = None

            # ── Step 2: Polygonize mask ────────────────────────────────────────
            self._report(40, 'Step 2/3 — Building polygon around image content...')

            processing.run('gdal:polygonize', {
                'INPUT':               temp_mask_raster,
                'BAND':                1,
                'FIELD':               'value',
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA':               '',
                'OUTPUT':              temp_mask_vector,
            })

            processing.run('native:extractbyattribute', {
                'INPUT':    temp_mask_vector,
                'FIELD':    'value',
                'OPERATOR': 0,
                'VALUE':    '1',
                'OUTPUT':   temp_filtered,
            })

            # ── Step 3: Clip raster by mask + alpha channel ────────────────────
            self._report(65, 'Step 3/3 — Clipping raster (alpha channel enabled)...')

            mask_source = temp_filtered if os.path.exists(temp_filtered) else temp_mask_vector

            result = processing.run('gdal:cliprasterbymasklayer', {
                'INPUT':           self.input_path,
                'MASK':            mask_source,
                'SOURCE_CRS':      None,
                'TARGET_CRS':      None,
                'TARGET_EXTENT':   None,
                'NODATA':          None,
                'ALPHA_BAND':      self.add_alpha,   # ✅ alpha channel ticked
                'CROP_TO_CUTLINE': True,
                'KEEP_RESOLUTION': True,
                'SET_RESOLUTION':  False,
                'X_RESOLUTION':    None,
                'Y_RESOLUTION':    None,
                'MULTITHREADING':  True,
                'OPTIONS':         'COMPRESS=LZW|TILED=YES',
                'DATA_TYPE':       0,
                'EXTRA':           '',
                'OUTPUT':          self.output_path,
            })

            if not result or not os.path.exists(self.output_path):
                return {'success': False,
                        'message': 'Clip by mask failed. Check output path and disk space.'}

            # ── Cleanup ────────────────────────────────────────────────────────
            self._report(95, 'Cleaning up...')
            for path in [temp_mask_raster, temp_mask_vector, temp_filtered]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

            self._report(100, 'Done!')
            return {
                'success':     True,
                'output_path': self.output_path,
                'message':     f'Black frame removed successfully!\n\nOutput saved to:\n{self.output_path}'
            }

        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}


# ── Dialog Window ──────────────────────────────────────────────────────────────

class BlackFrameRemoverDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface  = iface
        self.worker = None
        self.setWindowTitle('Black Frame Remover')
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel('🗺  Black Frame Remover')
        title.setFont(QFont('Arial', 13, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel('Removes black/nodata borders from georeferenced rasters')
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet('color: #ddd;')
        layout.addWidget(line)

        # ── Input ─────────────────────────────────────────────────────────────
        in_group = QGroupBox('Input Raster')
        in_layout = QVBoxLayout(in_group)
        in_layout.addWidget(QLabel('Paste or browse the georeferenced raster path:'))
        in_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText('e.g. C:/projects/georef_image.tif')
        browse_in = QPushButton('Browse...')
        browse_in.clicked.connect(self._browse_input)
        in_row.addWidget(self.input_edit)
        in_row.addWidget(browse_in)
        in_layout.addLayout(in_row)
        layout.addWidget(in_group)

        # ── Settings ──────────────────────────────────────────────────────────
        set_group = QGroupBox('Settings')
        set_layout = QVBoxLayout(set_group)

        # Threshold
        set_layout.addWidget(QLabel(
            'Black threshold: pixels at or below this value are treated as border:'))
        thresh_row = QHBoxLayout()
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(15)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setValue(15)
        self.threshold_spin.setSuffix('  (0–100)')
        self.threshold_slider.valueChanged.connect(self.threshold_spin.setValue)
        self.threshold_spin.valueChanged.connect(self.threshold_slider.setValue)
        thresh_row.addWidget(self.threshold_slider)
        thresh_row.addWidget(self.threshold_spin)
        set_layout.addLayout(thresh_row)
        hint_row = QHBoxLayout()
        hint_row.addWidget(QLabel('0 = pure black only'))
        hint_row.addStretch()
        hint_row.addWidget(QLabel('100 = aggressive'))
        set_layout.addLayout(hint_row)

        set_layout.addSpacing(8)

        # Edge smoothing (morphological closing) ← THE FIX
        set_layout.addWidget(QLabel(
            'Edge smoothing: prevents dark image pixels near edges from being removed:\n'
            '(increase if dark fields or forests near the border are incorrectly cut)'))
        closing_row = QHBoxLayout()
        self.closing_slider = QSlider(Qt.Horizontal)
        self.closing_slider.setRange(1, 51)
        self.closing_slider.setSingleStep(2)
        self.closing_slider.setValue(21)
        self.closing_spin = QSpinBox()
        self.closing_spin.setRange(1, 51)
        self.closing_spin.setValue(21)
        self.closing_spin.setSuffix('  px')
        self.closing_slider.valueChanged.connect(self.closing_spin.setValue)
        self.closing_spin.valueChanged.connect(self.closing_slider.setValue)
        closing_row.addWidget(self.closing_slider)
        closing_row.addWidget(self.closing_spin)
        set_layout.addLayout(closing_row)
        hint_row2 = QHBoxLayout()
        hint_row2.addWidget(QLabel('1 = no smoothing'))
        hint_row2.addStretch()
        hint_row2.addWidget(QLabel('51 = fill large dark areas'))
        set_layout.addLayout(hint_row2)

        set_layout.addSpacing(4)
        self.alpha_check = QCheckBox('Add alpha channel (transparent background)')
        self.alpha_check.setChecked(True)
        set_layout.addWidget(self.alpha_check)
        layout.addWidget(set_group)

        # ── Output ────────────────────────────────────────────────────────────
        out_group = QGroupBox('Output')
        out_layout = QVBoxLayout(out_group)
        out_layout.addWidget(QLabel('Save cleaned raster as:'))
        out_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText('e.g. C:/projects/georef_image_clean.tif')
        browse_out = QPushButton('Browse...')
        browse_out.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_edit)
        out_row.addWidget(browse_out)
        out_layout.addLayout(out_row)
        self.load_check = QCheckBox('Load result into QGIS after processing')
        self.load_check.setChecked(True)
        out_layout.addWidget(self.load_check)
        layout.addWidget(out_group)

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel('')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet('color: #555; font-size: 11px;')
        layout.addWidget(self.status_label)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton('▶  Remove Black Frame')
        self.run_btn.setFixedHeight(36)
        self.run_btn.setStyleSheet(
            'QPushButton { background:#2e7d32; color:white; font-weight:bold;'
            'border-radius:4px; font-size:13px; }'
            'QPushButton:hover { background:#1b5e20; }'
            'QPushButton:disabled { background:#aaa; }'
        )
        self.run_btn.clicked.connect(self._run)
        close_btn = QPushButton('Close')
        close_btn.setFixedHeight(36)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Georeferenced Raster', '',
            'Raster Files (*.tif *.tiff *.img *.jpg *.png *.vrt);;All Files (*)'
        )
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text():
                base, ext = os.path.splitext(path)
                self.output_edit.setText(base + '_clean' + (ext if ext else '.tif'))

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Output Raster', '', 'GeoTIFF (*.tif *.tiff)'
        )
        if path:
            if not path.lower().endswith(('.tif', '.tiff')):
                path += '.tif'
            self.output_edit.setText(path)

    def _run(self):
        input_path  = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()

        if not input_path or not os.path.exists(input_path):
            QMessageBox.warning(self, 'Missing Input',
                                'Please provide a valid input raster path.')
            return
        if not output_path:
            QMessageBox.warning(self, 'Missing Output',
                                'Please specify an output file path.')
            return
        if not output_path.lower().endswith(('.tif', '.tiff')):
            output_path += '.tif'

        # Closing size must be odd
        closing_size = self.closing_spin.value()
        if closing_size % 2 == 0:
            closing_size += 1

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText('Starting...')

        self.worker = WorkerThread(
            input_path   = input_path,
            output_path  = output_path,
            threshold    = self.threshold_spin.value(),
            closing_size = closing_size,
            add_alpha    = self.alpha_check.isChecked(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, result):
        self.run_btn.setEnabled(True)
        self.progress_bar.setValue(100 if result['success'] else 0)
        if result['success']:
            self.status_label.setText('✅ Completed successfully!')
            if self.load_check.isChecked():
                name  = os.path.splitext(os.path.basename(result['output_path']))[0]
                layer = QgsRasterLayer(result['output_path'], name)
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
            QMessageBox.information(self, 'Success', result['message'])
        else:
            self.status_label.setText('❌ Processing failed.')
            QMessageBox.critical(self, 'Error', result['message'])


# ── Plugin Class ───────────────────────────────────────────────────────────────

class BlackFrameRemover:

    def __init__(self, iface):
        self.iface  = iface
        self.action = None
        self.dlg    = None

    def initGui(self):
        icon_path = os.path.join(plugin_dir, 'icon.png')
        self.action = QAction(
            QIcon(icon_path), 'Remove Black Frame', self.iface.mainWindow()
        )
        self.action.setToolTip('Remove black/nodata border from georeferenced raster')
        self.action.triggered.connect(self.run)
        self.iface.addPluginToRasterMenu('&Black Frame Remover', self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginRasterMenu('&Black Frame Remover', self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        if self.dlg is None:
            self.dlg = BlackFrameRemoverDialog(self.iface)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
