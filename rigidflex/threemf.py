"""Minimal multi-material 3MF writer.

Each object is made of named parts (one mesh per material), and each part is
assigned to a toolhead. The file uses the Bambu/Orca project layout
(`3D/Objects/*.model` + `Metadata/model_settings.config`), which OrcaSlicer and
Snapmaker Orca open with the parts and toolhead assignments intact.

Standard library only.
"""
from __future__ import annotations

import struct
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

Triangle = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


def read_stl(path: str | Path) -> list[Triangle]:
    """Read an ASCII or binary STL into a list of triangles."""
    data = Path(path).read_bytes()
    tris: list[Triangle] = []
    is_ascii = data[:5].lower() == b"solid" and b"facet" in data[:1024]
    if is_ascii:
        verts: list[tuple[float, float, float]] = []
        for line in data.decode("ascii", errors="replace").splitlines():
            parts = line.split()
            if parts and parts[0] == "vertex":
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                if len(verts) == 3:
                    tris.append((verts[0], verts[1], verts[2]))
                    verts = []
    else:
        (count,) = struct.unpack_from("<I", data, 80)
        off = 84
        for _ in range(count):
            v = struct.unpack_from("<12f", data, off)
            tris.append(((v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11])))
            off += 50
    if not tris:
        raise ValueError(f"No triangles found in {path}")
    return tris


@dataclass
class Volume:
    name: str
    triangles: list[Triangle]
    extruder: int  # 1-based toolhead number


@dataclass
class Object3MF:
    name: str
    volumes: list[Volume]
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    settings: dict[str, str] = field(default_factory=dict)  # per-object slicer settings


def _fmt(x: float) -> str:
    return f"{x:.5f}".rstrip("0").rstrip(".") or "0"


_NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
       'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
       'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')


def _mesh_xml(triangles: list[Triangle]) -> tuple[str, int]:
    index: dict[tuple[float, float, float], int] = {}
    verts: list[str] = []
    tris: list[str] = []
    for tri in triangles:
        ids = []
        for p in tri:
            key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
            if key not in index:
                index[key] = len(index)
                verts.append(f'<vertex x="{_fmt(key[0])}" y="{_fmt(key[1])}" z="{_fmt(key[2])}"/>')
            ids.append(index[key])
        if len({*ids}) == 3:  # skip degenerate triangles
            tris.append(f'<triangle v1="{ids[0]}" v2="{ids[1]}" v3="{ids[2]}"/>')
    return "<mesh><vertices>" + "".join(verts) + "</vertices><triangles>" + "".join(tris) + "</triangles></mesh>", len(tris)


def write_3mf(path: str | Path, objects: list[Object3MF], title: str = "rigidflex") -> Path:
    path = Path(path)
    files: dict[str, str] = {}
    resources: list[str] = []
    build: list[str] = []
    rels: list[str] = []
    cfg: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    next_id = 1

    for n, obj in enumerate(objects, start=1):
        sub_path = f"/3D/Objects/object_{n}.model"
        sub_objects: list[str] = []
        components: list[str] = []
        part_ids: list[tuple[int, Volume, int]] = []
        for vol in obj.volumes:
            pid = next_id
            next_id += 1
            mesh, ntri = _mesh_xml(vol.triangles)
            sub_objects.append(f'<object id="{pid}" p:UUID="{uuid.uuid4()}" type="model">{mesh}</object>')
            components.append(f'<component p:path="{sub_path}" objectid="{pid}" p:UUID="{uuid.uuid4()}" '
                              'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
            part_ids.append((pid, vol, ntri))
        oid = next_id
        next_id += 1
        files[sub_path.lstrip("/")] = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {_NS}>'
            '<metadata name="BambuStudio:3mfVersion">1</metadata><resources>'
            + "".join(sub_objects) + "</resources><build/></model>"
        )
        rels.append(f'<Relationship Target="{sub_path}" Id="rel-{n}" '
                    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
        resources.append(f'<object id="{oid}" p:UUID="{uuid.uuid4()}" type="model"><components>'
                         + "".join(components) + "</components></object>")
        dx, dy, dz = obj.offset
        build.append(f'<item objectid="{oid}" p:UUID="{uuid.uuid4()}" '
                     f'transform="1 0 0 0 1 0 0 0 1 {_fmt(dx)} {_fmt(dy)} {_fmt(dz)}" printable="1"/>')

        cfg.append(f'<object id="{oid}">')
        cfg.append(f'<metadata key="name" value={quoteattr(obj.name)}/>')
        cfg.append(f'<metadata key="extruder" value="{obj.volumes[0].extruder}"/>')
        for key, value in obj.settings.items():
            cfg.append(f'<metadata key={quoteattr(key)} value={quoteattr(value)}/>')
        for pid, vol, ntri in part_ids:
            cfg.append(f'<part id="{pid}" subtype="normal_part">')
            cfg.append(f'<metadata key="name" value={quoteattr(vol.name)}/>')
            cfg.append('<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>')
            cfg.append(f'<metadata key="extruder" value="{vol.extruder}"/>')
            cfg.append(f'<mesh_stat face_count="{ntri}" edges_fixed="0" degenerate_facets="0" '
                       'facets_removed="0" facets_reversed="0" backwards_edges="0"/>')
            cfg.append("</part>")
        cfg.append("</object>")
    cfg.append("</config>")

    files["3D/3dmodel.model"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {_NS}>'
        '<metadata name="Application">rigidflex</metadata>'
        '<metadata name="BambuStudio:3mfVersion">1</metadata>'
        f'<metadata name="Title">{title}</metadata>'
        "<resources>" + "".join(resources) + "</resources>"
        f'<build p:UUID="{uuid.uuid4()}">' + "".join(build) + "</build></model>"
    )
    files["3D/_rels/3dmodel.model.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels) + "</Relationships>"
    )
    files["Metadata/model_settings.config"] = "\n".join(cfg)
    files["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="config" ContentType="text/xml"/>'
        "</Types>"
    )
    files["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model", "3D/_rels/3dmodel.model.rels"]:
            z.writestr(name, files.pop(name))
        for name, data in files.items():
            z.writestr(name, data)
    return path
