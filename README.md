# Black Frame Remover

**QGIS Plugin for Black Frame Removal in Georeferenced Imagery**

Plugin that automatically removes black/nodata borders from georeferenced rasters using footprint detection and edge-safe morphology; better than standard NoData transparency workflows.

**Tech Stack:** PyQGIS · GDAL · NumPy | **Open Source** | **Raster Processing**

## 🎯 01 / Problem

**The black border problem in GIS**

After georeferencing scanned maps and historical aerial photos, output rasters contain black frames around valid content:

- **⬛ Hides basemaps** – Blocks visual QA/context checking
- **⚙️ Complicates mosaicking** – Causes seams, prevents clean blending
- **🕳️ Creates holes** – Standard NoData removes legitimate dark pixels

## 🔧 02 / Solution

**Footprint detection + edge-safe morphology**

Instead of blindly making dark pixels transparent, the plugin:

1. **Threshold Detection** – Identifies border pixels (0–100 adjustable)
2. **Edge-Safe Refinement** – Morphological closing protects forests/shadows/water near edges
3. **Footprint Creation** – Converts mask to true polygon geometry
4. **Clip & Export** – Clips to footprint + alpha band → clean GeoTIFF

| Criterion | Standard NoData=0 | Black Frame Remover |
|-----------|------------------|-------------------|
| Removes outer black border | ✓ Yes | **✓ Yes** |
| Preserves dark interior pixels | ✗ Creates holes | **✓ Fully preserved** |
| Handles shadows/dark vegetation | ✗ Removed | **✓ Edge morphology** |
| Footprint-based clipping | ✗ Pixel value only | **✓ True polygon** |
| Adjustable sensitivity | ✗ Fixed | **✓ 0–100 user control** |
| Alpha band export | ~ Renderer-dependent | **✓ Fused into GeoTIFF** |

## 🖥️ 03 / Plugin Interface

**One-click workflow:**
Input Raster → Threshold (0-100) → Edge Smoothing (1-51px) → Alpha Band → Output GeoTIFF

- **🎚️ Black Threshold**: 0=pure black, 100=aggressive (default: 15)
- **🛡️ Edge Smoothing**: Prevents edge pixel loss (default: 1px)
- **⚡ Auto-load**: Result loads into QGIS canvas immediately

## 🎯 04 / Use Cases

1. **Historical Aerial Imagery Cleanup** – Remove frames without destroying dark fields/forests
2. **Scanned Map Preparation** – Transparent borders for digitization
3. **Raster Overlays** – Clean historical baselayers for change detection
4. **Map Layouts & Mosaics** – Publication-ready tiles


## 📥 Installation

1. Download from [QGIS Plugins Repository](https://plugins.qgis.org)
2. Plugins → Manage → Installed → Enable "Black Frame Remover"
3. Raster menu → **Remove Black Frame**

## 📚 Repository

[https://github.com/Oseiprince4567/Black-Frame-Remover]

**Author:** Prince Osei Boateng  
**Contact:** oseiboateng93@gmail.com  (https://oseiprince4567.github.io/Portfolio/blackframe.html)
