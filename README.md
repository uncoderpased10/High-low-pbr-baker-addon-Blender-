# High-Low PBR Baker Pro

### Professional High-to-Low Poly Baking for Blender

**High-Low PBR Baker Pro** is a workflow-focused Blender add-on designed to simplify and automate high-to-low poly texture baking using the Cycles render engine.

It brings mesh detection, intelligent cage generation, texture configuration, multi-channel PBR baking, and automatic material setup into one convenient panel inside Blender's 3D Viewport.

Whether you're baking detailed sculpted models onto optimized game-ready meshes or preparing assets for real-time rendering, High-Low PBR Baker Pro helps streamline the process.

---

## ✨ Features

### 1. Automatic High-Poly & Low-Poly Detection
- Automatically detect high-poly and low-poly objects from your current selection.
- Identify meshes using polygon counts.
- Automatically assign the highest-polygon mesh as the High-Poly source and the lowest-polygon mesh as the Low-Poly target.
- Support for single-object and collection-based High-Poly sources.
- Display polygon counts for both source and target meshes.

### 2. Smart BVH Auto-Cage System
- Intelligent cage-distance estimation using BVH spatial queries.
- Automatically calculate cage extrusion based on surface geometry.
- Calculate maximum ray distance to help prevent unwanted projection from distant surfaces.
- Adjustable cage safety margin.
- Smooth envelope cage generation.
- Live cage preview in the 3D Viewport.
- Manual extrusion and ray-distance controls for additional precision.

### 3. Automatic UV Unwrapping
- Built-in Smart UV Unwrap functionality.
- Automatically generate UV islands for the Low-Poly target.
- Detect missing UV maps and provide a quick-unwrapping option.

### 4. Multi-Channel PBR Baking

Bake individual maps or multiple enabled channels in one automated operation.

| Map | Purpose |
|---|---|
| Normal | Transfer high-poly surface details to low-poly geometry. |
| Diffuse | Bake base-color information. |
| Roughness | Transfer surface roughness variations. |
| Metallic | Bake metallic information. |
| Ambient Occlusion | Capture crevice and contact shading. |
| Emission | Bake emissive information. |
| Material ID | Generate material identification maps. |

### 5. Normal Map Configuration
- Tangent-space normal map baking.
- OpenGL (+Y) normal convention.
- DirectX (-Y) normal convention.
- Optional roughness-to-glossiness inversion.

### 6. Flexible Texture Resolution & Quality
Choose from multiple texture resolutions:

- 512 × 512
- 1024 × 1024 (1K)
- 2048 × 2048 (2K)
- 4096 × 4096 (4K)
- 8192 × 8192 (8K)

Additional controls:
- Adjustable UV padding and pixel margins.
- 1x and 2x anti-aliasing options.
- Configurable Cycles bake samples.
- Separate Ambient Occlusion sample settings.

### 7. Crash-Shield & Compute Options
- Optional Crash-Shield processing.
- Memory cleanup between bake passes.
- Viewport shader isolation during baking.
- Automatic GPU-to-CPU fallback option.
- CPU Safe Mode for memory-constrained systems.

These options are designed to improve stability when working with demanding baking scenes. Actual performance depends on scene complexity and available hardware.

### 8. Automatic PBR Material Setup
- Automatically generate a Principled BSDF-based material.
- Connect generated texture maps to the material when supported by the baking workflow.
- Automatically assign the generated material to the Low-Poly target.

### 9. Flexible Texture Export
Save generated texture maps directly to disk.

Supported output formats:
- PNG
- 16-bit OpenEXR
- TGA

Additional options:
- 8-bit and 16-bit output settings where supported.
- Custom output directory.
- Automatic texture naming using the selected base name.
- Save-to-disk toggle.

### 10. One-Click Baking Workflow
- Bake individual PBR channels.
- Bake all enabled channels in one operation.
- View the latest baking status directly in the add-on panel.
- Manage mesh targets, cage configuration, baking settings, and output from one interface.

---

## 🖥️ Interface

The add-on is accessible directly from:

**Blender 3D Viewport → Sidebar (N) → PBR Baker**

The interface is organized into five sections:

1. Mesh Targets
2. Smart BVH Auto-Cage
3. Bake Settings & Crash-Shield
4. PBR Channels
5. Output & Material Setup

---

## ⚙️ Requirements

- Blender: 5.2 (declared in the add-on's `bl_info` metadata).
- Render Engine: Cycles.
- Operating Systems: Windows, macOS, and Linux.
- A properly prepared High-Poly source mesh.
- A Low-Poly target mesh with suitable UV coordinates.

**Hardware:** GPU acceleration is optional. CPU Safe Mode is available as an alternative.

---

## 📥 Installation

### Method 1: Install from ZIP

1. Download the latest release from the GitHub Releases page.
2. Open Blender.
3. Navigate to Edit → Preferences.
4. Open the Add-ons section.
5. Click Install from Disk.
6. Select the downloaded add-on ZIP.
7. Complete the installation and enable High-Low PBR Baker Pro.

### Download

[Download the Latest Release](https://github.com/uncoderpased10/High-low-pbr-baker-addon-Blender-/releases/latest)

---

## 🚀 How to Use

### Step 1: Prepare Your Meshes

- Create or import your High-Poly model.
- Prepare the corresponding Low-Poly model.
- Ensure both models are aligned correctly in world space.
- Make sure the Low-Poly target has a suitable UV map and material.

### Step 2: Open the Add-on

- Move your cursor over the 3D Viewport.
- Press `N` to open the Sidebar.
- Select the **PBR Baker** tab.

### Step 3: Assign Mesh Targets

You have two High-Poly source modes:

- Single Object: Select one High-Poly mesh.
- Collection: Select a collection containing multiple High-Poly mesh objects.

Assign your Low-Poly target.

Alternatively, select your meshes and click **Auto-Detect High & Low**.

### Step 4: Configure Smart BVH Auto-Cage

- Enable Smart BVH Auto-Cage.
- Adjust the cage safety margin.
- Click Detect Cage to calculate extrusion and maximum ray distance.
- Use Preview Cage to inspect the generated envelope.
- Adjust extrusion and ray distance manually if required.

### Step 5: Configure Baking Settings

Choose your:
- Texture resolution.
- Base texture name.
- UV padding margin.
- Bake samples.
- Anti-aliasing quality.
- Normal map convention.
- Crash-Shield setting.
- Compute device mode.

### Step 6: Select PBR Channels

Enable the maps you want to bake:

- Diffuse
- Normal
- Roughness
- Metallic
- Ambient Occlusion
- Emission
- Material ID

Use the individual Bake buttons for specific maps, or select **Bake ALL Maps**.

### Step 7: Configure Output

Choose:
- Automatic PBR material generation.
- Texture export.
- Output directory.
- Image format.
- Bit depth.

### Step 8: Bake

Click **Bake ALL Maps**.

Once the process completes, inspect the generated maps and material in Blender.

---

## 💡 Tips for Better Baking Results

- Ensure the High-Poly and Low-Poly models are correctly aligned.
- Use clean, non-overlapping UV islands.
- Check cage coverage before starting expensive baking operations.
- Adjust ray distance carefully to prevent projection errors.
- Use sufficient UV padding to reduce texture bleeding.
- Use appropriate normal conventions for your target application.
- Use CPU Safe Mode if GPU memory becomes a limitation.
- Test your settings with a smaller texture resolution before attempting large bakes.

**Note:** Auto-Cage and Crash-Shield are assistance features, not guarantees against every projection error, memory limitation, or Blender crash. Results depend on geometry, UV layout, materials, and hardware.

---

## 📁 Project Structure

```text
High-Low-PBR-Baker-Pro/
│
├── __init__.py
│
├── blender_manifest.toml
│
├── core/
│   ├── auto_cage.py
│   └── baker_engine.py
│
├── ui/
│   └── panel.py
│
└── README.md
```

---

## 🔄 Version History

### Version 1.0.2

- High-Low PBR Baker Pro initial public release.
- Automatic High-Poly and Low-Poly detection.
- Smart BVH Auto-Cage system.
- Cage preview functionality.
- Smart UV Unwrap.
- Seven PBR baking channels.
- Normal map convention controls.
- Automated PBR material setup.
- Crash-Shield and compute device options.
- Multiple texture resolutions and export formats.

---

## 🛠️ Issues & Suggestions

Found a bug or have an idea for improvement?

Please report it through the GitHub Issues section.

[Report an Issue](https://github.com/uncoderpased10/High-low-pbr-baker-addon-Blender-/issues)

---

## 📜 License

This project is distributed under the **GNU General Public License v3.0 or later (GPL-3.0-or-later)**.

See the LICENSE file for the full license terms.

---

## 👨‍💻 Author

**Senior Blender Tools Studio**

Project: High-Low PBR Baker Pro

GitHub: [@uncoderpased10](https://github.com/uncoderpased10)

---

*Built to make professional High-to-Low Poly PBR baking more accessible and efficient inside Blender.*
