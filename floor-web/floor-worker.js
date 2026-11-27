// floor-worker.js - the HX Unbound Floor build (helix-floor/floor/build_floor2.py's stages) in the browser.
// Pyodide runs the repository's own Python on the user's stock Helix Floor 3.80.0 file, without the SHARC simulator check
// (minutes here), then compares the result's MD5 with the same mix built on a PC.
//
// In:  { stock: ArrayBuffer, options: { splash, pedal, meter, names } }
// Out: { type: "progress", step, of, text } | { type: "log", text }
//      { type: "done", file, bytes: ArrayBuffer, md5, mix, reference, tested } | { type: "error", text }
//      reference: "match" | "differs" | "none" (no PC build recorded for this mix); tested: the mix has run on a Floor
"use strict";

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var STOCK_MD5 = "805caa03e8a30fd6ff7892f32ed5a9f4";   // Helix_Floor_v3.80.0_0x7d01f5efb.hxf
var NAMES_CSV = "helix-floor/names/real_names.csv";
var SPLASH = "helix-floor/floor/splash/unbound_boot.png";

// A mix is a letter per toggle that is on: S boot screen, P NAM Pedal, M meter and Focus View, N real-gear names.
var REFERENCE = {        // mix -> MD5 of the PC build of the same mix (build_floor2.py, same environment)
  "": "5e39ee8a64a829deca1cf441d9000d7c",
  "S": "0b7e1d70e1651b198c34ab4ebc26524c",
  "P": "fbd01b44c0b05cb393d369318f027aff",
  "M": "c277582efacc9ed20d4958a484d70fe7",
  "SP": "769b5df580f34b27ba5ee0fbe29bdb0b",
  "SM": "f18db9c832977ab08c99b6a9fd657ec4",
  "PM": "7ecbdfe87b418890e61c610dcb7cdf64",
  "SPM": "2f1bd7a239472761056b4f8f5e1a2bf9",
  "N": "5ab351d4a68a5b19db4666295737f0a5",
  "SN": "2fa18eef0b14c91c720e79df7cd7a5a1",
  "PN": "92954063384f18074511326b018551d6",
  "MN": "fc74318e8e8d050231e69917294de9e3",
  "SPN": "698e061a527f4dff1cf617d799b7b43c",
  "SMN": "94d0f43f5e020dfd5c53ed63a50a4847",
  "PMN": "0acb49d8271b257b927d397d347f4768",
  "SPMN": "2fce003c22e5117a85849ceee1a7c32f",
};
var TESTED = {};         // mix -> MD5 of the build that was run on a Helix Floor (none of these mixes yet)

// Every build: the faster two-NAM kernel layout, the DSP rewrites, the editor's screen mirror, the stopped-clock fix.
var BASE_ENV = {
  NAM_KERNEL: "nam_floor5", NAM_MAX_BLOCKS: "16", NAM_DIAG: "1",      // NAM_DIAG: no simulator check
  NAM_PAIR: "1", NAM_NOSENT: "1", NAM_LB_B0: "2", NAM_DSP_COST: "3250", NAM_PR1: "0",
  NAM_SCREEN_MIRROR: "1", NAM_CLK_STOP: "1",
};
var TOGGLE_ENV = {
  pedal: { NAM_PEDAL: "1" },
  meter: { NAM_DSP_METER: "1", NAM_FOCUS_VIEW: "1", NAM_EMMC_ART: "1" },
  names: { NAM_NAMES: "/work/names.csv" },
};

// What the build reads, relative to the repository root (the page sits in floor-web/).
var SOURCES = [
  "helix-floor/floor/upstream.py",
  "helix-floor/floor/arm_guards.py",
  "helix-floor/floor/ir_title.py",
  "helix-floor/floor/screen_mirror.py",
  "helix-floor/floor/dsp_meter.py",
  "helix-floor/floor/focus_emmc.py",
  "helix-floor/floor/clk_stop.py",
  "helix-floor/floor/partition_guard.py",
  "helix-floor/floor/spec555.py",
  "helix-floor/floor/unbound_info.py",
  "helix-floor/floor/floor_hxf.py",
  "helix-floor/floor/nam_floor.py",
  "helix-floor/floor/nam_floor2.py",
  "helix-floor/floor/nam_floor3.py",
  "helix-floor/floor/nam_floor5.py",
  "helix-floor/floor/nam_pedal.py",
  "helix-floor/floor/stage_slots.py",
  "helix-floor/floor/stage_slots2.py",
  "helix-floor/floor/stage_model.py",
  "helix-floor/floor/stage_kernel.py",
  "helix-floor/floor/stage_main.py",
  "helix-floor/floor/stage_dsp_opt.py",
  "helix-floor/floor/dsp_opt_port.py",
  "helix-floor/floor/dsp_opt_floor.json",
  "helix-floor/floor/stage_splash.py",
  "helix-floor/floor/build_floor.py",
  "helix-floor/floor/build_staged.py",
  "helix-floor/floor/build_test2b.py",
  "helix-floor/floor/build_test2c.py",
  "helix-floor/floor/m4/floor_dsp_meter.bin",
  "helix-floor/floor/m4/floor_dsp_meter.json",
  "helix-floor/floor/m4/floor_mirror.bin",
  "helix-floor/floor/m4/floor_mirror.json",
  "helix-floor/floor/m4/focus_emmc.bin",
  "helix-floor/floor/m4/unbound_info.bin",
  "helix-floor/floor/m4/unbound_info.json",
  "tools/hxf.py",
  "tools/l6ia.py",
  "tools/l6ia_verify.py",
  "tools/patch_amp.py",
  "tools/kit_patch_amp.py",
  "tools/sharc/entry4_blob.py",
  "tools/sharc/nam_lite.py",
  "tools/sharc/nam_multi.py",
  "tools/sharc/nam_multi_kernel.asm",
  "tools/sharc/nam_pack.py",
  "tools/sharc/sasm.py",
  "tools/sharc/ssim.py",
];

var DRIVER = [
  "import contextlib, hashlib, io, os, runpy, sys",
  "os.chdir('/repo')",
  "sys.modules['capstone'] = None          # (listing only; not in Pyodide)",
  "def setenv(pairs):",
  "    for k in [k for k in os.environ if k.startswith('NAM_')]:",
  "        del os.environ[k]",
  "    os.environ.update(pairs)",
  "    # the stages' modules read NAM_* when first imported: forget them, so each build sees its own toggles",
  "    for n, m in list(sys.modules.items()):",
  "        if str(getattr(m, '__file__', '') or '').startswith('/repo/'):",
  "            del sys.modules[n]",
  "def run(argv):",
  "    out = io.StringIO()",
  "    sys.argv = list(argv)",
  "    try:",
  "        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):",
  "            runpy.run_path(argv[0], run_name='__main__')",
  "    except SystemExit as e:",
  "        if e.code not in (None, 0):",
  "            raise RuntimeError(out.getvalue() + str(e.code))",
  "    return out.getvalue()",
  "def md5(path):",
  "    return hashlib.md5(open(path, 'rb').read()).hexdigest()",
].join("\n");

var py = null;

function post(m, t) { self.postMessage(m, t || []); }

async function put(rel) {
  var r = await fetch("../" + rel);
  if (!r.ok) throw new Error("Could not load " + rel + " (" + r.status + ")");
  var data = new Uint8Array(await r.arrayBuffer());
  py.FS.mkdirTree("/repo/" + rel.split("/").slice(0, -1).join("/"));
  py.FS.writeFile("/repo/" + rel, data);
}

async function boot() {
  importScripts(PYODIDE + "pyodide.js");
  var p = await loadPyodide({ indexURL: PYODIDE });
  await p.loadPackage(["numpy", "pillow"]);
  py = p;
  try {
    for (var i = 0; i < SOURCES.length; i++) await put(SOURCES[i]);
    await put(SPLASH);
  } catch (e) { py = null; throw e; }
  py.runPython(DRIVER);
}

function mixOf(o) { return (o.splash ? "S" : "") + (o.pedal ? "P" : "") + (o.meter ? "M" : "") + (o.names ? "N" : ""); }

async function build(stock, options) {
  var mix = mixOf(options), total = 8 + (options.splash ? 1 : 0), n = 0;
  function step(text) { post({ type: "progress", step: ++n, of: total, text: text }); }
  step("Loading Python and the build tools (first time: about a minute)");
  if (!py) await boot();
  var run = py.globals.get("run"), md5 = py.globals.get("md5");
  var env = Object.assign({}, BASE_ENV);
  Object.keys(TOGGLE_ENV).forEach(function (k) { if (options[k]) Object.assign(env, TOGGLE_ENV[k]); });
  py.globals.get("setenv")(py.toPy(new Map(Object.entries(env))));
  py.FS.mkdirTree("/work");
  py.FS.writeFile("/work/stock.hxf", new Uint8Array(stock));
  if (options.names) {
    await put(NAMES_CSV);
    py.FS.writeFile("/work/names.csv", py.FS.readFile("/repo/" + NAMES_CSV));
  }
  var got = md5("/work/stock.hxf");
  if (got !== STOCK_MD5) {
    throw new Error("This is not Line 6's Helix Floor 3.80.0 file (" + got + "). You need " +
      "Helix_Floor_v3.80.0_0x7d01f5efb.hxf, unchanged.");
  }
  var F = "helix-floor/floor/", cur = "/work/s0.l6ia", k = 0;
  function stage(text, argv) {                       // argv(in, out)
    step(text);
    var next = "/work/s" + (++k) + ".l6ia";
    post({ type: "log", text: run(py.toPy(argv(cur, next))) });
    try { py.FS.unlink(cur); } catch (e) { /* (memory) */ }
    cur = next;
  }
  step("Unpacking your stock file");
  run(py.toPy(["tools/hxf.py", "unpack", "/work/stock.hxf", cur]));
  stage("Making room in the DSP memory", function (a, b) { return [F + "stage_slots2.py", a, b]; });
  stage("Adding the NAM model", function (a, b) { return [F + "stage_model.py", a, b]; });
  stage("Assembling the NAM kernel", function (a, b) { return [F + "stage_kernel.py", a, b]; });
  stage("Patching the main program", function (a, b) { return [F + "stage_main.py", a, b]; });
  var v = run(py.toPy(["tools/l6ia_verify.py", cur]));
  if (v.indexOf("ALL OK") < 0) throw new Error("The firmware check failed:\n" + v);
  stage("Adding the faster DSP code", function (a, b) { return [F + "stage_dsp_opt.py", a, b, F + "dsp_opt_floor.json"]; });
  if (options.splash) stage("Adding the boot screen", function (a, b) { return [F + "stage_splash.py", a, b, SPLASH]; });
  step("Packing the firmware file (checks every partition's size)");
  post({ type: "log", text: run(py.toPy([F + "floor_hxf.py", "pack", cur, "/work/out.hxf", "--donor", "/work/stock.hxf"])) });
  var out = md5("/work/out.hxf");
  var bytes = py.FS.readFile("/work/out.hxf");
  ["/work/out.hxf", cur, "/work/stock.hxf"].forEach(function (p) { try { py.FS.unlink(p); } catch (e) { } });
  var buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  var ref = REFERENCE[mix];
  post({ type: "done", file: "Helix_Floor_v3.80.0_UNBOUND" + (mix ? "_" + mix : "") + ".hxf", bytes: buf, md5: out, mix: mix,
         reference: !ref ? "none" : ref === out ? "match" : "differs", tested: TESTED[mix] === out }, [buf]);
}

self.onmessage = function (ev) {
  build(ev.data.stock, ev.data.options).catch(function (err) { post({ type: "error", text: String(err && err.message || err) }); });
};
