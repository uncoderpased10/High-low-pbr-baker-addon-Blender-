# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty,
)

from ..core.auto_cage import (
    CAGE_PREVIEW_NAME,
    compute_auto_cage_metrics,
    create_or_update_cage_mesh,
    remove_cage_preview,
)
from ..core.baker_engine import execute_pbr_bake, resolve_high_poly_objects


def _poll_mesh_object(self, obj):
    return obj is not None and obj.type == 'MESH' and not obj.name.startswith("_HLPBR_")


def _on_cage_param_update(self, context):
    if bpy.data.objects.get(CAGE_PREVIEW_NAME) is not None and self.low_poly_obj is not None:
        create_or_update_cage_mesh(
            context,
            self.low_poly_obj,
            extrusion=self.extrusion,
            smooth_iterations=2,
            is_preview=True,
        )


class HLPBR_Settings(bpy.types.PropertyGroup):
    source_mode: EnumProperty(
        name="Source Mode",
        description="Bake from a single High-Poly object or an entire High-Poly collection",
        items=[
            ('OBJECT', "Single Object", "Bake from a single High-Poly mesh object", 'MESH_DATA', 0),
            ('COLLECTION', "Collection", "Bake from all mesh objects in a High-Poly collection", 'OUTLINER_COLLECTION', 1),
        ],
        default='OBJECT',
    )
    high_poly_obj: PointerProperty(
        name="High-Poly",
        description="High-Poly source mesh (supports 1M-3M+ faces)",
        type=bpy.types.Object,
        poll=_poll_mesh_object,
    )
    high_poly_collection: PointerProperty(
        name="High-Poly Collection",
        description="Collection containing multiple High-Poly mesh parts",
        type=bpy.types.Collection,
    )
    low_poly_obj: PointerProperty(
        name="Low-Poly",
        description="UV-unwrapped Low-Poly target mesh",
        type=bpy.types.Object,
        poll=_poll_mesh_object,
    )

    use_auto_cage: BoolProperty(
        name="Smart BVH Auto-Cage",
        description="Automatically calculate optimal cage extrusion and ray distance from surface geometry before baking",
        default=True,
    )
    use_smooth_cage_mesh: BoolProperty(
        name="Smooth Envelope Cage",
        description="Generate a smoothed normal-displaced cage mesh during baking to eliminate corner seams",
        default=True,
    )
    cage_margin_pct: FloatProperty(
        name="Cage Margin (%)",
        description="Extra envelope buffer above detected peak surface relief",
        default=18.0,
        min=0.0,
        max=150.0,
        subtype='PERCENTAGE',
    )
    extrusion: FloatProperty(
        name="Extrusion",
        description="Cage extrusion distance (auto-computed when Smart Auto-Cage is enabled)",
        default=0.05,
        min=0.0,
        soft_max=2.0,
        precision=4,
        update=_on_cage_param_update,
    )
    max_ray_distance: FloatProperty(
        name="Max Ray Distance",
        description="Maximum inward raycast distance to prevent far-side bleed",
        default=0.10,
        min=0.0,
        soft_max=5.0,
        precision=4,
    )
    last_cage_stats: StringProperty(
        name="Cage Stats",
        default="",
    )

    base_name: StringProperty(
        name="Base Name",
        description="Prefix for baked textures and material (defaults to Low-Poly name if empty)",
        default="",
    )
    resolution: EnumProperty(
        name="Resolution",
        description="Output texture resolution",
        items=[
            ('512', "512", "512 x 512 px"),
            ('1024', "1024", "1024 x 1024 px (1K)"),
            ('2048', "2048", "2048 x 2048 px (2K)"),
            ('4096', "4096", "4096 x 4096 px (4K)"),
            ('8192', "8192", "8192 x 8192 px (8K)"),
        ],
        default='2048',
    )
    margin: IntProperty(
        name="Padding",
        description="UV island dilation margin in pixels to prevent mipmap seams",
        default=8,
        min=0,
        max=128,
    )
    anti_aliasing: EnumProperty(
        name="Anti-Aliasing",
        description="Supersampling quality for razor-sharp UV borders",
        items=[
            ('1', "1x (Fast)", "Native resolution bake"),
            ('2', "2x (Crisp)", "Bake at 2x resolution and downscale cleanly"),
        ],
        default='1',
    )
    bake_samples: IntProperty(
        name="Samples",
        description="Cycles bake samples (16 is noise-free and fast for PBR maps)",
        default=16,
        min=1,
        max=256,
    )
    ao_samples: IntProperty(
        name="AO Samples",
        description="Cycles samples used specifically for Ambient Occlusion",
        default=32,
        min=4,
        max=512,
    )
    normal_convention: EnumProperty(
        name="Normal Space",
        description="Tangent normal green channel orientation",
        items=[
            ('OPENGL', "OpenGL (+Y)", "Blender / Unreal (with flip) / Godot / Unity"),
            ('DIRECTX', "DirectX (-Y)", "DirectX / Substance / 3ds Max"),
        ],
        default='OPENGL',
    )
    invert_roughness_to_gloss: BoolProperty(
        name="Invert to Glossiness",
        description="Invert Roughness output to produce a Glossiness map",
        default=False,
    )

    crash_shield_enabled: BoolProperty(
        name="Crash-Shield (3M+ Poly Safe)",
        description="Isolate viewport shaders, disable denoising during bake, and purge memory between passes",
        default=True,
    )
    compute_mode: EnumProperty(
        name="Device",
        description="Cycles compute backend with automatic GPU->CPU OOM fallback",
        items=[
            ('AUTO', "Auto GPU (CPU Fallback)", "Use GPU if available and fall back to CPU on low VRAM"),
            ('CPU_SAFE', "CPU Safe Mode", "Force CPU rendering for huge 3M+ face meshes on low-VRAM GPUs"),
        ],
        default='AUTO',
    )

    bake_diffuse: BoolProperty(name="Diffuse", default=True)
    bake_normal: BoolProperty(name="Normal", default=True)
    bake_roughness: BoolProperty(name="Roughness", default=True)
    bake_metallic: BoolProperty(name="Metallic", default=True)
    bake_ao: BoolProperty(name="Ambient Occlusion", default=False)
    bake_emission: BoolProperty(name="Emission", default=False)
    bake_mat_id: BoolProperty(name="Material ID", default=False)

    auto_build_material: BoolProperty(
        name="Auto-Apply PBR Material",
        description="Automatically create and assign a Principled BSDF material with all baked maps wired",
        default=True,
    )
    save_to_disk: BoolProperty(
        name="Save Textures to Disk",
        description="Export baked maps to a folder on disk",
        default=True,
    )
    output_path: StringProperty(
        name="Folder",
        description="Destination folder for baked textures",
        default="//Baked_Textures/",
        subtype='DIR_PATH',
    )
    file_format: EnumProperty(
        name="Format",
        items=[
            ('PNG', "PNG", "Lossless PNG"),
            ('OPEN_EXR', "EXR (16-bit)", "16-bit Float OpenEXR"),
            ('TARGA', "TGA", "Targa"),
        ],
        default='PNG',
    )
    color_depth: EnumProperty(
        name="Bit Depth",
        items=[
            ('8', "8-bit", "Standard 8-bit per channel"),
            ('16', "16-bit", "High-precision 16-bit per channel (best for Normal maps)"),
        ],
        default='16',
    )

    last_status: StringProperty(name="Last Status", default="Ready")


class HLPBR_OT_AutoAssignSelection(bpy.types.Operator):
    bl_idname = "hlpbr.auto_assign_selection"
    bl_label = "Auto-Detect High & Low"
    bl_description = "Automatically assign selected meshes by polygon count (highest = High-Poly, lowest = Low-Poly)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.hlpbr_settings
        meshes = [
            o for o in context.selected_objects
            if o.type == 'MESH' and not o.name.startswith("_HLPBR_")
        ]
        if len(meshes) < 2:
            self.report({'WARNING'}, "Select at least 2 mesh objects (High-Poly and Low-Poly).")
            return {'CANCELLED'}

        meshes.sort(key=lambda o: len(o.data.polygons), reverse=True)
        settings.source_mode = 'OBJECT'
        settings.high_poly_obj = meshes[0]
        settings.low_poly_obj = meshes[-1]
        if not settings.base_name.strip():
            settings.base_name = meshes[-1].name

        self.report(
            {'INFO'},
            f"Assigned High: {meshes[0].name} ({len(meshes[0].data.polygons):,} faces) -> Low: {meshes[-1].name} ({len(meshes[-1].data.polygons):,} faces)",
        )
        return {'FINISHED'}


class HLPBR_OT_DetectAutoCage(bpy.types.Operator):
    bl_idname = "hlpbr.detect_auto_cage"
    bl_label = "Detect Auto-Cage"
    bl_description = "Analyze High-Poly to Low-Poly geometry using BVH spatial queries and compute optimal cage values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.hlpbr_settings
        high_objs = resolve_high_poly_objects(context, settings)
        low_obj = settings.low_poly_obj

        if not high_objs or low_obj is None:
            self.report({'WARNING'}, "Assign both High-Poly and Low-Poly meshes first.")
            return {'CANCELLED'}

        metrics = compute_auto_cage_metrics(
            context,
            high_objs,
            low_obj,
            safety_margin_pct=settings.cage_margin_pct,
        )
        settings.extrusion = metrics["extrusion"]
        settings.max_ray_distance = metrics["max_ray_distance"]
        settings.last_cage_stats = (
            f"P99 Relief: {metrics['p99_distance']:.4f}m | Ext: {metrics['extrusion']:.4f}m"
        )
        self.report({'INFO'}, f"Auto-Cage detected -> Extrusion: {metrics['extrusion']:.4f}, Max Ray: {metrics['max_ray_distance']:.4f}")
        return {'FINISHED'}


class HLPBR_OT_ToggleCagePreview(bpy.types.Operator):
    bl_idname = "hlpbr.toggle_cage_preview"
    bl_label = "Preview Cage Overlay"
    bl_description = "Toggle wireframe preview of the Auto-Cage envelope in the 3D Viewport"

    def execute(self, context):
        settings = context.scene.hlpbr_settings
        if bpy.data.objects.get(CAGE_PREVIEW_NAME) is not None:
            remove_cage_preview()
            return {'FINISHED'}

        if settings.low_poly_obj is None:
            self.report({'WARNING'}, "Assign a Low-Poly mesh first.")
            return {'CANCELLED'}

        high_objs = resolve_high_poly_objects(context, settings)
        if settings.use_auto_cage and high_objs:
            metrics = compute_auto_cage_metrics(
                context,
                high_objs,
                settings.low_poly_obj,
                safety_margin_pct=settings.cage_margin_pct,
            )
            settings.extrusion = metrics["extrusion"]
            settings.max_ray_distance = metrics["max_ray_distance"]

        create_or_update_cage_mesh(
            context,
            settings.low_poly_obj,
            extrusion=settings.extrusion,
            smooth_iterations=2,
            is_preview=True,
        )
        return {'FINISHED'}


class HLPBR_OT_QuickSmartUV(bpy.types.Operator):
    bl_idname = "hlpbr.quick_smart_uv"
    bl_label = "Auto Smart UV Unwrap"
    bl_description = "Generate a clean non-overlapping UV map on the Low-Poly target mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        low_obj = context.scene.hlpbr_settings.low_poly_obj
        if low_obj is None or low_obj.type != 'MESH':
            self.report({'WARNING'}, "No Low-Poly mesh assigned.")
            return {'CANCELLED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.select_all(action='DESELECT')
        low_obj.select_set(True)
        context.view_layer.objects.active = low_obj

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.015)
        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"Smart UV unwrapped '{low_obj.name}'.")
        return {'FINISHED'}


class HLPBR_OT_BakeSingleMap(bpy.types.Operator):
    bl_idname = "hlpbr.bake_single_map"
    bl_label = "Bake Single PBR Map"
    bl_description = "Bake this specific PBR channel from High-Poly to Low-Poly"
    bl_options = {'REGISTER', 'UNDO'}

    map_type: StringProperty(default="DIFFUSE")

    def execute(self, context):
        ok, msg, _elapsed = execute_pbr_bake(context, [self.map_type])
        context.scene.hlpbr_settings.last_status = msg
        self.report({'INFO'} if ok else {'ERROR'}, msg)
        return {'FINISHED'} if ok else {'CANCELLED'}


class HLPBR_OT_BakeAllMaps(bpy.types.Operator):
    bl_idname = "hlpbr.bake_all_maps"
    bl_label = "Bake ALL Maps"
    bl_description = "Bake all enabled PBR channels in one automated, crash-protected pass"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.hlpbr_settings
        maps = []
        if s.bake_diffuse:
            maps.append("DIFFUSE")
        if s.bake_roughness:
            maps.append("ROUGHNESS")
        if s.bake_metallic:
            maps.append("METALLIC")
        if s.bake_normal:
            maps.append("NORMAL")
        if s.bake_ao:
            maps.append("AO")
        if s.bake_emission:
            maps.append("EMISSION")
        if s.bake_mat_id:
            maps.append("MAT_ID")

        if not maps:
            self.report({'WARNING'}, "Enable at least one PBR map channel to bake.")
            return {'CANCELLED'}

        ok, msg, _elapsed = execute_pbr_bake(context, maps)
        s.last_status = msg
        self.report({'INFO'} if ok else {'ERROR'}, msg)
        return {'FINISHED'} if ok else {'CANCELLED'}


class HLPBR_PT_MainPanel(bpy.types.Panel):
    bl_label = "High-Low PBR Baker Pro"
    bl_idname = "HLPBR_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PBR Baker"

    def draw(self, context):
        layout = self.layout
        s = context.scene.hlpbr_settings

        # --- Header Card + Top Primary Bake CTA ---
        header_box = layout.box()
        row = header_box.row(align=True)
        row.label(text="PBR BAKER PRO", icon='RENDER_RESULT')
        row.operator("hlpbr.auto_assign_selection", text="Auto-Detect", icon='EYEDROPPER')

        high_objs = resolve_high_poly_objects(context, s)
        hp_faces = sum(len(o.data.polygons) for o in high_objs)
        lp_faces = len(s.low_poly_obj.data.polygons) if (s.low_poly_obj and s.low_poly_obj.type == 'MESH') else 0

        if hp_faces > 0 and lp_faces > 0:
            sub = header_box.row()
            sub.label(text=f"HP: {hp_faces:,}  ->  LP: {lp_faces:,} faces", icon='CHECKMARK')
        else:
            sub = header_box.row()
            sub.label(text="Select High & Low meshes -> Auto-Detect", icon='INFO')

        top_cta = header_box.column(align=True)
        top_cta.scale_y = 1.5
        top_cta.operator("hlpbr.bake_all_maps", text="Bake ALL Maps", icon='RENDER_STILL')

        # --- 1. Mesh Targets ---
        mesh_box = layout.box()
        mesh_box.label(text="1. Mesh Targets", icon='OBJECT_DATA')
        mesh_box.prop(s, "source_mode", expand=True)

        if s.source_mode == 'OBJECT':
            mesh_box.prop(s, "high_poly_obj", icon='MESH_ICOSPHERE')
        else:
            mesh_box.prop(s, "high_poly_collection", icon='OUTLINER_COLLECTION')

        mesh_box.prop(s, "low_poly_obj", icon='MESH_CUBE')

        if s.low_poly_obj and s.low_poly_obj.type == 'MESH' and not s.low_poly_obj.data.uv_layers:
            warn_row = mesh_box.row(align=True)
            warn_row.alert = True
            warn_row.operator("hlpbr.quick_smart_uv", text="Missing UVs! Click to Auto-Unwrap", icon='ERROR')

        # --- 2. Smart BVH Auto-Cage ---
        cage_box = layout.box()
        c_head = cage_box.row(align=True)
        c_head.label(text="2. Smart BVH Auto-Cage", icon='MOD_SOLIDIFY')
        c_head.prop(s, "use_auto_cage", text="Auto")

        if s.use_auto_cage:
            cage_box.prop(s, "cage_margin_pct", slider=True)

        c_btns = cage_box.row(align=True)
        c_btns.operator("hlpbr.detect_auto_cage", text="Detect Cage", icon='VIEWZOOM')
        is_previewing = bpy.data.objects.get(CAGE_PREVIEW_NAME) is not None
        c_btns.operator(
            "hlpbr.toggle_cage_preview",
            text="Hide Cage" if is_previewing else "Preview Cage",
            icon='HIDE_OFF' if is_previewing else 'SHADING_WIRE',
            depress=is_previewing,
        )

        col_cage = cage_box.column(align=True)
        col_cage.prop(s, "extrusion")
        col_cage.prop(s, "max_ray_distance")
        col_cage.prop(s, "use_smooth_cage_mesh")

        if s.last_cage_stats:
            stat_row = cage_box.row()
            stat_row.scale_y = 0.8
            stat_row.label(text=s.last_cage_stats, icon='DRIVER_DISTANCE')

        # --- 3. Bake Settings & Crash-Shield ---
        cfg_box = layout.box()
        cfg_box.label(text="3. Bake Settings & Crash-Shield", icon='PREFERENCES')
        cfg_box.prop(s, "base_name", text="Name")

        res_row = cfg_box.row(align=True)
        res_row.label(text="Resolution:")
        res_row.prop(s, "resolution", text="")

        grid = cfg_box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.prop(s, "margin")
        grid.prop(s, "bake_samples")
        grid.prop(s, "anti_aliasing", text="AA")
        grid.prop(s, "normal_convention", text="")

        cfg_box.prop(s, "crash_shield_enabled")
        cfg_box.prop(s, "compute_mode", text="Device")

        # --- 4. PBR Channels ---
        map_box = layout.box()
        map_box.label(text="4. PBR Channels (Zero-Error)", icon='NODE_MATERIAL')

        channels = [
            ("bake_diffuse", "Diffuse", "DIFFUSE", 'SHADING_RENDERED'),
            ("bake_roughness", "Roughness", "ROUGHNESS", 'NODE_TEXTURE'),
            ("bake_metallic", "Metallic", "METALLIC", 'SHADING_SOLID'),
            ("bake_normal", "Normal", "NORMAL", 'NORMALS_FACE'),
            ("bake_ao", "Ambient Occlusion", "AO", 'SHADING_BBOX'),
            ("bake_emission", "Emission", "EMISSION", 'LIGHT_SUN'),
            ("bake_mat_id", "Material ID", "MAT_ID", 'COLOR'),
        ]

        for prop_name, label, map_code, icon_name in channels:
            row = map_box.row(align=True)
            row.prop(s, prop_name, text="")
            op = row.operator("hlpbr.bake_single_map", text=f"Bake {label}", icon=icon_name)
            op.map_type = map_code

        if s.bake_roughness:
            r_opt = map_box.row()
            r_opt.prop(s, "invert_roughness_to_gloss")

        # --- 5. Output & Master CTA ---
        out_box = layout.box()
        out_box.label(text="5. Output & Material Setup", icon='FILE_IMAGE')
        out_box.prop(s, "auto_build_material")
        out_box.prop(s, "save_to_disk")
        if s.save_to_disk:
            out_box.prop(s, "output_path", text="")
            fmt_row = out_box.row(align=True)
            fmt_row.prop(s, "file_format", text="")
            if s.file_format != 'OPEN_EXR':
                fmt_row.prop(s, "color_depth", text="")

        bot_cta = layout.column(align=True)
        bot_cta.scale_y = 1.65
        bot_cta.operator("hlpbr.bake_all_maps", text="Bake ALL Maps", icon='RENDER_STILL')

        if s.last_status:
            status_row = layout.row()
            status_row.scale_y = 0.85
            status_row.label(text=s.last_status, icon='TIME')
