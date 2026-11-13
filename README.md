#  — High-to-Low Poly Baker for Blender

A lightweight, workflow-focused Blender add-on designed to simplify and speed up **High-to-Low Poly texture baking** in Cycles. Instead of manually creating image textures, wiring unconnected shader nodes, and toggling bake settings for every map, this add-on handles the setup from a single panel in the 3D Viewport.

---

## Features

- **One-Click High-to-Low Baking:** Select your high-poly source mesh(es) and low-poly target mesh to bake surface details cleanly.
- **Automated Image & Node Setup:** Automatically generates target image textures at your chosen resolution and connects/selects the active Image Texture node on the low-poly material.
- **Multi-Map Support:** Bake essential PBR and mesh data maps (Normal, Ambient Occlusion, Diffuse/Albedo, Roughness, Emission, etc.).
- **Ray Distance & Cage Controls:** Easily adjust ray extrusion and max ray distance—or assign a custom cage object—to prevent ray misses and projection artifacts.
- **Resolution & Margin Presets:** Quick selection for common texture sizes (`512x512`, `1024x1024`, `2048x2048`, `4096x4096`) and pixel padding margins.
- **Non-Destructive Workflow:** Preserves your existing material setups while cleanly managing temporary bake nodes and render settings.

---

## Requirements

- **Blender:** `3.6 LTS` or `4.0+` (Cycles Render Engine)
- **OS:** Windows, macOS, or Linux

---

## Installation

1. Download the latest release `.zip` (or the `.py` script) from the [Releases](../../releases) page.
2. Open **Blender** and go to **Edit > Preferences > Add-ons**.
3. Click **Install...** (or **Install from Disk...** in Blender 4.2+) in the top-right corner.
4. Select the downloaded `.zip` or `.py` file and click **Install Add-on**.
5. Enable the checkbox next to **[Addon Name]**.

---

## Usage

1. **Prepare Your Meshes:**
   - Ensure your **Low-Poly** mesh has clean, non-overlapping UVs and an assigned material.
   - Align your **High-Poly** mesh(es) directly over the low-poly mesh in world space.
2. **Open the Add-on Panel:**
   - Press `N` in the **3D Viewport** to open the sidebar and navigate to the **[Panel Tab Name]** tab.
3. **Configure Bake Settings:**
   - Assign your **High-Poly** source object(s) and **Low-Poly** target object.
   - Choose your desired **Texture Resolution** (e.g., `2048x2048`) and **Margin**.
   - Adjust **Extrusion / Ray Distance** (or select a **Cage** mesh) to eliminate projection errors.
   - Select the **Bake Maps** you want to generate.
4. **Bake & Save:**
   - Click **Bake** to run the Cycles bake process.
   - Inspect the generated maps in Blender's **Image Editor** and save them to disk (`Image > Save As` or via the add-on's export path).

---

## Supported Bake Maps

| Map Type | Purpose | Color Space |
| :--- | :--- | :--- |
| **Normal (Tangent)** | Transfers high-poly surface bevels, dents, and micro-detail onto low-poly geometry | Non-Color |
| **Ambient Occlusion (AO)** | Captures crevice shadows and contact darkening | Non-Color |
| **Diffuse / Albedo** | Transfers base color information without lighting influence | sRGB |
| **Roughness** | Transfers surface gloss/matte variation | Non-Color |
| **Emit / ID** | Bakes material color IDs or emissive details for texturing masks | sRGB |

---

## Tips for Clean Bakes

- **Smooth Shading:** Set both high-poly and low-poly meshes to **Shade Smooth** before baking normal maps.
- **UV Padding:** Keep a margin of at least `8px–16px` for `2K` textures to prevent mipmap seam bleeding in game engines.
- **Naming Convention:** Use consistent suffixes (e.g., `Asset_high` and `Asset_low`) when organizing complex multi-part scenes.

---

## License

Distributed under the **GNU General Public License v3.0 (GPL-3.0)** — compatible with Blender's Python API licensing. See `LICENSE` for details.
