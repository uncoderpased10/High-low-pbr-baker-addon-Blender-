# SPDX-License-Identifier: GPL-3.0-or-later
import colorsys
import hashlib
import bpy


def _find_socket_by_names(socket_collection, candidate_names):
    """Find a node socket safely across Blender 4.x / 5.2 naming variants."""
    for name in candidate_names:
        sock = socket_collection.get(name)
        if sock is not None:
            return sock
    return None


def _get_active_material_output(node_tree):
    """Return the active Material Output node (or first Material Output found)."""
    outputs = [n for n in node_tree.nodes if n.type == 'OUTPUT_MATERIAL']
    for out in outputs:
        if getattr(out, "is_active_output", False):
            return out
    return outputs[0] if outputs else None


def _find_principled_nodes(node_tree):
    """Return all Principled BSDF nodes in a material node tree."""
    return [n for n in node_tree.nodes if n.type == 'BSDF_PRINCIPLED']


class MaterialStateGuard:
    """
    Captures and deterministically restores all material node graphs on high-poly objects.
    Guarantees zero corrupted shaders even if a bake is cancelled or fails.
    """

    def __init__(self, high_objs):
        self.materials = []
        seen = set()
        for obj in high_objs:
            if obj is None or obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if mat is not None and mat.name not in seen:
                    seen.add(mat.name)
                    self.materials.append(mat)

        self._saved_states = {}

    def capture(self):
        """Snapshot every link and scalar value on all tracked high-poly materials."""
        self._saved_states.clear()
        for mat in self.materials:
            if not mat.use_nodes:
                mat.use_nodes = True
            nt = mat.node_tree
            if nt is None:
                continue

            links_snapshot = []
            for lk in nt.links:
                links_snapshot.append((lk.from_node.name, lk.from_socket.name, lk.to_node.name, lk.to_socket.name))

            bsdf_values = {}
            for node in _find_principled_nodes(nt):
                vals = {}
                for inp in node.inputs:
                    if hasattr(inp, "default_value"):
                        val = inp.default_value
                        if hasattr(val, "__len__"):
                            vals[inp.name] = tuple(val)
                        else:
                            vals[inp.name] = val
                bsdf_values[node.name] = vals

            self._saved_states[mat.name] = {
                "links": links_snapshot,
                "bsdf_values": bsdf_values,
            }

    def restore(self):
        """Restore exact original links, remove temporary bake nodes, and restore slider values."""
        for mat in self.materials:
            state = self._saved_states.get(mat.name)
            nt = mat.node_tree
            if state is None or nt is None:
                continue

            for node in list(nt.nodes):
                if node.name.startswith("_HLPBR_TMP_"):
                    nt.nodes.remove(node)

            nt.links.clear()
            for from_n, from_s, to_n, to_s in state["links"]:
                fn = nt.nodes.get(from_n)
                tn = nt.nodes.get(to_n)
                if fn is None or tn is None:
                    continue
                fs = fn.outputs.get(from_s)
                ts = tn.inputs.get(to_s)
                if fs is not None and ts is not None:
                    nt.links.new(fs, ts)

            for node_name, vals in state["bsdf_values"].items():
                node = nt.nodes.get(node_name)
                if node is None:
                    continue
                for inp_name, saved_val in vals.items():
                    inp = node.inputs.get(inp_name)
                    if inp is not None and hasattr(inp, "default_value"):
                        try:
                            inp.default_value = saved_val
                        except Exception:
                            pass

    def prepare_diffuse_albedo(self):
        """
        Eliminate the #1 Blender baking error (black diffuse textures on metallic surfaces):
        Force Metallic = 0.0 and disconnect any Metallic input links across all high-poly materials.
        """
        for mat in self.materials:
            nt = mat.node_tree
            if nt is None:
                continue
            for bsdf in _find_principled_nodes(nt):
                met_in = _find_socket_by_names(bsdf.inputs, ["Metallic"])
                if met_in is not None:
                    for lk in list(met_in.links):
                        nt.links.remove(lk)
                    met_in.default_value = 0.0

    def prepare_scalar_channel_as_emission(self, channel_names, default_scalar=0.0):
        """
        Route a Principled BSDF channel (e.g., Metallic, Alpha, Subsurface Weight)
        directly into an Emission shader connected to Material Output -> Surface
        so Cycles can bake it with zero lighting distortion.
        """
        for mat in self.materials:
            nt = mat.node_tree
            if nt is None:
                continue
            out_node = _get_active_material_output(nt)
            if out_node is None:
                out_node = nt.nodes.new("ShaderNodeOutputMaterial")
                out_node.name = "_HLPBR_TMP_Output"

            surf_in = out_node.inputs.get("Surface")
            if surf_in is None:
                continue

            bsdfs = _find_principled_nodes(nt)
            emit = nt.nodes.new("ShaderNodeEmission")
            emit.name = "_HLPBR_TMP_EmitChannel"
            emit.inputs["Strength"].default_value = 1.0

            if bsdfs:
                bsdf = bsdfs[0]
                src_in = _find_socket_by_names(bsdf.inputs, channel_names)
                if src_in is not None:
                    if src_in.is_linked:
                        from_sock = src_in.links[0].from_socket
                        nt.links.new(from_sock, emit.inputs["Color"])
                    else:
                        v = src_in.default_value
                        if hasattr(v, "__len__"):
                            emit.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0)
                        else:
                            fv = float(v)
                            emit.inputs["Color"].default_value = (fv, fv, fv, 1.0)
                else:
                    emit.inputs["Color"].default_value = (default_scalar, default_scalar, default_scalar, 1.0)
            else:
                emit.inputs["Color"].default_value = (default_scalar, default_scalar, default_scalar, 1.0)

            for lk in list(surf_in.links):
                nt.links.remove(lk)
            nt.links.new(emit.outputs["Emission"], surf_in)

    def prepare_material_id_as_emission(self):
        """
        Assign a deterministic, visually distinct flat emission color per material
        for clean Material ID map baking.
        """
        for idx, mat in enumerate(self.materials):
            nt = mat.node_tree
            if nt is None:
                continue
            out_node = _get_active_material_output(nt)
            if out_node is None:
                out_node = nt.nodes.new("ShaderNodeOutputMaterial")
                out_node.name = "_HLPBR_TMP_Output"

            surf_in = out_node.inputs.get("Surface")
            if surf_in is None:
                continue

            digest = hashlib.md5(f"{mat.name}_{idx}".encode("utf-8")).digest()
            hue = ((idx * 0.618033988749895) + (digest[0] / 255.0) * 0.15) % 1.0
            sat = 0.78 + (digest[1] / 255.0) * 0.20
            val = 0.85 + (digest[2] / 255.0) * 0.15

            r, g, b = colorsys.hsv_to_rgb(hue, sat, val)

            emit = nt.nodes.new("ShaderNodeEmission")
            emit.name = "_HLPBR_TMP_MatID"
            emit.inputs["Color"].default_value = (r, g, b, 1.0)
            emit.inputs["Strength"].default_value = 1.0

            for lk in list(surf_in.links):
                nt.links.remove(lk)
            nt.links.new(emit.outputs["Emission"], surf_in)


def setup_lowpoly_bake_target_node(low_obj, image):
    """
    Ensure low_obj has a valid material and an ACTIVE, SELECTED Image Texture node
    pointing to `image` so Cycles never throws 'No active image found in material'.
    """
    if image is not None:
        image.use_fake_user = True

    if not low_obj.data.materials:
        mat = bpy.data.materials.new(name=f"{low_obj.name}_BakeTarget_Mat")
        mat.use_nodes = True
        low_obj.data.materials.append(mat)

    for slot in low_obj.material_slots:
        mat = slot.material
        if mat is None:
            mat = bpy.data.materials.new(name=f"{low_obj.name}_BakeTarget_Mat")
            mat.use_nodes = True
            slot.material = mat
        if not mat.use_nodes:
            mat.use_nodes = True

        nt = mat.node_tree
        for n in nt.nodes:
            n.select = False

        tex_node = nt.nodes.get("_HLPBR_BAKE_TARGET_TEX")
        if tex_node is None or tex_node.type != 'TEX_IMAGE':
            tex_node = nt.nodes.new("ShaderNodeTexImage")
            tex_node.name = "_HLPBR_BAKE_TARGET_TEX"
            tex_node.location = (-450, 300)

        tex_node.image = image
        tex_node.select = True
        nt.nodes.active = tex_node


def build_final_pbr_material(low_obj, base_name, baked_images, normal_convention='OPENGL'):
    """
    Assemble a clean, production-ready Principled BSDF material on low_obj
    with all baked textures properly wired and color spaces verified.
    """
    mat_name = f"{base_name}_PBR_Mat"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True

    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (420, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (80, 0)
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    tex_coord = nt.nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-780, 0)

    y_cursor = 360

    def _add_tex_node(img, label, colorspace):
        nonlocal y_cursor
        img.use_fake_user = True
        try:
            img.colorspace_settings.name = colorspace
        except Exception:
            pass
        node = nt.nodes.new("ShaderNodeTexImage")
        node.label = label
        node.name = f"TEX_{label}"
        node.image = img
        node.location = (-420, y_cursor)
        nt.links.new(tex_coord.outputs["UV"], node.inputs["Vector"])
        y_cursor -= 280
        return node

    diff_img = baked_images.get("DIFFUSE")
    ao_img = baked_images.get("AO")
    base_col_in = _find_socket_by_names(bsdf.inputs, ["Base Color"])

    if diff_img is not None and base_col_in is not None:
        diff_node = _add_tex_node(diff_img, "BaseColor", "sRGB")
        if ao_img is not None:
            ao_node = _add_tex_node(ao_img, "AmbientOcclusion", "Non-Color")
            mix_ao = nt.nodes.new("ShaderNodeMix")
            mix_ao.data_type = 'RGBA'
            mix_ao.blend_type = 'MULTIPLY'
            mix_ao.inputs[0].default_value = 0.65
            mix_ao.location = (-130, 320)
            rgba_inputs = [s for s in mix_ao.inputs if getattr(s, "type", None) == 'RGBA']
            rgba_outputs = [s for s in mix_ao.outputs if getattr(s, "type", None) == 'RGBA']
            in_a = rgba_inputs[0] if len(rgba_inputs) >= 2 else mix_ao.inputs[6]
            in_b = rgba_inputs[1] if len(rgba_inputs) >= 2 else mix_ao.inputs[7]
            out_res = rgba_outputs[0] if rgba_outputs else mix_ao.outputs[2]
            nt.links.new(diff_node.outputs["Color"], in_a)
            nt.links.new(ao_node.outputs["Color"], in_b)
            nt.links.new(out_res, base_col_in)
        else:
            nt.links.new(diff_node.outputs["Color"], base_col_in)
    elif ao_img is not None and base_col_in is not None:
        ao_node = _add_tex_node(ao_img, "AmbientOcclusion", "Non-Color")
        nt.links.new(ao_node.outputs["Color"], base_col_in)

    met_img = baked_images.get("METALLIC")
    met_in = _find_socket_by_names(bsdf.inputs, ["Metallic"])
    if met_img is not None and met_in is not None:
        met_node = _add_tex_node(met_img, "Metallic", "Non-Color")
        nt.links.new(met_node.outputs["Color"], met_in)

    rough_img = baked_images.get("ROUGHNESS")
    rough_in = _find_socket_by_names(bsdf.inputs, ["Roughness"])
    if rough_img is not None and rough_in is not None:
        rough_node = _add_tex_node(rough_img, "Roughness", "Non-Color")
        nt.links.new(rough_node.outputs["Color"], rough_in)

    norm_img = baked_images.get("NORMAL")
    norm_in = _find_socket_by_names(bsdf.inputs, ["Normal"])
    if norm_img is not None and norm_in is not None:
        norm_node = _add_tex_node(norm_img, "Normal", "Non-Color")
        nrm_map = nt.nodes.new("ShaderNodeNormalMap")
        nrm_map.space = 'TANGENT'
        nrm_map.location = (-130, -240)
        nt.links.new(norm_node.outputs["Color"], nrm_map.inputs["Color"])
        nt.links.new(nrm_map.outputs["Normal"], norm_in)

    emit_img = baked_images.get("EMISSION")
    emit_in = _find_socket_by_names(bsdf.inputs, ["Emission Color", "Emission"])
    emit_str_in = _find_socket_by_names(bsdf.inputs, ["Emission Strength"])
    if emit_img is not None and emit_in is not None:
        emit_node = _add_tex_node(emit_img, "Emission", "sRGB")
        nt.links.new(emit_node.outputs["Color"], emit_in)
        if emit_str_in is not None:
            emit_str_in.default_value = 1.0

    low_obj.data.materials.clear()
    low_obj.data.materials.append(mat)
    return mat
