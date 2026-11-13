# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "High-Low PBR Baker Pro",
    "author": "Senior Blender Tools Studio",
    "version": (1, 0, 2),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar (N) > PBR Baker",
    "description": "Zero-error 1-click High-to-Low Poly PBR baker with BVH Auto-Cage & Crash-Shield for 1M-3M+ face meshes",
    "category": "Render",
}

import bpy
from .core.auto_cage import remove_cage_preview
from .ui.panel import (
    HLPBR_Settings,
    HLPBR_OT_AutoAssignSelection,
    HLPBR_OT_DetectAutoCage,
    HLPBR_OT_ToggleCagePreview,
    HLPBR_OT_QuickSmartUV,
    HLPBR_OT_BakeSingleMap,
    HLPBR_OT_BakeAllMaps,
    HLPBR_PT_MainPanel,
)

CLASSES = (
    HLPBR_Settings,
    HLPBR_OT_AutoAssignSelection,
    HLPBR_OT_DetectAutoCage,
    HLPBR_OT_ToggleCagePreview,
    HLPBR_OT_QuickSmartUV,
    HLPBR_OT_BakeSingleMap,
    HLPBR_OT_BakeAllMaps,
    HLPBR_PT_MainPanel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.hlpbr_settings = bpy.props.PointerProperty(type=HLPBR_Settings)


def unregister():
    remove_cage_preview()
    if hasattr(bpy.types.Scene, "hlpbr_settings"):
        del bpy.types.Scene.hlpbr_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
