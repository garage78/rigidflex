// Builds a two-object, three-part 3MF with the configurator's own writer (web/threemf.js).
// Run by tests/test_rigidflex.py, which then opens the file and checks parts and toolheads.
import { writeFileSync } from "node:fs";
import { write3MF, meshVolume } from "../web/threemf.js";

function cube(x0, size) {
  const [a, b] = [x0, x0 + size];
  const v = (x, y, z) => [x, y, z];
  const q = (p0, p1, p2, p3) => [...p0, ...p1, ...p2, ...p0, ...p2, ...p3];
  return new Float32Array([
    ...q(v(a, a, a), v(a, b, a), v(b, b, a), v(b, a, a)), // bottom
    ...q(v(a, a, b), v(b, a, b), v(b, b, b), v(a, b, b)), // top
    ...q(v(a, a, a), v(b, a, a), v(b, a, b), v(a, a, b)),
    ...q(v(b, a, a), v(b, b, a), v(b, b, b), v(b, a, b)),
    ...q(v(b, b, a), v(a, b, a), v(a, b, b), v(b, b, b)),
    ...q(v(a, b, a), v(a, a, a), v(a, a, b), v(a, b, b)),
  ]);
}

const vol = meshVolume(cube(0, 10));
if (Math.abs(vol - 1000) > 1e-6) throw new Error(`cube volume ${vol}`);
const volumes = [
  { name: "rigid", extruder: 1, pos: cube(0, 10) },
  { name: "tpu95a", extruder: 2, pos: cube(10, 10) },
  { name: "tpu85a", extruder: 3, pos: cube(20, 10) },
];
const objects = [0, 1].map((i) => ({ name: `test_${i + 1}`, offset: [100, 100 + 30 * i, 0], settings: { interlocking_beam: "1" }, volumes }));
const blob = write3MF(objects, "web test");
writeFileSync(process.argv[2], Buffer.from(await blob.arrayBuffer()));
console.log("ok");
