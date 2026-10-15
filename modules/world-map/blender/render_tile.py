"""Prova Blender, passo 2: renderiza o recorte exportado por export_tile.py.

No Mac (Blender 4.2 LTS ou mais recente, https://www.blender.org/download/):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render_tile.py -- build/blender-prova
Opções (depois do "--"):
    --samples 96        amostras do Cycles (mais = menos grão, mais lento)
    --px 2048           resolução final (a exportação foi feita a 2048)
    --relief 40         exagero do relevo (altura máxima em unidades do mundo; o recorte tem 360 de lado)
    --no-trees          sem árvores (para comparar e para renders rápidos)
    --cpu               força o processador (por defeito usa a GPU do Mac, via Metal, se houver)
    --save-blend        guarda também a cena (prova.blend) para abrir e mexer no Blender
Escreve <pasta>/render.png.

Tudo é gerado por código, sem assets externos nem IA: o mesmo recorte dá sempre a mesma imagem.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"dir": None, "samples": 96, "px": None, "relief": 40.0, "trees": True, "cpu": False, "save_blend": False}
    it = iter(argv)
    for a in it:
        if a == "--samples":
            opts["samples"] = int(next(it))
        elif a == "--px":
            opts["px"] = int(next(it))
        elif a == "--relief":
            opts["relief"] = float(next(it))
        elif a == "--no-trees":
            opts["trees"] = False
        elif a == "--cpu":
            opts["cpu"] = True
        elif a == "--save-blend":
            opts["save_blend"] = True
        else:
            opts["dir"] = Path(a)
    if not opts["dir"]:
        sys.exit("indica a pasta exportada: ... -- build/blender-prova")
    return opts


O = parse_args()
D = O["dir"].resolve()
meta = json.loads((D / "meta.json").read_text())
SIZE = float(meta["size"])                     # lado do recorte, em unidades do mundo (= unidades do Blender)
PX = O["px"] or meta["px"]
height = np.load(D / "height.npy")             # 0..~1, linha 0 = norte
forest = np.load(D / "forest.npy")
sea = np.load(D / "sea.npy")
burgs = json.loads((D / "burgs.json").read_text())
N = height.shape[0]
RELIEF = O["relief"]


def sample(arr, x, y):
    """Amostragem bilinear; x,y em unidades do Blender (origem no canto sudoeste do recorte)."""
    fx = np.clip(x / SIZE * N - 0.5, 0, N - 1.001)
    fy = np.clip((SIZE - y) / SIZE * N - 0.5, 0, N - 1.001)      # Blender: y para norte; imagem: linha 0 a norte
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - x0, fy - y0
    a, b = arr[y0, x0], arr[y0, x0 + 1]
    c, d = arr[y0 + 1, x0], arr[y0 + 1, x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


# ------------------------------------------------------------------------------------------------ cena limpa
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)


def material(name, build):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    build(nt, bsdf)
    return m


def image_node(nt, path, non_color=False):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(str(path))
    n.extension = "EXTEND"
    if non_color:
        n.image.colorspace_settings.name = "Non-Color"
    return n


# ------------------------------------------------------------------------------------------------ terreno
GRID = 1024                                     # vértices por lado (~1 M); o detalhe fino vem do bump
bpy.ops.mesh.primitive_grid_add(x_subdivisions=GRID, y_subdivisions=GRID, size=SIZE, calc_uvs=True,
                                location=(SIZE / 2, SIZE / 2, 0))
terrain = bpy.context.active_object
terrain.name = "Terreno"
me = terrain.data
co = np.empty(len(me.vertices) * 3, np.float32)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
wx, wy = co[:, 0] + SIZE / 2, co[:, 1] + SIZE / 2       # a grelha nasce centrada na origem do objeto
h = sample(height, wx, wy)
depth = sample(sea, wx, wy)
co[:, 2] = np.where(h > 0, h * RELIEF + 0.15, -0.6 - depth * 2.5)      # a terra fica acima da água; o fundo desce
me.vertices.foreach_set("co", co.ravel())
attr = me.attributes.new("forest", "FLOAT", "POINT")
attr.data.foreach_set("value", sample(forest, wx, wy).astype(np.float32))
me.update()
bpy.ops.object.shade_smooth()


def build_terrain(nt, bsdf):
    L = nt.links
    uv = nt.nodes.new("ShaderNodeTexCoord")
    col = image_node(nt, D / "color.png")
    L.new(uv.outputs["UV"], col.inputs["Vector"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep_n = nt.nodes.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Normal"], sep_n.inputs["Vector"])
    sep_p = nt.nodes.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep_p.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 8
    # rocha nas encostas íngremes
    steep = nt.nodes.new("ShaderNodeMapRange")
    steep.inputs["From Min"].default_value = 0.93
    steep.inputs["From Max"].default_value = 0.78
    L.new(sep_n.outputs["Z"], steep.inputs["Value"])
    rock = nt.nodes.new("ShaderNodeMix")
    rock.data_type = "RGBA"
    rock.inputs["A"].default_value = (0.42, 0.39, 0.35, 1)
    rock.inputs["B"].default_value = (0.58, 0.55, 0.50, 1)
    L.new(noise.outputs["Fac"], rock.inputs["Factor"])
    mix_rock = nt.nodes.new("ShaderNodeMix")
    mix_rock.data_type = "RGBA"
    L.new(steep.outputs["Result"], mix_rock.inputs["Factor"])
    L.new(col.outputs["Color"], mix_rock.inputs["A"])
    L.new(rock.outputs["Result"], mix_rock.inputs["B"])
    # neve: acima de ~75 % da altura máxima, só onde não é a pique, com orla irregular
    snow_h = nt.nodes.new("ShaderNodeMapRange")
    snow_h.inputs["From Min"].default_value = RELIEF * 0.70
    snow_h.inputs["From Max"].default_value = RELIEF * 0.82
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    L.new(noise.outputs["Fac"], add.inputs[0])
    add.inputs[1].default_value = RELIEF * 0.12
    L.new(sep_p.outputs["Z"], add.inputs[2])
    L.new(add.outputs["Value"], snow_h.inputs["Value"])
    flat = nt.nodes.new("ShaderNodeMapRange")
    flat.inputs["From Min"].default_value = 0.70
    flat.inputs["From Max"].default_value = 0.85
    L.new(sep_n.outputs["Z"], flat.inputs["Value"])
    snow_f = nt.nodes.new("ShaderNodeMath")
    snow_f.operation = "MULTIPLY"
    L.new(snow_h.outputs["Result"], snow_f.inputs[0])
    L.new(flat.outputs["Result"], snow_f.inputs[1])
    mix_snow = nt.nodes.new("ShaderNodeMix")
    mix_snow.data_type = "RGBA"
    L.new(snow_f.outputs["Value"], mix_snow.inputs["Factor"])
    L.new(mix_rock.outputs["Result"], mix_snow.inputs["A"])
    mix_snow.inputs["B"].default_value = (0.93, 0.94, 0.95, 1)
    L.new(mix_snow.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    # micro-relevo
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 3.0
    fine.inputs["Detail"].default_value = 10
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.08
    L.new(fine.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


terrain.data.materials.append(material("Terreno", build_terrain))

# ------------------------------------------------------------------------------------------------ água
bpy.ops.mesh.primitive_plane_add(size=SIZE, location=(SIZE / 2, SIZE / 2, 0.05))
water = bpy.context.active_object
water.name = "Mar"


def build_water(nt, bsdf):
    L = nt.links
    uv = nt.nodes.new("ShaderNodeTexCoord")
    tex = image_node(nt, D / "sea.png", non_color=True)
    L.new(uv.outputs["UV"], tex.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.30, 0.50, 0.52, 1)       # baixio
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.06, 0.15, 0.22, 1)       # fundo
    L.new(tex.outputs["Color"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Specular IOR Level"].default_value = 0.15
    waves = nt.nodes.new("ShaderNodeTexWave")
    waves.inputs["Scale"].default_value = 0.6
    waves.inputs["Distortion"].default_value = 6
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    L.new(waves.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


water.data.materials.append(material("Mar", build_water))

# ------------------------------------------------------------------------------------------------ árvores
lib = bpy.data.collections.new("Modelos")
scene.collection.children.link(lib)
lib.hide_render = True


def tree_material(name, rgb):
    def build(nt, bsdf):
        info = nt.nodes.new("ShaderNodeObjectInfo")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * 0.75 for c in rgb], 1)
        ramp.color_ramp.elements[1].color = (*[min(1, c * 1.2) for c in rgb], 1)
        nt.links.new(info.outputs["Random"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.85
    return material(name, build)


def make(op, name, mat, **kw):
    op(**kw)
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    lib.objects.link(ob)
    return ob


conifer = make(bpy.ops.mesh.primitive_cone_add, "Conifera", tree_material("Agulhas", (0.12, 0.24, 0.13)),
               vertices=7, radius1=0.7, depth=2.4, location=(0, 0, 1.2))
broad = make(bpy.ops.mesh.primitive_ico_sphere_add, "Folhosa", tree_material("Folhas", (0.20, 0.32, 0.14)),
             subdivisions=1, radius=0.85, location=(0, 0, 1.1))
for ob in (conifer, broad):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_flat()
trees = bpy.data.collections.new("Arvores")
lib.children.link(trees)
for ob in (conifer, broad):
    lib.objects.unlink(ob)
    trees.objects.link(ob)

if O["trees"]:
    ng = bpy.data.node_groups.new("Floresta", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nn, L = ng.nodes, ng.links
    gin, gout = nn.new("NodeGroupInput"), nn.new("NodeGroupOutput")
    attr_n = nn.new("GeometryNodeInputNamedAttribute")
    attr_n.data_type = "FLOAT"
    attr_n.inputs["Name"].default_value = "forest"
    dens = nn.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    dens.inputs[1].default_value = 0.7                       # árvores por unidade² onde a floresta é densa
    L.new(attr_n.outputs["Attribute"], dens.inputs[0])
    dist = nn.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Seed"].default_value = 7
    L.new(gin.outputs["Geometry"], dist.inputs["Mesh"])
    L.new(dens.outputs["Value"], dist.inputs["Density"])
    normal = nn.new("GeometryNodeInputNormal")
    sepn = nn.new("ShaderNodeSeparateXYZ")
    L.new(normal.outputs["Normal"], sepn.inputs["Vector"])
    gt = nn.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.82                        # sem árvores em encostas a pique
    L.new(sepn.outputs["Z"], gt.inputs[0])
    L.new(gt.outputs["Value"], dist.inputs["Selection"])
    coll = nn.new("GeometryNodeCollectionInfo")
    coll.inputs["Collection"].default_value = trees
    coll.inputs["Separate Children"].default_value = True
    coll.inputs["Reset Children"].default_value = True
    rnd_i = nn.new("FunctionNodeRandomValue")
    rnd_i.data_type = "INT"
    rnd_i.inputs["Min"].default_value = 0
    rnd_i.inputs["Max"].default_value = 1
    rnd_s = nn.new("FunctionNodeRandomValue")
    rnd_s.data_type = "FLOAT"
    rnd_s.inputs["Min"].default_value = 0.6
    rnd_s.inputs["Max"].default_value = 1.25
    rnd_s.inputs["Seed"].default_value = 3
    rnd_r = nn.new("FunctionNodeRandomValue")
    rnd_r.data_type = "FLOAT_VECTOR"
    rnd_r.inputs["Max"].default_value = (0.08, 0.08, 6.283)
    rnd_r.inputs["Seed"].default_value = 5
    inst = nn.new("GeometryNodeInstanceOnPoints")
    inst.inputs["Pick Instance"].default_value = True
    L.new(dist.outputs["Points"], inst.inputs["Points"])
    L.new(coll.outputs["Instances"], inst.inputs["Instance"])
    L.new(rnd_i.outputs[2], inst.inputs["Instance Index"])
    L.new(rnd_s.outputs[1], inst.inputs["Scale"])
    L.new(rnd_r.outputs[0], inst.inputs["Rotation"])
    join = nn.new("GeometryNodeJoinGeometry")
    L.new(gin.outputs["Geometry"], join.inputs["Geometry"])
    L.new(inst.outputs["Instances"], join.inputs["Geometry"])
    L.new(join.outputs["Geometry"], gout.inputs["Geometry"])
    mod = terrain.modifiers.new("Floresta", "NODES")
    mod.node_group = ng

# ------------------------------------------------------------------------------------------------ povoações
house_mat = material("Casas", lambda nt, b: (setattr(b.inputs["Base Color"], "default_value", (0.62, 0.42, 0.30, 1)),
                                            setattr(b.inputs["Roughness"], "default_value", 0.8)))
wall_mat = material("Paredes", lambda nt, b: setattr(b.inputs["Base Color"], "default_value", (0.86, 0.80, 0.68, 1)))
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
house = bpy.context.active_object
house.name = "Casa"
house.scale = (0.8, 0.55, 0.45)
bpy.ops.object.transform_apply(scale=True)
house.data.materials.append(wall_mat)
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.7, depth=0.45, location=(0, 0, 0.45))
roof = bpy.context.active_object
roof.rotation_euler[2] = math.pi / 4
roof.scale = (1.1, 0.8, 1)
bpy.ops.object.transform_apply(rotation=True, scale=True)
roof.data.materials.append(house_mat)
bpy.ops.object.select_all(action="DESELECT")
house.select_set(True)
roof.select_set(True)
bpy.context.view_layer.objects.active = house
bpy.ops.object.join()
for c in house.users_collection:
    c.objects.unlink(house)
lib.objects.link(house)
town = bpy.data.collections.new("Povoacoes")
scene.collection.children.link(town)
rng = np.random.default_rng(11)
k = N / SIZE
for b in burgs:
    n = int(np.clip(3 + b["pop"] * 1.5, 3, 18)) + (8 if b["capital"] else 0)
    bx, by = b["x"] / k, SIZE - b["y"] / k
    for i in range(n):
        r = rng.uniform(0, 0.6 + 0.35 * math.sqrt(n))
        a = rng.uniform(0, 2 * math.pi)
        x, y = bx + r * math.cos(a), by + r * math.sin(a)
        z = float(sample(height, np.array([x]), np.array([y]))[0])
        if z <= 0:
            continue
        ob = house.copy()
        ob.location = (x, y, z * RELIEF + 0.15)
        ob.rotation_euler[2] = rng.uniform(0, math.pi)
        s = rng.uniform(0.8, 1.2) * (1.25 if b["capital"] else 1)
        ob.scale = (s, s, s)
        town.objects.link(ob)

# ------------------------------------------------------------------------------------------------ luz, câmara, render
bpy.ops.object.light_add(type="SUN", location=(0, 0, 50))
sun = bpy.context.active_object
sun.data.energy = 5.0
sun.data.angle = math.radians(3)                             # sombras ligeiramente suaves
sun.rotation_euler = (math.radians(60), 0, math.radians(-135))  # luz rasante de noroeste, como nos mapas clássicos
world = bpy.data.worlds.new("Ceu")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.62, 0.70, 0.80, 1)
bg.inputs["Strength"].default_value = 0.35

bpy.ops.object.camera_add(location=(SIZE / 2, SIZE / 2, 200), rotation=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = "ORTHO"
cam.data.ortho_scale = SIZE
cam.data.clip_end = 1000
scene.camera = cam

scene.render.engine = "CYCLES"
scene.render.resolution_x = scene.render.resolution_y = PX
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.cycles.samples = O["samples"]
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 4
scene.view_settings.view_transform = "Standard"           # cores fiéis à paleta (o AgX lava-as)
scene.view_settings.look = "None"
scene.view_settings.exposure = -0.4
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(D / "render.png")

if not O["cpu"]:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type != "CPU"]
        if gpus:
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
            print(f"a usar a GPU ({kind}): {', '.join(d.name for d in gpus)}")
            break
    else:
        print("sem GPU disponível: a usar o processador (mais lento)")

if O["save_blend"]:
    bpy.ops.wm.save_as_mainfile(filepath=str(D / "prova.blend"))
print(f"a renderizar {PX}×{PX} com {O['samples']} amostras…")
bpy.ops.render.render(write_still=True)
print("guardado:", D / "render.png")
