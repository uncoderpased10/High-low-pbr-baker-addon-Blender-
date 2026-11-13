# SPDX-License-Identifier: GPL-3.0-or-later
import gc
import bpy


class BakeCrashShield:
    """
    Protects Blender 5.2 from VRAM spikes, viewport shader stalls, and RAM exhaustion
    when baking 1M-3M+ face high-poly meshes onto low-poly targets.
    """

    def __init__(self, context, high_objs, low_obj, settings):
        self.context = context
        self.scene = context.scene
        self.high_objs = [o for o in high_objs if o is not None]
        self.low_obj = low_obj
        self.settings = settings

        self._prev_engine = self.scene.render.engine
        self._prev_cycles_device = getattr(self.scene.cycles, "device", "CPU")
        self._prev_samples = getattr(self.scene.cycles, "samples", 128)
        self._prev_adaptive = getattr(self.scene.cycles, "use_adaptive_sampling", True)
        self._prev_denoising = getattr(self.scene.cycles, "use_denoising", True)
        self._prev_bake_type = getattr(self.scene.cycles, "bake_type", "COMBINED")

        self._bake = self.scene.render.bake
        self._prev_bake_cfg = {
            "use_selected_to_active": self._bake.use_selected_to_active,
            "use_cage": self._bake.use_cage,
            "cage_object": self._bake.cage_object,
            "cage_extrusion": self._bake.cage_extrusion,
            "max_ray_distance": self._bake.max_ray_distance,
            "margin": self._bake.margin,
            "use_clear": self._bake.use_clear,
            "use_pass_direct": self._bake.use_pass_direct,
            "use_pass_indirect": self._bake.use_pass_indirect,
            "use_pass_color": self._bake.use_pass_color,
            "normal_space": self._bake.normal_space,
            "normal_r": self._bake.normal_r,
            "normal_g": self._bake.normal_g,
            "normal_b": self._bake.normal_b,
        }

        self._viewport_shadings = []
        self._disabled_modifiers = []
        self._hidden_objects = []

    def _configure_compute_device(self):
        mode = self.settings.compute_mode
        if mode == 'CPU_SAFE':
            self.scene.cycles.device = 'CPU'
            return

        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs is not None:
            cprefs = prefs.preferences
            for backend in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
                try:
                    cprefs.compute_device_type = backend
                    cprefs.get_devices()
                    has_gpu = any(d.type != 'CPU' for d in cprefs.devices)
                    if has_gpu:
                        for d in cprefs.devices:
                            d.use = True
                        self.scene.cycles.device = 'GPU'
                        return
                except Exception:
                    continue

        if mode == 'AUTO':
            self.scene.cycles.device = 'CPU'

    def enter(self):
        """Isolate viewport overhead, configure Cycles for fast low-VRAM baking."""
        self.scene.render.engine = 'CYCLES'
        self._configure_compute_device()

        self.scene.cycles.samples = max(1, int(self.settings.bake_samples))
        if hasattr(self.scene.cycles, "use_adaptive_sampling"):
            self.scene.cycles.use_adaptive_sampling = True
        if hasattr(self.scene.cycles, "use_denoising"):
            self.scene.cycles.use_denoising = False

        if self.settings.crash_shield_enabled:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                self._viewport_shadings.append((space, space.shading.type))
                                space.shading.type = 'SOLID'

            keep_names = {self.low_obj.name} | {o.name for o in self.high_objs}
            for obj in self.scene.objects:
                if obj.type == 'MESH' and obj.name not in keep_names:
                    if not obj.hide_render:
                        self._hidden_objects.append((obj, obj.hide_render))
                        obj.hide_render = True

            for obj in self.high_objs:
                for mod in obj.modifiers:
                    if mod.show_viewport and not mod.show_render:
                        self._disabled_modifiers.append((mod, True))
                        mod.show_viewport = False

        self.purge_memory()

    @staticmethod
    def purge_memory():
        """Force Python GC and Blender orphan datablock cleanup between passes."""
        gc.collect()
        try:
            bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
        except Exception:
            pass

    def exit(self):
        """Restore all scene, Cycles, viewport, and object states."""
        for space, prev_shading in self._viewport_shadings:
            try:
                space.shading.type = prev_shading
            except Exception:
                pass

        for obj, prev_hr in self._hidden_objects:
            try:
                obj.hide_render = prev_hr
            except Exception:
                pass

        for mod, prev_sv in self._disabled_modifiers:
            try:
                mod.show_viewport = prev_sv
            except Exception:
                pass

        for k, v in self._prev_bake_cfg.items():
            try:
                setattr(self._bake, k, v)
            except Exception:
                pass

        try:
            self.scene.cycles.device = self._prev_cycles_device
            self.scene.cycles.samples = self._prev_samples
            self.scene.cycles.use_adaptive_sampling = self._prev_adaptive
            self.scene.cycles.use_denoising = self._prev_denoising
            self.scene.cycles.bake_type = self._prev_bake_type
            self.scene.render.engine = self._prev_engine
        except Exception:
            pass

        self.purge_memory()
