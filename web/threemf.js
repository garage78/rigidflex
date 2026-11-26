// Multi-material 3MF writer for the browser: the same project layout as rigidflex/threemf.py
// (3D/Objects/*.model + Metadata/model_settings.config), which Snapmaker Orca and OrcaSlicer open
// with every part already on its toolhead. No dependencies: a tiny stored (uncompressed) ZIP writer is included.

export function parseSTL(buffer) {
  const view = new DataView(buffer);
  const count = view.getUint32(80, true);
  const pos = new Float32Array(count * 9);
  let off = 84;
  for (let i = 0; i < count; i++) {
    for (let j = 0; j < 9; j++) pos[i * 9 + j] = view.getFloat32(off + 12 + j * 4, true);
    off += 50;
  }
  return pos;
}

export function meshVolume(pos) {
  let v = 0;
  for (let i = 0; i < pos.length; i += 9) {
    const [ax, ay, az, bx, by, bz, cx, cy, cz] = pos.subarray(i, i + 9);
    v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
  }
  return Math.abs(v) / 6; // mm³
}

export function bounds(meshes) {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const pos of meshes)
    for (let i = 0; i < pos.length; i += 3)
      for (let k = 0; k < 3; k++) {
        lo[k] = Math.min(lo[k], pos[i + k]);
        hi[k] = Math.max(hi[k], pos[i + k]);
      }
  return { lo, hi };
}

const fmt = (x) => {
  const s = x.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
  return s === "-0" || s === "" ? "0" : s;
};
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const uuid = () =>
  crypto.randomUUID ? crypto.randomUUID() : "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx".replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));

function meshXML(pos) {
  const index = new Map();
  const verts = [];
  const tris = [];
  for (let i = 0; i < pos.length; i += 9) {
    const ids = [];
    for (let j = 0; j < 9; j += 3) {
      const key = `${fmt(pos[i + j])} ${fmt(pos[i + j + 1])} ${fmt(pos[i + j + 2])}`;
      let id = index.get(key);
      if (id === undefined) {
        id = index.size;
        index.set(key, id);
        const [x, y, z] = key.split(" ");
        verts.push(`<vertex x="${x}" y="${y}" z="${z}"/>`);
      }
      ids.push(id);
    }
    if (ids[0] !== ids[1] && ids[1] !== ids[2] && ids[0] !== ids[2])
      tris.push(`<triangle v1="${ids[0]}" v2="${ids[1]}" v3="${ids[2]}"/>`);
  }
  return { xml: `<mesh><vertices>${verts.join("")}</vertices><triangles>${tris.join("")}</triangles></mesh>`, ntri: tris.length };
}

const NS =
  'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" ' +
  'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" ' +
  'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"';

/**
 * objects: [{ name, offset: [x,y,z], settings: {key: value}, volumes: [{ name, extruder, pos: Float32Array }] }]
 * Returns a Blob (model/3mf).
 */
export function write3MF(objects, title = "rigidflex") {
  const files = {};
  const resources = [], build = [], rels = [];
  const cfg = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"];
  let nextId = 1;
  objects.forEach((obj, n0) => {
    const n = n0 + 1;
    const sub = `/3D/Objects/object_${n}.model`;
    const subObjects = [], components = [], parts = [];
    for (const vol of obj.volumes) {
      const pid = nextId++;
      const { xml, ntri } = meshXML(vol.pos);
      subObjects.push(`<object id="${pid}" p:UUID="${uuid()}" type="model">${xml}</object>`);
      components.push(`<component p:path="${sub}" objectid="${pid}" p:UUID="${uuid()}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>`);
      parts.push({ pid, vol, ntri });
    }
    const oid = nextId++;
    files[sub.slice(1)] =
      `<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" ${NS}>` +
      `<metadata name="BambuStudio:3mfVersion">1</metadata><resources>${subObjects.join("")}</resources><build/></model>`;
    rels.push(`<Relationship Target="${sub}" Id="rel-${n}" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>`);
    resources.push(`<object id="${oid}" p:UUID="${uuid()}" type="model"><components>${components.join("")}</components></object>`);
    const [dx, dy, dz] = obj.offset || [0, 0, 0];
    build.push(`<item objectid="${oid}" p:UUID="${uuid()}" transform="1 0 0 0 1 0 0 0 1 ${fmt(dx)} ${fmt(dy)} ${fmt(dz)}" printable="1"/>`);
    cfg.push(`<object id="${oid}">`, `<metadata key="name" value="${esc(obj.name)}"/>`, `<metadata key="extruder" value="${obj.volumes[0].extruder}"/>`);
    for (const [k, v] of Object.entries(obj.settings || {})) cfg.push(`<metadata key="${esc(k)}" value="${esc(v)}"/>`);
    for (const { pid, vol, ntri } of parts) {
      cfg.push(
        `<part id="${pid}" subtype="normal_part">`,
        `<metadata key="name" value="${esc(vol.name)}"/>`,
        '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
        `<metadata key="extruder" value="${vol.extruder}"/>`,
        `<mesh_stat face_count="${ntri}" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>`,
        "</part>"
      );
    }
    cfg.push("</object>");
  });
  cfg.push("</config>");

  const ordered = [
    ["[Content_Types].xml",
      '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>' +
      '<Default Extension="png" ContentType="image/png"/><Default Extension="config" ContentType="text/xml"/></Types>'],
    ["_rels/.rels",
      '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'],
    ["3D/3dmodel.model",
      `<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" ${NS}>` +
      '<metadata name="Application">rigidflex</metadata><metadata name="BambuStudio:3mfVersion">1</metadata>' +
      `<metadata name="Title">${esc(title)}</metadata><resources>${resources.join("")}</resources>` +
      `<build p:UUID="${uuid()}">${build.join("")}</build></model>`],
    ["3D/_rels/3dmodel.model.rels",
      '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      `${rels.join("")}</Relationships>`],
    ...Object.entries(files),
    ["Metadata/model_settings.config", cfg.join("\n")],
  ];
  return new Blob([zipStore(ordered)], { type: "model/3mf" });
}

// ---------- minimal ZIP (method 0 = stored) ----------
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function zipStore(entries) {
  const enc = new TextEncoder();
  const chunks = [], central = [];
  let offset = 0;
  const d = new Date();
  const dosTime = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
  const dosDate = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  for (const [name, content] of entries) {
    const nameBytes = enc.encode(name);
    const data = typeof content === "string" ? enc.encode(content) : content;
    const crc = crc32(data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // UTF-8 names
    local.setUint16(8, 0, true);
    local.setUint16(10, dosTime, true);
    local.setUint16(12, dosDate, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, nameBytes.length, true);
    local.setUint16(28, 0, true);
    chunks.push(new Uint8Array(local.buffer), nameBytes, data);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true);
    cen.setUint16(4, 20, true);
    cen.setUint16(6, 20, true);
    cen.setUint16(8, 0x0800, true);
    cen.setUint16(10, 0, true);
    cen.setUint16(12, dosTime, true);
    cen.setUint16(14, dosDate, true);
    cen.setUint32(16, crc, true);
    cen.setUint32(20, data.length, true);
    cen.setUint32(24, data.length, true);
    cen.setUint16(28, nameBytes.length, true);
    cen.setUint32(42, offset, true);
    central.push(new Uint8Array(cen.buffer), nameBytes);
    offset += 30 + nameBytes.length + data.length;
  }
  const cenSize = central.reduce((s, c) => s + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, entries.length, true);
  end.setUint16(10, entries.length, true);
  end.setUint32(12, cenSize, true);
  end.setUint32(16, offset, true);
  const all = [...chunks, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(all.reduce((s, c) => s + c.length, 0));
  let p = 0;
  for (const c of all) {
    out.set(c, p);
    p += c.length;
  }
  return out;
}
