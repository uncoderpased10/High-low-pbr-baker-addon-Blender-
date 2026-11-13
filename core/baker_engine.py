# SPDX-License-Identifier: GPL-3.0-or-later
import os
import time
import bpy
import numpy as np

from .auto_cage import compute_auto_cage_metrics, create_or_update_cage_mesh, remove_cage_preview
from .material_router import (
    MaterialStateGuard,
    setup_lowpoly_bake_target_node,
    build_final_pbr_material,
)
from .memory_guard import BakeCrashShield


MAP_META = {
    "DIFFUSE": {"suffix": "BaseColor", "colorspace": "sRGB", "default_bg": (0.0, 0.0, 0.0, 1.0)},
    "NORMAL": {"suffix": "Normal", "colorspace": "Non-Color", "default_bg": (0.5, 0.5, 1.0, 1.0)},
    "ROUGHNESS": {"suffix": "Roughness", "colorspace": "Non-Color", "default_bg": (0.5, 0.5, 0.5, 1.0)},
    "METALLIC": {"suffix": "Metallic", "colorspace": "Non-Color", "default_bg": (0.0, 0.0, 0.0, 1.0)},
    "AO": {"suffix": "AO", "colorspace": "Non-Color", "default_bg": (1.0, 1.0, 1.0, 1.0)},
    "EMISSION": {"suffix": "Emission", "colorspace": "sRGB", "default_bg": (0.0, 0.0, 0.0, 1.0)},
    "MAT_ID": {"suffix": "MaterialID", "colorspace": "sRGB", "default_bg": (0.0, 0.0, 0.0, 1.0)},
}


def resolve_high_poly_objects(context, settings):
    """Collect valid high-poly mesh objects from either Single Object or Collection mode."""
    low_obj = settings.low_poly_obj
    objs = []
    if settings.source_mode == 'COLLECTION' and settings.high_poly_collection is not None:
        for obj in settings.high_poly_collection.all_objects:
            if obj.type == 'MESH' and obj != low_obj and not obj.name.startswith("_HLPBR_"):
                objs.append(obj)
    elif settings.high_poly_obj is not None and settings.high_poly_obj.type == 'MESH':
        if settings.high_poly_obj != low_obj:
            objs.append(settings.high_poly_obj)
    return objs


def _create_bake_image(name, width, height, colorspace, use_float=False):
    """
    Create or replace a clean datablock image ready for Cycles baking.
    Sets `use_fake_user = True` immediately so `orphans_purge()` never removes
    completed bake passes when subsequent passes reassign the target texture node.
    """
    existing = bpy.data.images.get(name)
    if existing is not None:
        existing.use_fake_user = False
        bpy.data.images.remove(existing)

    img = bpy.data.images.new(
        name=name,
        width=width,
        height=height,
        alpha=False,
        float_buffer=use_float,
    )
    img.use_fake_user = True
    try:
        img.colorspace_settings.name = colorspace
    except Exception:
        pass
    return img


def _post_process_image(img, invert_values=False, target_res=None):
    """Fast vectorized NumPy post-processing (e.g., Roughness->Glossiness invert & supersample downscale)."""
    if invert_values:
        w, h = img.size
        pixels = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(pixels)
        pixels = pixels.reshape((h, w, 4))
        pixels[:, :, :3] = 1.0 - pixels[:, :, :3]
        img.pixels.foreach_set(pixels.ravel())
        img.update()

    if target_res is not None and (img.size[0] != target_res or img.size[1] != target_res):
        img.scale(target_res, target_res)
        img.update()


def _resolve_safe_output_dir(output_dir):
    """Resolve relative '//' paths safely even when the .blend file has not been saved yet."""
    if not output_dir:
        return None
    if output_dir.startswith("//") and not getattr(bpy.data, "filepath", ""):
        rel_sub = output_dir[2:].strip("/\\") or "Baked_Textures"
        return os.path.join(os.path.expanduser("~"), "Blender_Baked_Textures", rel_sub)
    return bpy.path.abspath(output_dir)


def _save_image_to_disk(img, output_dir, colorspace, file_format='PNG', bit_depth='8'):
    """
    Save baked image cleanly to disk using Standard color transform (so Non-Color data
    is never distorted by AgX/Filmic), reload, and re-lock fake user & colorspace.
    """
    img.use_fake_user = True
    abs_dir = _resolve_safe_output_dir(output_dir)
    if not abs_dir:
        try:
            img.pack()
        except Exception:
            pass
        return None

    os.makedirs(abs_dir, exist_ok=True)

    ext_map = {
        'PNG': ".png",
        'TARGA': ".tga",
        'OPEN_EXR': ".exr",
    }
    ext = ext_map.get(file_format, ".png")
    filepath = os.path.join(abs_dir, f"{img.name}{ext}")

    scene = bpy.context.scene
    img_settings = scene.render.image_settings
    prev_fmt = img_settings.file_format
    prev_depth = img_settings.color_depth
    prev_mode = img_settings.color_mode

    view_settings = getattr(scene, "view_settings", None)
    prev_transform = getattr(view_settings, "view_transform", None)

    try:
        img_settings.file_format = file_format
        img_settings.color_mode = 'RGB'
        if file_format == 'OPEN_EXR':
            img_settings.color_depth = '16'
        else:
            img_settings.color_depth = bit_depth

        if view_settings is not None and prev_transform is not None:
            try:
                view_settings.view_transform = 'Standard'
            except Exception:
                pass

        img.filepath_raw = filepath
        img.save_render(filepath=filepath, scene=scene)
        img.source = 'FILE'
        img.filepath = filepath
        img.reload()
        img.use_fake_user = True
        try:
            img.colorspace_settings.name = colorspace
        except Exception:
            pass
    finally:
        if view_settings is not None and prev_transform is not None:
            try:
                view_settings.view_transform = prev_transform
            except Exception:
                pass
        img_settings.file_format = prev_fmt
        img_settings.color_depth = prev_depth
        img_settings.color_mode = prev_mode

    return filepath


def _prepare_selection_for_bake(context, high_objs, low_obj):
    """Ensure exact Blender selection state: all high-poly selected, low-poly active."""
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    for obj in high_objs:
        obj.hide_set(False)
        obj.hide_render = False
        obj.select_set(True)

    low_obj.hide_set(False)
    low_obj.hide_render = False
    low_obj.select_set(True)
    context.view_layer.objects.active = low_obj


def execute_pbr_bake(context, map_list):
    """
    Execute one or more PBR bake passes from High-Poly source(s) to Low-Poly target.
    Returns (success: bool, message: str, elapsed_seconds: float).
    """
    t_start = time.perf_counter()
    scene = context.scene
    settings = scene.hlpbr_settings

    low_obj = settings.low_poly_obj
    high_objs = resolve_high_poly_objects(context, settings)

    if not high_objs:
        return False, "No valid High-Poly mesh assigned.", 0.0
    if low_obj is None or low_obj.type != 'MESH':
        return False, "No valid Low-Poly mesh assigned.", 0.0
    if not low_obj.data.uv_layers:
        return False, f"Low-Poly '{low_obj.name}' has no UV Map! Click 'Auto Smart UV' first.", 0.0

    remove_cage_preview()

    if settings.use_auto_cage:
        metrics = compute_auto_cage_metrics(
            context,
            high_objs,
            low_obj,
            safety_margin_pct=settings.cage_margin_pct,
        )
        settings.extrusion = metrics["extrusion"]
        settings.max_ray_distance = metrics["max_ray_distance"]

    base_name = settings.base_name.strip() or low_obj.name
    target_res = int(settings.resolution)
    aa_mult = int(settings.anti_aliasing)
    bake_res = target_res * aa_mult
    use_float = (settings.file_format == 'OPEN_EXR') or (aa_mult > 1)

    shield = BakeCrashShield(context, high_objs, low_obj, settings)
    mat_guard = MaterialStateGuard(high_objs)
    baked_image_names = {}
    temp_cage_obj = None

    wm = context.window_manager
    wm.progress_begin(0, len(map_list))

    try:
        shield.enter()
        mat_guard.capture()

        if settings.use_smooth_cage_mesh:
            temp_cage_obj = create_or_update_cage_mesh(
                context,
                low_obj,
                extrusion=settings.extrusion,
                smooth_iterations=2,
                is_preview=False,
            )

        bake_cfg = scene.render.bake
        bake_cfg.use_selected_to_active = True
        bake_cfg.margin = int(settings.margin) * aa_mult
        bake_cfg.use_clear = True

        if temp_cage_obj is not None:
            bake_cfg.use_cage = True
            bake_cfg.cage_object = temp_cage_obj
            bake_cfg.cage_extrusion = 0.0
            bake_cfg.max_ray_distance = settings.max_ray_distance
        else:
            bake_cfg.use_cage = False
            bake_cfg.cage_extrusion = settings.extrusion
            bake_cfg.max_ray_distance = settings.max_ray_distance

        bake_cfg.normal_space = 'TANGENT'
        bake_cfg.normal_r = 'POS_X'
        bake_cfg.normal_g = 'NEG_Y' if settings.normal_convention == 'DIRECTX' else 'POS_Y'
        bake_cfg.normal_b = 'POS_Z'

        for step_idx, map_key in enumerate(map_list):
            wm.progress_update(step_idx)
            meta = MAP_META[map_key]
            img_name = f"{base_name}_{meta['suffix']}"
            img = _create_bake_image(
                name=img_name,
                width=bake_res,
                height=bake_res,
                colorspace=meta["colorspace"],
                use_float=use_float,
            )

            mat_guard.restore()
            setup_lowpoly_bake_target_node(low_obj, img)
            _prepare_selection_for_bake(context, high_objs, low_obj)

            if map_key == "DIFFUSE":
                mat_guard.prepare_diffuse_albedo()
                bake_cfg.use_pass_direct = False
                bake_cfg.use_pass_indirect = False
                bake_cfg.use_pass_color = True
                cycles_bake_type = 'DIFFUSE'

            elif map_key == "ROUGHNESS":
                cycles_bake_type = 'ROUGHNESS'

            elif map_key == "METALLIC":
                mat_guard.prepare_scalar_channel_as_emission(["Metallic"], default_scalar=0.0)
                cycles_bake_type = 'EMIT'

            elif map_key == "NORMAL":
                cycles_bake_type = 'NORMAL'

            elif map_key == "AO":
                prev_samp = scene.cycles.samples
                scene.cycles.samples = max(prev_samp, int(settings.ao_samples))
                cycles_bake_type = 'AO'

            elif map_key == "EMISSION":
                cycles_bake_type = 'EMIT'

            elif map_key == "MAT_ID":
                mat_guard.prepare_material_id_as_emission()
                cycles_bake_type = 'EMIT'

            else:
                continue

            try:
                bpy.ops.object.bake(type=cycles_bake_type)
            except RuntimeError as err:
                if scene.cycles.device == 'GPU':
                    scene.cycles.device = 'CPU'
                    shield.purge_memory()
                    bpy.ops.object.bake(type=cycles_bake_type)
                else:
                    raise err

            if map_key == "AO":
                scene.cycles.samples = max(1, int(settings.bake_samples))

            invert = (map_key == "ROUGHNESS" and settings.invert_roughness_to_gloss)
            _post_process_image(img, invert_values=invert, target_res=target_res)

            if settings.save_to_disk:
                _save_image_to_disk(
                    img,
                    output_dir=settings.output_path,
                    colorspace=meta["colorspace"],
                    file_format=settings.file_format,
                    bit_depth=settings.color_depth,
                )
            else:
                try:
                    img.pack()
                except Exception:
                    pass

            baked_image_names[map_key] = img.name
            shield.purge_memory()

        mat_guard.restore()

        # Re-resolve live image datablocks by name so no stale StructRNA can ever be touched
        resolved_images = {}
        for m_key, i_name in baked_image_names.items():
            live_img = bpy.data.images.get(i_name)
            if live_img is not None:
                resolved_images[m_key] = live_img

        if settings.auto_build_material and resolved_images:
            build_final_pbr_material(
                low_obj,
                base_name=base_name,
                baked_images=resolved_images,
                normal_convention=settings.normal_convention,
            )

        wm.progress_update(len(map_list))
        elapsed = time.perf_counter() - t_start
        return True, f"Baked {len(resolved_images)} map(s) in {elapsed:.1f}s", elapsed

    except Exception as exc:
        return False, f"Bake error: {exc}", time.perf_counter() - t_start

    finally:
        mat_guard.restore()
        if temp_cage_obj is not None:
            mesh_data = temp_cage_obj.data
            bpy.data.objects.remove(temp_cage_obj, do_unlink=True)
            if mesh_data and mesh_data.users == 0:
                bpy.data.meshes.remove(mesh_data)
        shield.exit()
        wm.progress_end()
