// The parts the configurator offers. Each one maps UI values to the parameters of a .scad file in scad/,
// and lists the bodies to export, each on its own U1 toolhead.

export const TOOLS = {
  1: { label: "Rigid", detail: "PETG, ASA or PLA", color: "#4f7ea8", density: 1.27 },
  2: { label: "TPU 95A", detail: "the usual TPU", color: "#e8772e", density: 1.21 },
  3: { label: "TPU 85A", detail: "soft TPU", color: "#e9b824", density: 1.2 },
};

const num = (id, label, min, max, step, value, unit = "mm", hint = "") => ({ id, type: "range", label, min, max, step, value, unit, hint });

export const MODELS = [
  {
    id: "grommet",
    label: "Grommet",
    title: "Grommet / cable pass-through",
    blurb:
      "A rigid ring snaps into the panel hole and a TPU membrane seals around the cable with a 15 % interference fit. Set the cable to 0 for a blanking plug. Three materials puts the sealing lip in soft TPU 85A.",
    file: "grommet.scad",
    controls: [
      num("panel_hole_d", "Panel hole", 12, 60, 0.5, 25),
      num("panel_thick", "Panel thickness", 0.5, 4, 0.1, 1.2),
      num("cable_d", "Cable or rod", 0, 40, 0.5, 8, "mm", "0 = blanking plug"),
      num("flange", "Flange beyond the hole", 2, 10, 0.5, 4),
      num("membrane", "Membrane thickness", 0.8, 2.4, 0.2, 1.2),
      { id: "three", type: "toggle", label: "Three materials (soft 85A sealing lip)", value: false },
    ],
    fix(v) {
      v.cable_d = Math.min(v.cable_d, Math.floor((v.panel_hole_d - 6.6) * 2) / 2);
      return { cable_d: { max: Math.floor((v.panel_hole_d - 6.6) * 2) / 2 } };
    },
    bodies(v) {
      const p = { panel_hole_d: v.panel_hole_d, panel_thick: v.panel_thick, cable_d: v.cable_d, flange: v.flange, membrane: v.membrane, three: v.three };
      const b = [
        { name: "rigid", tool: 1, params: { ...p, part: "rigid" }, explode: [0, 0, 0] },
        { name: "tpu95a", tool: 2, params: { ...p, part: "flex" }, explode: [0, 0, 1] },
      ];
      if (v.three && v.cable_d > 0) b.push({ name: "tpu85a_lip", tool: 3, params: { ...p, part: "soft" }, explode: [0, 0, 2] });
      return b;
    },
    filename: (v) => `grommet_hole${v.panel_hole_d}_cable${v.cable_d}${v.three ? "_3mat" : ""}`,
    copies: () => 1,
    section: "y",
  },
  {
    id: "softjaw",
    label: "Soft jaws",
    title: "Magnetic soft jaws for a vise",
    blurb:
      "A rigid plate with a TPU face, for holding painted, chromed or printed parts without marking them. The TPU is printed on top of the plate and keys into grooves. Press 10 × 3 mm magnets into the back.",
    file: "soft_jaw.scad",
    controls: [
      num("jaw_w", "Jaw width", 40, 200, 1, 100),
      num("jaw_h", "Jaw height", 12, 60, 1, 25),
      num("plate_t", "Rigid plate", 3, 8, 0.5, 4),
      num("pad_t", "TPU pad", 1.2, 5, 0.2, 2.4),
      num("magnets", "Magnets", 0, 6, 1, 3, ""),
      { id: "face", type: "select", label: "TPU face", options: [["ribbed", "Ribbed"], ["smooth", "Smooth"]], value: "ribbed" },
      { id: "pair", type: "toggle", label: "Print a pair", value: true },
    ],
    bodies(v) {
      const p = { jaw_w: v.jaw_w, jaw_h: v.jaw_h, plate_t: v.plate_t, pad_t: v.pad_t, magnets: v.magnets, face: v.face };
      return [
        { name: "rigid", tool: 1, params: { ...p, part: "rigid" }, explode: [0, 0, 0] },
        { name: "tpu95a", tool: 2, params: { ...p, part: "flex" }, explode: [0, 0, 1] },
      ];
    },
    filename: (v) => `soft_jaw_${v.jaw_w}x${v.jaw_h}`,
    copies: (v) => (v.pair ? 2 : 1),
    spacing: (v) => [0, v.jaw_h + 8, 0],
    section: "x",
  },
  {
    id: "coupon",
    label: "Coupons",
    title: "Bond-test coupons",
    blurb:
      "The dog-bones from the rigidflex test campaign. Print a plate with your own materials, pull them, and add your numbers to the open dataset.",
    file: "coupons.scad",
    controls: [
      {
        id: "series", type: "select", label: "Series",
        options: [["A", "A · in-layer butt joint"], ["B", "B · lap joint (layer bond)"], ["G", "G · graded, three materials"]],
        value: "A",
      },
      { id: "joint", type: "select", label: "Joint", options: [["dovetail", "Dovetail"], ["sawtooth", "Sawtooth"], ["flat", "Flat"], ["orca-beam", "Flat + Orca beam interlocking"]], value: "dovetail", show: (v) => v.series === "A" },
      { id: "overlap", type: "select", label: "Overlap", options: [["20", "20 mm"], ["10", "10 mm"]], value: "20", show: (v) => v.series === "B" },
      { id: "order", type: "select", label: "Print order", options: [["tpu-on-rigid", "TPU printed on rigid"], ["rigid-on-tpu", "Rigid printed on TPU"]], value: "tpu-on-rigid", show: (v) => v.series === "B" },
      { id: "graded", type: "select", label: "Joint", options: [["graded", "Rigid → 6 mm TPU 95A band → TPU 85A"], ["direct", "Rigid → TPU 85A directly"]], value: "graded", show: (v) => v.series === "G" },
      num("copies", "Coupons on the plate", 1, 5, 1, 5, ""),
    ],
    bodies(v) {
      if (v.series === "B") {
        const p = { coupon: "B", overlap: Number(v.overlap), rigid_below: v.order === "tpu-on-rigid" };
        const up = v.order === "tpu-on-rigid" ? 1 : -1;
        return [
          { name: "rigid", tool: 1, params: { ...p, part: "rigid" }, explode: [0, 0, 0] },
          { name: "tpu95a", tool: 2, params: { ...p, part: "flex" }, explode: [0, 0, up] },
        ];
      }
      if (v.series === "G") {
        const p = { coupon: "A", joint: "flat", buffer: v.graded === "graded" ? 6 : 0 };
        const b = [{ name: "rigid", tool: 1, params: { ...p, part: "rigid" }, explode: [-1, 0, 0] }];
        if (v.graded === "graded") b.push({ name: "tpu95a_band", tool: 2, params: { ...p, part: "buffer" }, explode: [0, 0, 0] });
        b.push({ name: "tpu85a", tool: 3, params: { ...p, part: "flex" }, explode: [1, 0, 0] });
        return b;
      }
      const p = { coupon: "A", joint: v.joint === "orca-beam" ? "flat" : v.joint };
      return [
        { name: "rigid", tool: 1, params: { ...p, part: "rigid" }, explode: [-1, 0, 0] },
        { name: "tpu95a", tool: 2, params: { ...p, part: "flex" }, explode: [1, 0, 0] },
      ];
    },
    settings: (v) => (v.series === "A" && v.joint === "orca-beam" ? { interlocking_beam: "1" } : {}),
    filename: (v) =>
      v.series === "A" ? `coupons_A_${v.joint}` : v.series === "B" ? `coupons_B_overlap${v.overlap}_${v.order}` : `coupons_G_${v.graded}`,
    copies: (v) => v.copies,
    spacing: () => [0, 30, 0],
    section: "y",
  },
];
