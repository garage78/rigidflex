import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MODELS, TOOLS } from "./models.js";
import { parseSTL, meshVolume, bounds, write3MF } from "./threemf.js";

const BED = 270; // Snapmaker U1 build plate, mm
const $ = (s) => document.querySelector(s);

// ---------------- state ----------------
let model = MODELS[0];
const values = {};
for (const m of MODELS) values[m.id] = Object.fromEntries(m.controls.map((c) => [c.id, c.value]));
let result = null; // { modelId, v, bodies: [{name, tool, explode, pos}] }
let jobId = 0;
let firstRun = true;

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });

// ---------------- viewer ----------------
const view = $("#view");
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.localClippingEnabled = true;
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
// the wheel scrolls the page until the viewer is clicked, so the 3D view never traps scrolling
controls.enableZoom = false;
view.addEventListener("pointerdown", () => (controls.enableZoom = true));
view.addEventListener("pointerleave", () => (controls.enableZoom = false));
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 2.2));
const key = new THREE.DirectionalLight(0xffffff, 2.4);
key.position.set(1, -1.5, 2.2);
scene.add(key);
const rim = new THREE.DirectionalLight(0xffffff, 0.8);
rim.position.set(-1.5, 1.2, 0.6);
scene.add(rim);
const group = new THREE.Group();
scene.add(group);
let grid = null;
const clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);

function resize() {
  const { clientWidth: w, clientHeight: h } = view;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(view);

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});

function shade(hex, f) {
  const c = new THREE.Color(hex);
  return c.multiplyScalar(f);
}

let meshes = [];
let size = 50;
let center = new THREE.Vector3();

function showResult(fit) {
  group.clear();
  meshes = [];
  const box = new THREE.Box3();
  for (const b of result.bodies) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(b.pos, 3));
    geo.computeVertexNormals();
    geo.computeBoundingBox();
    box.union(geo.boundingBox);
    const color = TOOLS[b.tool].color;
    const front = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: b.tool === 1 ? 0.45 : 0.7, metalness: 0.02, side: THREE.FrontSide, clipShadows: true }));
    const back = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: shade(color, 0.55), side: THREE.BackSide }));
    const g = new THREE.Group();
    g.add(front, back);
    g.userData = { body: b };
    group.add(g);
    meshes.push(g);
  }
  center = box.getCenter(new THREE.Vector3());
  const dims = box.getSize(new THREE.Vector3());
  size = Math.max(dims.x, dims.y, dims.z);
  if (grid) scene.remove(grid);
  const span = Math.ceil((Math.max(dims.x, dims.y) * 1.8) / 10) * 10;
  grid = new THREE.GridHelper(span, span / 5, 0xb9b4aa, 0xd8d3c9);
  grid.rotation.x = Math.PI / 2;
  grid.position.set(center.x, center.y, box.min.z - 0.05);
  scene.add(grid);
  applyView();
  if (fit) {
    const r = Math.max(size, 20);
    camera.position.set(center.x + r * 0.9, center.y - r * 1.5, center.z + r * 1.0);
    controls.target.copy(center);
    camera.near = r / 100;
    camera.far = r * 50;
    camera.updateProjectionMatrix();
  }
  updateLegend();
}

function applyView() {
  const explode = Number($("#explode").value);
  const cut = $("#section").checked;
  const axis = model.section || "y";
  const n = new THREE.Vector3(axis === "x" ? -1 : 0, axis === "y" ? -1 : 0, axis === "z" ? -1 : 0);
  // the cut sits slightly off-centre so round parts show their wall, not a seam
  clipPlane.set(n, -n.dot(center) - (axis === "z" ? 0 : 0.001));
  const hidden = new Set([...document.querySelectorAll("[data-hide]:not(:checked)")].map((e) => Number(e.dataset.hide)));
  for (const g of meshes) {
    const { body } = g.userData;
    const d = body.explode;
    g.position.set(d[0] * explode * size * 0.45, d[1] * explode * size * 0.45, d[2] * explode * size * 0.35);
    g.visible = !hidden.has(body.tool);
    for (const m of g.children) m.material.clippingPlanes = cut ? [clipPlane] : [];
  }
}
$("#explode").addEventListener("input", applyView);
$("#section").addEventListener("change", applyView);

// ---------------- form ----------------
function renderTabs() {
  const tabs = $("#tabs");
  tabs.innerHTML = "";
  for (const m of MODELS) {
    const b = document.createElement("button");
    b.type = "button";
    b.role = "tab";
    b.textContent = m.label;
    b.setAttribute("aria-selected", m === model);
    b.addEventListener("click", () => {
      if (m === model) return;
      model = m;
      renderTabs();
      renderForm();
      schedule(true);
    });
    tabs.appendChild(b);
  }
}

function renderForm() {
  const v = values[model.id];
  const limits = model.fix ? model.fix(v) : {};
  $("#model-title").textContent = model.title;
  $("#model-blurb").textContent = model.blurb;
  const form = $("#params");
  form.innerHTML = "";
  for (const c of model.controls) {
    if (c.show && !c.show(v)) continue;
    const row = document.createElement("div");
    row.className = `field field-${c.type}`;
    const id = `p-${c.id}`;
    if (c.type === "range") {
      const max = limits[c.id]?.max ?? c.max;
      row.innerHTML = `<label for="${id}"><span>${c.label}</span><output id="${id}-out"></output></label>
        <input id="${id}" type="range" min="${c.min}" max="${Math.max(c.min, max)}" step="${c.step}" value="${v[c.id]}">
        ${c.hint ? `<small>${c.hint}</small>` : ""}`;
      const input = row.querySelector("input");
      const out = row.querySelector("output");
      const show = () => (out.textContent = `${Number(input.value)}${c.unit ? " " + c.unit : ""}`);
      show();
      input.addEventListener("input", () => {
        v[c.id] = Number(input.value);
        show();
        if (model.fix) {
          const lim = model.fix(v);
          for (const [k, l] of Object.entries(lim)) {
            const other = $(`#p-${k}`);
            if (other) {
              other.max = Math.max(Number(other.min), l.max);
              if (Number(other.value) !== v[k]) {
                other.value = v[k];
                other.dispatchEvent(new Event("refresh"));
              }
            }
          }
        }
        schedule();
      });
      input.addEventListener("refresh", show);
    } else if (c.type === "toggle") {
      row.innerHTML = `<label class="switch"><input id="${id}" type="checkbox" ${v[c.id] ? "checked" : ""}><span>${c.label}</span></label>`;
      row.querySelector("input").addEventListener("change", (e) => {
        v[c.id] = e.target.checked;
        renderForm();
        schedule();
      });
    } else if (c.type === "select") {
      row.innerHTML = `<label for="${id}"><span>${c.label}</span></label><select id="${id}">${c.options
        .map(([val, text]) => `<option value="${val}" ${String(v[c.id]) === val ? "selected" : ""}>${text}</option>`)
        .join("")}</select>`;
      row.querySelector("select").addEventListener("change", (e) => {
        v[c.id] = e.target.value;
        renderForm();
        schedule();
      });
    }
    form.appendChild(row);
  }
}

// ---------------- build ----------------
let timer = null;
function schedule(fit = false) {
  clearTimeout(timer);
  timer = setTimeout(() => build(fit), fit ? 0 : 350);
}

function setStatus(text, busy) {
  $("#status").textContent = text;
  view.classList.toggle("busy", !!busy);
  $("#download").disabled = !!busy || !result;
}

function build(fit) {
  const v = { ...values[model.id] };
  const bodies = model.bodies(v);
  const id = ++jobId;
  setStatus(firstRun ? "Loading OpenSCAD in your browser (11 MB, first time only)…" : `Building ${bodies.length} bodies…`, true);
  const t0 = performance.now();
  worker.onmessage = ({ data }) => {
    if (data.id !== id) return;
    if (data.progress !== undefined) {
      if (!firstRun || data.progress > 0) setStatus(`Building… ${Math.round(data.progress * bodies.length)} of ${bodies.length} bodies`, true);
      return;
    }
    if (data.error) {
      setStatus(`OpenSCAD reported an error: ${data.error}`, false);
      return;
    }
    const wasFirst = firstRun;
    firstRun = false;
    const modelChanged = !result || result.modelId !== model.id;
    result = { modelId: model.id, v, bodies: data.bodies.map((b) => ({ ...b, pos: parseSTL(b.stl) })) };
    showResult(fit || modelChanged || wasFirst);
    setStatus(`Built in ${((performance.now() - t0) / 1000).toFixed(1)} s from scad/${model.file}`, false);
  };
  worker.postMessage({ id, file: model.file, bodies: bodies.map((b) => ({ name: b.name, tool: b.tool, explode: b.explode, params: b.params })) });
}

// ---------------- legend & stats ----------------
function updateLegend() {
  const copies = model.copies(result.v);
  const byTool = {};
  for (const b of result.bodies) byTool[b.tool] = (byTool[b.tool] || 0) + meshVolume(b.pos);
  const rows = Object.entries(byTool)
    .sort(([a], [b]) => a - b)
    .map(([tool, mm3]) => {
      const t = TOOLS[tool];
      const g = (mm3 / 1000) * t.density * copies;
      return `<li><label><input type="checkbox" data-hide="${tool}" checked>
        <i style="background:${t.color}"></i><b>T${tool}</b> ${t.label} <small>${t.detail}</small></label>
        <span>${g < 10 ? g.toFixed(1) : Math.round(g)} g</span></li>`;
    })
    .join("");
  $("#legend").innerHTML = rows;
  $("#copies-note").textContent = copies > 1 ? `Weights for the whole plate (${copies} copies).` : "";
  document.querySelectorAll("[data-hide]").forEach((e) => e.addEventListener("change", applyView));
}

// ---------------- download ----------------
$("#download").addEventListener("click", () => {
  if (!result) return;
  const m = MODELS.find((x) => x.id === result.modelId);
  const copies = m.copies(result.v);
  const step = m.spacing ? m.spacing(result.v) : [0, 0, 0];
  const { lo, hi } = bounds(result.bodies.map((b) => b.pos));
  const total = [hi[0] - lo[0] + step[0] * (copies - 1), hi[1] - lo[1] + step[1] * (copies - 1)];
  const base = [BED / 2 - total[0] / 2 - lo[0], BED / 2 - total[1] / 2 - lo[1], -lo[2]];
  const name = m.filename(result.v);
  const objects = [];
  for (let i = 0; i < copies; i++)
    objects.push({
      name: copies > 1 ? `${name}_${i + 1}` : name,
      offset: [base[0] + step[0] * i, base[1] + step[1] * i, base[2]],
      settings: m.settings ? m.settings(result.v) : {},
      volumes: result.bodies.map((b) => ({ name: b.name, extruder: b.tool, pos: b.pos })),
    });
  const blob = write3MF(objects, name);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${name}.3mf`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
});

renderTabs();
renderForm();
schedule(true);
