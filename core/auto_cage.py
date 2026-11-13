# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _build_combined_highpoly_bvh(context, high_objs):
    """Build a single world-space BVHTree from one or more high-poly mesh objects."""
    depsgraph = context.evaluated_depsgraph_get()
    all_verts = []
    all_polys = []
    vert_offset = 0

    for obj in high_objs:
        if obj is None or obj.type != 'MESH':
            continue
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if mesh is None:
            continue
        try:
            mesh.calc_loop_triangles()
            mat = eval_obj.matrix_world
            verts = [mat @ v.co for v in mesh.vertices]
            tris = [
                (
                    tri.vertices[0] + vert_offset,
                    tri.vertices[1] + vert_offset,
                    tri.vertices[2] + vert_offset,
                )
                for tri in mesh.loop_triangles
            ]
            all_verts.extend(verts)
            all_polys.extend(tris)
            vert_offset += len(verts)
        finally:
            eval_obj.to_mesh_clear()

    if not all_verts or not all_polys:
        return None

    return BVHTree.FromPolygons(all_verts, all_polys, all_triangles=True)


def compute_auto_cage_metrics(context, high_objs, low_obj, safety_margin_pct=18.0, max_samples=25000):
    """
    Analyze surface deviation between high-poly source(s) and low-poly target
    using C++ BVHTree spatial queries.
    """
    if not high_objs or low_obj is None or low_obj.type != 'MESH':
        return {
            "extrusion": 0.05,
            "max_ray_distance": 0.10,
            "p99_distance": 0.04,
            "max_distance": 0.05,
            "mean_distance": 0.01,
            "sample_count": 0,
        }

    bvh = _build_combined_highpoly_bvh(context, high_objs)
    if bvh is None:
        return {
            "extrusion": 0.05,
            "max_ray_distance": 0.10,
            "p99_distance": 0.04,
            "max_distance": 0.05,
            "mean_distance": 0.01,
            "sample_count": 0,
        }

    depsgraph = context.evaluated_depsgraph_get()
    eval_low = low_obj.evaluated_get(depsgraph)
    low_mesh = eval_low.to_mesh()

    try:
        mat_world = eval_low.matrix_world
        normal_mat = mat_world.to_3x3().inverted_safe().transposed()

        sample_points = []
        sample_normals = []

        verts = low_mesh.vertices
        polys = low_mesh.polygons
        total_items = len(verts) + len(polys)
        stride = max(1, total_items // max_samples)

        for idx in range(0, len(verts), stride):
            v = verts[idx]
            sample_points.append(mat_world @ v.co)
            n = (normal_mat @ v.normal).normalized()
            sample_normals.append(n)

        for idx in range(0, len(polys), stride):
            p = polys[idx]
            sample_points.append(mat_world @ p.center)
            n = (normal_mat @ p.normal).normalized()
            sample_normals.append(n)

        bbox_corners = [mat_world @ Vector(corner) for corner in low_obj.bound_box]
        min_co = Vector((min(c.x for c in bbox_corners), min(c.y for c in bbox_corners), min(c.z for c in bbox_corners)))
        max_co = Vector((max(c.x for c in bbox_corners), max(c.y for c in bbox_corners), max(c.z for c in bbox_corners)))
        diag = max((max_co - min_co).length, 1e-4)

        distances = []
        outward_offsets = []

        for pt, nrm in zip(sample_points, sample_normals):
            loc, _hit_nrm, _face_idx, dist = bvh.find_nearest(pt)
            if loc is not None and dist is not None:
                if dist <= diag * 0.25:
                    distances.append(dist)
                    delta = loc - pt
                    outward = delta.dot(nrm)
                    outward_offsets.append(max(dist, outward))

        if not distances:
            default_ext = round(diag * 0.015, 5)
            return {
                "extrusion": max(default_ext, 0.002),
                "max_ray_distance": max(round(default_ext * 2.0, 5), 0.004),
                "p99_distance": default_ext,
                "max_distance": default_ext,
                "mean_distance": default_ext * 0.5,
                "sample_count": 0,
            }

        distances.sort()
        outward_offsets.sort()
        n = len(distances)
        p99_idx = min(n - 1, int(n * 0.99))

        p99_dist = outward_offsets[p99_idx]
        max_dist = outward_offsets[-1]
        mean_dist = sum(distances) / n

        base_envelope = max(p99_dist, min(max_dist, p99_dist * 1.35))
        margin_mult = 1.0 + (max(0.0, safety_margin_pct) / 100.0)
        extrusion = max(base_envelope * margin_mult, diag * 0.0015, 0.0005)
        max_ray = max(extrusion * 2.25, max_dist * 1.35, extrusion + diag * 0.005)

        return {
            "extrusion": round(extrusion, 5),
            "max_ray_distance": round(max_ray, 5),
            "p99_distance": round(p99_dist, 5),
            "max_distance": round(max_dist, 5),
            "mean_distance": round(mean_dist, 5),
            "sample_count": n,
        }
    finally:
        eval_low.to_mesh_clear()


CAGE_PREVIEW_NAME = "_HLPBR_AutoCage_Preview"
CAGE_MAT_NAME = "_HLPBR_AutoCage_Mat"


def remove_cage_preview():
    """Safely remove any temporary cage preview object, mesh, and material."""
    obj = bpy.data.objects.get(CAGE_PREVIEW_NAME)
    if obj is not None:
        mesh_data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh_data and mesh_data.users == 0:
            bpy.data.meshes.remove(mesh_data)

    mat = bpy.data.materials.get(CAGE_MAT_NAME)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)


def create_or_update_cage_mesh(context, low_obj, extrusion, smooth_iterations=2, is_preview=True):
    """
    Build a clean displaced cage mesh from low_obj along smooth normals,
    with optional Laplacian smoothing to prevent self-intersections in tight crevices.
    """
    if low_obj is None or low_obj.type != 'MESH':
        return None

    cage_name = CAGE_PREVIEW_NAME if is_preview else "_HLPBR_BakeCage_Temp"
    existing = bpy.data.objects.get(cage_name)
    if existing is not None:
        old_data = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if old_data and old_data.users == 0:
            bpy.data.meshes.remove(old_data)

    depsgraph = context.evaluated_depsgraph_get()
    eval_low = low_obj.evaluated_get(depsgraph)
    temp_mesh = bpy.data.meshes.new_from_object(eval_low)
    temp_mesh.name = f"{cage_name}_Mesh"

    bm = bmesh.new()
    try:
        bm.from_mesh(temp_mesh)
        bm.normal_update()

        vert_normals = {}
        for v in bm.verts:
            acc = Vector((0.0, 0.0, 0.0))
            for f in v.link_faces:
                acc += f.normal * f.calc_area()
            if acc.length > 1e-8:
                acc.normalize()
            else:
                acc = v.normal.copy()
            vert_normals[v.index] = acc

        for _ in range(max(0, smooth_iterations)):
            new_normals = {}
            for v in bm.verts:
                acc = vert_normals[v.index] * 2.0
                for e in v.link_edges:
                    other = e.other_vert(v)
                    acc += vert_normals[other.index]
                if acc.length > 1e-8:
                    acc.normalize()
                else:
                    acc = vert_normals[v.index]
                new_normals[v.index] = acc
            vert_normals = new_normals

        scale = low_obj.matrix_world.to_scale()
        avg_scale = max((abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0, 1e-5)
        local_extrusion = extrusion / avg_scale

        for v in bm.verts:
            v.co += vert_normals[v.index] * local_extrusion

        bm.normal_update()
        bm.to_mesh(temp_mesh)
    finally:
        bm.free()

    cage_obj = bpy.data.objects.new(cage_name, temp_mesh)
    cage_obj.matrix_world = low_obj.matrix_world.copy()
    context.scene.collection.objects.link(cage_obj)

    if is_preview:
        cage_obj.display_type = 'WIRE'
        cage_obj.show_in_front = True
        cage_obj.hide_render = True
        cage_obj.hide_select = True
    else:
        cage_obj.hide_viewport = True
        cage_obj.hide_render = True

    return cage_obj
