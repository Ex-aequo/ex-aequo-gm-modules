"""Renderiza um recorte exportado (export_tile.py, para a prova) ou um tile do mundo (render_world.py).

No Mac (Blender 4.2 LTS, https://www.blender.org/download/lts/4-2/):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render_tile.py -- build/blender-prova
A pasta tem: height.npy, sea.png, color.png, trees.npy, houses.npy e meta.json (janela com margem).
A câmara mostra só o interior; a margem existe para as sombras e o relevo vizinhos entrarem.
Opções (depois do "--"):
    --samples 96        amostras do Cycles (mais = menos grão, mais lento)
    --px 1024           resolução final (por defeito, a do interior exportado)
    --relief 40         exagero do relevo (por defeito, o da exportação)
    --out ficheiro.png  onde guardar (por defeito <pasta>/render-<estilo>.png)
    --no-post           sem pós-processamento (os tiles do mundo levam-no no mosaico inteiro)
    --no-trees          sem árvores (para comparar e para renders rápidos)
    --cpu               força o processador (por defeito usa a GPU do Mac, via Metal, se houver)
    --save-blend        guarda também a cena (prova.blend) para abrir e mexer no Blender
    --style maqueta     maqueta (relevo realista, luz rasante) | atlas (mapa pintado, papel e tinta) |
                        sombrio (o tom da Praga: luz fria, névoa nos vales)
Escreve <pasta>/render-<estilo>.png.

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
    opts = {"dir": None, "samples": 96, "px": None, "relief": None, "trees": True, "cpu": False, "save_blend": False,
            "style": "atlas", "out": None, "post": True}
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
        elif a == "--style":
            opts["style"] = next(it)
        elif a == "--out":
            opts["out"] = Path(next(it))
        elif a == "--no-post":
            opts["post"] = False
        else:
            opts["dir"] = Path(a)
    if not opts["dir"]:
        sys.exit("indica a pasta exportada: ... -- build/blender-prova")
    return opts


O = parse_args()
D = O["dir"].resolve()
meta = json.loads((D / "meta.json").read_text())
KPU = float(meta["px_per_unit"])               # píxeis por unidade do mundo
N = int(meta["n"])                             # lado da janela exportada (com margem), em píxeis
SIZE = N / KPU                                 # lado da janela em unidades do mundo (= unidades do Blender)
INNER = meta["tile"] / KPU                     # o que a câmara mostra
PX = O["px"] or meta["tile"]
height = np.load(D / "height.npy")             # 0..~1, linha 0 = norte
sea = np.load(D / "sea.npy")
trees_pts = np.load(D / "trees.npy")           # x, y (px da janela), tipo, escala, rotação
houses_pts = np.load(D / "houses.npy")         # x, y, rotação, escala
RELIEF = O["relief"] or float(meta["relief"])
HMAX = float(meta.get("hmax") or height.max() or 1.0)    # global: a neve começa à mesma altura em todos os tiles

# estilos: só luz, cores, árvores e pós-processamento mudam; o terreno é o mesmo
STYLES = {
    "maqueta": dict(sun_tilt=60, sun_color=(1, 1, 1), sun_energy=5.0, sky=(0.62, 0.70, 0.80), sky_strength=0.35,
                    exposure=-0.4, tree_scale=1.0, tree_density=0.7, tree_tint=1.0, snow=(0.82, 0.84, 0.86)),
    "atlas": dict(sun_tilt=50, sun_color=(1.0, 0.93, 0.80), sun_energy=4.6, sky=(0.86, 0.78, 0.62), sky_strength=0.35,
                  exposure=-0.35, tree_scale=1.6, tree_density=0.28, tree_tint=1.1, snow=(0.90, 0.88, 0.82)),
    "sombrio": dict(sun_tilt=72, sun_color=(0.72, 0.80, 1.0), sun_energy=3.6, sky=(0.32, 0.37, 0.45), sky_strength=0.45,
                    exposure=-0.55, tree_scale=1.0, tree_density=0.85, tree_tint=0.7, snow=(0.70, 0.74, 0.80)),
}
if O["style"] not in STYLES:
    sys.exit(f"estilo desconhecido: {O['style']} (opções: {', '.join(STYLES)})")
ST = STYLES[O["style"]]


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
GRID = N // 2                                   # um vértice a cada 2 px; o detalhe fino vem do bump
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
    steep.inputs["From Min"].default_value = 0.90
    steep.inputs["From Max"].default_value = 0.72
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
    snow_h.inputs["From Min"].default_value = RELIEF * HMAX * 0.82        # neve só nos cumes
    snow_h.inputs["From Max"].default_value = RELIEF * HMAX * 0.94
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    L.new(noise.outputs["Fac"], add.inputs[0])
    add.inputs[1].default_value = RELIEF * HMAX * 0.10
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
    mix_snow.inputs["B"].default_value = (*ST["snow"], 1)
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
        t = ST["tree_tint"]
        ramp.color_ramp.elements[0].color = (*[c * 0.75 * t for c in rgb], 1)
        ramp.color_ramp.elements[1].color = (*[min(1, c * 1.2 * t) for c in rgb], 1)
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

def points_object(name, xy_px, attrs):
    """Nuvem de pontos (vértices soltos) pousada no terreno, com atributos para o Geometry Nodes."""
    x = xy_px[:, 0] / KPU
    y = SIZE - xy_px[:, 1] / KPU
    z = sample(height, x, y) * RELIEF + 0.15
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(x))
    me.vertices.foreach_set("co", np.column_stack([x, y, z]).astype(np.float32).ravel())
    for key, (kind, values) in attrs.items():
        at = me.attributes.new(key, kind, "POINT")
        at.data.foreach_set("value", values)
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def instancer(ob, source, index_attr=None, scale_mult=1.0):
    """Geometry Nodes: uma instância de `source` (coleção ou objeto) em cada ponto, com escala e rotação dos
    atributos "scale" e "rot" e, numa coleção, o modelo escolhido pelo atributo index_attr."""
    ng = bpy.data.node_groups.new(ob.name + "GN", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nn, L = ng.nodes, ng.links
    gin, gout = nn.new("NodeGroupInput"), nn.new("NodeGroupOutput")
    inst = nn.new("GeometryNodeInstanceOnPoints")
    L.new(gin.outputs["Geometry"], inst.inputs["Points"])
    if isinstance(source, bpy.types.Collection):
        src = nn.new("GeometryNodeCollectionInfo")
        src.inputs["Collection"].default_value = source
        src.inputs["Separate Children"].default_value = True
        src.inputs["Reset Children"].default_value = True
        inst.inputs["Pick Instance"].default_value = True
        idx = nn.new("GeometryNodeInputNamedAttribute")
        idx.data_type = "INT"
        idx.inputs["Name"].default_value = index_attr
        L.new(idx.outputs["Attribute"], inst.inputs["Instance Index"])
    else:
        src = nn.new("GeometryNodeObjectInfo")
        src.inputs["Object"].default_value = source
    L.new(src.outputs["Instances" if isinstance(source, bpy.types.Collection) else "Geometry"], inst.inputs["Instance"])
    sc = nn.new("GeometryNodeInputNamedAttribute")
    sc.data_type = "FLOAT"
    sc.inputs["Name"].default_value = "scale"
    mul = nn.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = scale_mult
    L.new(sc.outputs["Attribute"], mul.inputs[0])
    L.new(mul.outputs["Value"], inst.inputs["Scale"])
    rt = nn.new("GeometryNodeInputNamedAttribute")
    rt.data_type = "FLOAT"
    rt.inputs["Name"].default_value = "rot"
    comb = nn.new("ShaderNodeCombineXYZ")
    L.new(rt.outputs["Attribute"], comb.inputs["Z"])
    eul = nn.new("FunctionNodeEulerToRotation")
    L.new(comb.outputs["Vector"], eul.inputs["Euler"])
    L.new(eul.outputs["Rotation"], inst.inputs["Rotation"])
    L.new(inst.outputs["Instances"], gout.inputs["Geometry"])
    mod = ob.modifiers.new("Instancias", "NODES")
    mod.node_group = ng


if O["trees"] and len(trees_pts):
    tree_ob = points_object("PontosArvores", trees_pts[:, :2], {
        "kind": ("INT", trees_pts[:, 2].astype(np.int32)),
        "scale": ("FLOAT", trees_pts[:, 3]),
        "rot": ("FLOAT", trees_pts[:, 4])})
    instancer(tree_ob, trees, "kind", ST["tree_scale"])

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
if len(houses_pts):
    house_ob = points_object("PontosCasas", houses_pts[:, :2], {
        "rot": ("FLOAT", houses_pts[:, 2]),
        "scale": ("FLOAT", houses_pts[:, 3])})
    instancer(house_ob, house)

# ------------------------------------------------------------------------------------------------ luz, câmara, render
bpy.ops.object.light_add(type="SUN", location=(0, 0, 50))
sun = bpy.context.active_object
sun.data.energy = ST["sun_energy"]
sun.data.color = ST["sun_color"]
sun.data.angle = math.radians(3)                             # sombras ligeiramente suaves
sun.rotation_euler = (math.radians(ST["sun_tilt"]), 0, math.radians(-135))   # luz de noroeste, como nos mapas clássicos
world = bpy.data.worlds.new("Ceu")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (*ST["sky"], 1)
bg.inputs["Strength"].default_value = ST["sky_strength"]

bpy.ops.object.camera_add(location=(SIZE / 2, SIZE / 2, 200), rotation=(0, 0, 0))
cam = bpy.context.active_object
cam.data.type = "ORTHO"
cam.data.ortho_scale = INNER                                  # só o interior; a margem fica fora
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
scene.view_settings.exposure = ST["exposure"]
scene.render.image_settings.file_format = "PNG"
OUT = O["out"] or D / f"render-{O['style']}.png"
scene.render.filepath = str(OUT)

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


# ------------------------------------------------------------------------------------------------ pós-processamento
def box_blur(a, r):
    """Desfoque em caixa (separável, por somas acumuladas): o Blender traz numpy mas não scipy."""
    for axis in (0, 1):
        c = np.cumsum(np.pad(a, [(r + 1, r) if i == axis else (0, 0) for i in range(a.ndim)], mode="edge"), axis=axis)
        a = (np.take(c, range(2 * r + 1, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - 2 * r - 1),
                                                                              axis=axis)) / (2 * r + 1)
    return a


def post(path, style):
    if style == "maqueta":
        return
    img = bpy.data.images.load(str(path))
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    col = px.reshape(h, w, 4)[::-1, :, :3].copy()                   # linha 0 = norte
    pad, inner = int(meta["pad"]), int(meta["tile"])
    yi = pad + np.arange(h) * inner // h
    xi = pad + np.arange(w) * inner // w
    hm = height[yi][:, xi]
    land = (hm > 0).astype(np.float32)
    rng = np.random.default_rng(5)
    if style == "atlas":
        # papel: manchas largas + grão; tinta na costa; tom quente geral
        g = rng.random((h // 64 + 2, w // 64 + 2)).astype(np.float32)
        paper = box_blur(np.kron(g, np.ones((64, 64), np.float32))[:h, :w], 40)
        paper = 0.88 + 0.16 * (paper - paper.min()) / max(np.ptp(paper), 1e-6)
        grain = box_blur(rng.random((h, w)).astype(np.float32), 1)
        col *= (paper * (0.97 + 0.06 * grain))[..., None]
        soft = box_blur(land, 2)
        ink = np.clip(1 - np.abs(soft * 2 - 1) * 3.0, 0, 1)
        col = col * (1 - ink[..., None] * 0.75) + np.array([0.17, 0.13, 0.09]) * ink[..., None] * 0.75
        lum = col @ np.array([0.3, 0.55, 0.15], np.float32)
        col = lum[..., None] + (col - lum[..., None]) * 1.2              # cores mais vivas, como aguarela
        col = col * 0.92 + np.array([0.94, 0.86, 0.68]) * 0.08
    elif style == "sombrio":
        lum = col @ np.array([0.3, 0.55, 0.15], np.float32)
        col = col * 0.55 + lum[..., None] * 0.45                    # dessaturar
        low = np.clip(1 - hm / (HMAX * 0.25), 0, 1) * land          # névoa nas terras baixas
        haze = box_blur(low, 6)
        col = col * (1 - haze[..., None] * 0.28) + np.array([0.42, 0.45, 0.50]) * haze[..., None] * 0.28
        yy, xx = np.mgrid[0:h, 0:w]
        vig = 1 - 0.45 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2) ** 1.3
        col *= vig[..., None]
        col *= np.array([0.94, 0.97, 1.04])
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 1)[::-1]
    img.pixels.foreach_set(out.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()


if O["post"]:
    post(OUT, O["style"])
print("guardado:", OUT)
