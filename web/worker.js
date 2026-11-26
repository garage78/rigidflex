// Runs the repository's own OpenSCAD files in the browser (official OpenSCAD WebAssembly build).
// One OpenSCAD instance per exported body; the compiled wasm module is reused, so only the first run is slow.
import OpenSCAD from "./vendor/openscad/openscad.js";

const wasmUrl = new URL("./vendor/openscad/openscad.wasm", import.meta.url);
let compiled = null;
const sources = new Map();

async function wasmModule() {
  if (!compiled) {
    compiled = WebAssembly.compileStreaming(fetch(wasmUrl)).catch(async () => {
      // servers that do not send application/wasm
      const bytes = await (await fetch(wasmUrl)).arrayBuffer();
      return WebAssembly.compile(bytes);
    });
  }
  return compiled;
}

async function source(file) {
  if (!sources.has(file)) {
    const res = await fetch(new URL(`./scad/${file}`, import.meta.url));
    if (!res.ok) throw new Error(`Could not load scad/${file}`);
    sources.set(file, await res.text());
  }
  return sources.get(file);
}

function literal(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  return JSON.stringify(String(value));
}

async function exportBody(file, params) {
  const mod = await wasmModule();
  const log = [];
  const inst = await OpenSCAD({
    noInitialRun: true,
    print: (s) => log.push(s),
    printErr: (s) => log.push(s),
    instantiateWasm(imports, receive) {
      WebAssembly.instantiate(mod, imports).then((instance) => receive(instance, mod));
      return {};
    },
  });
  inst.FS.writeFile("/model.scad", await source(file));
  const args = ["/model.scad", "-o", "/out.stl", "--backend=manifold", "--export-format=binstl"];
  for (const [k, v] of Object.entries(params)) args.push("-D", `${k}=${literal(v)}`);
  try {
    inst.callMain(args);
  } catch (e) {
    // emscripten reports exit() as an exception; the output file decides success
  }
  let stl = null;
  try {
    stl = inst.FS.readFile("/out.stl");
  } catch (e) {
    stl = null;
  }
  const errors = log.filter((l) => /ERROR/.test(l));
  if (errors.length) throw new Error(errors.join("\n"));
  return stl && stl.length > 84 ? stl.buffer.slice(stl.byteOffset, stl.byteOffset + stl.byteLength) : null;
}

self.onmessage = async ({ data }) => {
  const { id, file, bodies } = data;
  try {
    const out = [];
    for (const body of bodies) {
      const stl = await exportBody(file, body.params);
      if (stl) out.push({ ...body, stl });
      self.postMessage({ id, progress: out.length / bodies.length });
    }
    self.postMessage({ id, bodies: out }, out.map((b) => b.stl));
  } catch (e) {
    self.postMessage({ id, error: String(e.message || e) });
  }
};

wasmModule(); // start compiling as soon as the page loads
