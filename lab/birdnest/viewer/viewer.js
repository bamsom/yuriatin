// birdnest episode viewer — standalone, no build step.
// Data is z-up (meters, ground at z=0); three.js is y-up, so everything lives
// in a `world` group rotated -90deg about X: data (x,y,z) -> display (x,z,-y).

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ---------------------------------------------------------------- scene ----
const BG = 0x0b0e14;
const container = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(BG);
scene.fog = new THREE.Fog(BG, 2.5, 9);

const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.01, 100);
camera.position.set(0.9, 0.6, 0.9);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 0.15, 0);

// ground: faint disc + grid
const ground = new THREE.Mesh(
  new THREE.CircleGeometry(2.2, 64),
  new THREE.MeshBasicMaterial({ color: 0x10141c })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.001;
scene.add(ground);
const grid = new THREE.GridHelper(4, 40, 0x2a3448, 0x161c28);
grid.material.transparent = true;
grid.material.opacity = 0.55;
scene.add(grid);

// z-up data lives here
const world = new THREE.Group();
world.rotation.x = -Math.PI / 2;
scene.add(world);
const frameGroup = new THREE.Group();   // members of the current step
const weldGroup = new THREE.Group();    // accumulated weld points
world.add(frameGroup, weldGroup);

// ------------------------------------------------------------- coloring ----
const C_COMP = new THREE.Color(0x4f8fe6);   // compression
const C_ZERO = new THREE.Color(0xe1e4eb);   // ~zero, pale
const C_TENS = new THREE.Color(0xff5a50);   // tension
const C_PLAIN = new THREE.Color(0xaeb9c9);

// t in [-1, 1] -> diverging color
function divergingColor(t) {
  const c = C_ZERO.clone();
  if (t < 0) c.lerp(C_COMP, Math.min(1, -t));
  else c.lerp(C_TENS, Math.min(1, t));
  return c;
}

// ---------------------------------------------------------------- state ----
let episode = null;
let stepIdx = 0;
let playing = false;
let playTimer = null;
let stressMode = true;
let maxAbsStress = 1;

const $ = id => document.getElementById(id);
const slider = $('step-slider');

// --------------------------------------------------------------- meshes ----
const disposables = [];
function clearGroup(g) {
  while (g.children.length) {
    const c = g.children.pop();
    if (c.geometry) c.geometry.dispose();
    if (c.material) c.material.dispose();
  }
}

function cylinderBetween(p0, p1, radius, material) {
  const a = new THREE.Vector3(...p0), b = new THREE.Vector3(...p1);
  const dir = new THREE.Vector3().subVectors(b, a);
  const len = dir.length();
  if (len < 1e-9) return null;
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, len, 10, 1), material);
  mesh.position.copy(a).addScaledVector(dir, 0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
  return mesh;
}

function buildStep(i) {
  clearGroup(frameGroup);
  clearGroup(weldGroup);
  const step = episode.steps[i];
  const placedStick = step.stick ? episode.seed_sticks.length + (i - 1) : -1;

  for (const m of step.members) {
    const s = m.axial_stress / maxAbsStress;
    const t = Math.sign(s) * Math.sqrt(Math.abs(s));   // sqrt scale for spread
    const color = stressMode ? divergingColor(t) : C_PLAIN.clone();
    const isNew = m.stick === placedStick;
    if (isNew) color.lerp(new THREE.Color(0xffffff), 0.25);
    const mat = new THREE.MeshBasicMaterial({ color });
    const radius = 0.0045 * (isNew ? 1.35 : 1.0);
    const mesh = cylinderBetween(m.p0, m.p1, radius, mat);
    if (mesh) frameGroup.add(mesh);
    if (isNew) {   // soft halo around the just-placed stick
      const halo = cylinderBetween(m.p0, m.p1, radius * 2.6, new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: 0.10,
        blending: THREE.AdditiveBlending, depthWrite: false,
      }));
      if (halo) frameGroup.add(halo);
    }
  }

  // welds accumulated up to this step: small luminous nodes
  const weldMat = new THREE.MeshBasicMaterial({
    color: 0x9fd3ff, transparent: true, opacity: 0.85,
  });
  const weldGeo = new THREE.SphereGeometry(0.0065, 10, 8);
  for (let k = 0; k <= i; k++) {
    for (const p of episode.steps[k].weld_points) {
      const dot = new THREE.Mesh(weldGeo, weldMat);
      dot.position.set(...p);
      weldGroup.add(dot);
    }
  }
}

// ------------------------------------------------------------------ HUD ----
function fmt(x, digits = 3) {
  if (x >= 1e8) return 'inf';
  if (x <= -1e8) return '-inf';
  return x.toFixed(digits);
}

function updateHUD() {
  const step = episode.steps[stepIdx];
  const meta = episode.meta;
  $('meta-line').textContent =
    `${meta.improviser} · seed ${meta.seed}` +
    (meta.stub_settled ? ' · stub-settled' : '') +
    ` · ${episode.seed_sticks.length} seed sticks`;
  // sticks placed so far / total budget (seed + requested growth steps)
  const nSeed = episode.seed_sticks.length;
  const stepsReq = Number.isFinite(meta.steps_requested)
    ? meta.steps_requested : episode.steps.length - 1;
  $('m-sticks').textContent = `${nSeed + stepIdx}/${nSeed + stepsReq}`;
  $('m-sticks').className = 'v';
  for (const k of ['topple', 'stress', 'buckling', 'deflection']) {
    const el = $('m-' + k);
    const v = step.margins[k];
    el.textContent = k === 'topple' ? fmt(v, 4) + ' m' : fmt(v);
    el.className = 'v ' + (v > 0 ? 'ok' : 'bad');
  }
  const sc = $('m-score');
  sc.textContent = fmt(step.score);
  sc.className = 'v ' + (step.score > 0 ? 'ok' : 'bad');

  const banner = $('failbanner');
  if (!step.alive) {
    let worst = 'topple', wv = Infinity;
    for (const [k, v] of Object.entries(step.margins)) if (v < wv) { wv = v; worst = k; }
    banner.textContent = `✕ STEP FAILED — ${worst} margin ${fmt(wv)}`;
    banner.style.display = 'block';
  } else {
    banner.style.display = 'none';
  }

  const placed = step.stick
    ? ` · +stick, ${step.weld_points.length} weld${step.weld_points.length === 1 ? '' : 's'}`
    : ' · seed';
  $('step-label').textContent = `step ${stepIdx}/${episode.steps.length - 1}${placed}`;
  $('legend-scale').textContent = `±${(maxAbsStress / 1e3).toFixed(1)} kPa (√)`;
}

// ------------------------------------------------------------- playback ----
function setStep(i) {
  if (!episode) return;
  stepIdx = Math.max(0, Math.min(i, episode.steps.length - 1));
  slider.value = stepIdx;
  buildStep(stepIdx);
  updateHUD();
}

function setPlaying(on) {
  playing = on && !!episode;
  $('btn-play').innerHTML = playing ? '&#10074;&#10074;' : '&#9654;';
  clearInterval(playTimer);
  if (playing) {
    playTimer = setInterval(() => {
      if (stepIdx >= episode.steps.length - 1) { setPlaying(false); return; }
      setStep(stepIdx + 1);
    }, 550);
  }
}

// -------------------------------------------------------------- loading ----
function fitCamera() {
  const box = new THREE.Box3();
  for (const step of episode.steps)
    for (const m of step.members)
      for (const p of [m.p0, m.p1])
        box.expandByPoint(new THREE.Vector3(p[0], p[2], -p[1]));  // z-up -> y-up
  const center = box.getCenter(new THREE.Vector3());
  const diag = Math.max(box.getSize(new THREE.Vector3()).length(), 0.4);
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(
    new THREE.Vector3(1, 0.62, 1).normalize(), diag * 1.7);
}

function loadEpisode(json, name) {
  if (json.schema !== 'birdnest-episode/1')
    throw new Error(`not a birdnest episode (schema: ${json.schema})`);
  episode = json;
  maxAbsStress = 1e-9;
  for (const step of episode.steps)
    for (const m of step.members)
      maxAbsStress = Math.max(maxAbsStress, Math.abs(m.axial_stress));
  slider.max = episode.steps.length - 1;
  $('file-name').textContent = name;
  setPlaying(false);
  fitCamera();
  setStep(0);
}

$('file-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  file.text().then(t => loadEpisode(JSON.parse(t), file.name))
    .catch(err => { $('file-name').textContent = 'load failed: ' + err.message; });
});

// bundled 3-step demo — loaded only when NO training runs are served (see
// initTraining below); it stays available any time via the file picker
function loadDemo() {
  fetch('demo_episode.json')
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(j => loadEpisode(j, 'demo_episode.json'))
    .catch(() => { $('file-name').textContent = 'no demo found — pick a JSON'; });
}

// ------------------------------------------------------------- controls ----
slider.addEventListener('input', () => { setPlaying(false); setStep(+slider.value); });
$('btn-play').addEventListener('click', () => {
  if (!playing && episode && stepIdx >= episode.steps.length - 1) setStep(0);
  setPlaying(!playing);
});
$('btn-prev').addEventListener('click', () => { setPlaying(false); setStep(stepIdx - 1); });
$('btn-next').addEventListener('click', () => { setPlaying(false); setStep(stepIdx + 1); });
$('btn-color').addEventListener('click', () => {
  stressMode = !stressMode;
  $('btn-color').textContent = stressMode ? 'stress' : 'plain';
  if (episode) buildStep(stepIdx);
});
addEventListener('keydown', e => {
  if (e.code === 'Space') { e.preventDefault(); $('btn-play').click(); }
  if (e.code === 'ArrowLeft') $('btn-prev').click();
  if (e.code === 'ArrowRight') $('btn-next').click();
});

// ----------------------------------------------------- training browser ----
// Appears only when the server root exposes runs/train-*/ (serve from
// lab/birdnest: python3 -m http.server 8765, then open /viewer/viewer.html).
// Everything is plain static fetches: run.json lists the checkpointed
// generations; each gen%04d/manifest.json carries the full archive (for
// shading) plus the showcase cells whose episodes exist as ordinary
// episode JSONs — clicking one replays it in the normal viewer.
let run = null;
let activeCellKey = null;
let runsBase = null;        // '../runs/' or 'runs/' — whichever listing worked
let autoOpenPending = false;

async function fetchListing(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(String(r.status));
  return new DOMParser().parseFromString(await r.text(), 'text/html');
}

function listingHrefs(doc) {
  return [...doc.querySelectorAll('a')]
    .map(a => decodeURIComponent(a.getAttribute('href') || ''));
}

async function listRuns() {
  // parse python -m http.server's directory listing for train-*/ entries;
  // try both prefixes so the panel works from either serving root
  for (const prefix of ['../runs/', 'runs/']) {
    try {
      const names = listingHrefs(await fetchListing(prefix))
        .filter(h => h.startsWith('train-') && h.endsWith('/'))
        .map(h => h.slice(0, -1))
        .sort();
      if (names.length) { runsBase = prefix; return names; }
    } catch { /* try the next prefix */ }
  }
  return [];
}

const genDir = g => `gen${String(g).padStart(4, '0')}`;

async function listSeedVariants(name) {
  // sibling folders gen%04d-seed<k>/ are birdnest.showcase re-rolls of the
  // same elites on a different seed accident
  const variants = {};
  try {
    for (const h of listingHrefs(await fetchListing(`${runsBase}${name}/`))) {
      const m = h.match(/^gen(\d{4})-seed(\d+)\/$/);
      if (m) (variants[+m[1]] ??= []).push(+m[2]);
    }
    for (const g in variants) variants[g].sort((a, b) => a - b);
  } catch { /* no listing, no variants */ }
  return variants;
}

async function selectRun(name) {
  const info = await (await fetch(`${runsBase}${name}/run.json`)).json();
  run = { name, info, variants: await listSeedVariants(name) };
  const gens = info.generations;
  const gs = $('gen-slider');
  gs.max = gens.length - 1;
  gs.value = gens.length - 1;      // open on the latest checkpoint
  showGen(gens.length - 1);
}

async function showGen(idx, seedVariant = null) {
  const gen = run.info.generations[idx];
  const seeds = run.variants[gen] || [];
  const sel = $('seed-select');
  sel.innerHTML = '';
  sel.add(new Option('original', ''));
  for (const s of seeds) sel.add(new Option(`seed ${s}`, String(s)));
  if (seedVariant !== null && !seeds.includes(seedVariant)) seedVariant = null;
  sel.value = seedVariant === null ? '' : String(seedVariant);
  $('seed-row').style.display = seeds.length ? 'flex' : 'none';
  const dir = genDir(gen) + (seedVariant === null ? '' : `-seed${seedVariant}`);
  const manifest = await (await fetch(
    `${runsBase}${run.name}/${dir}/manifest.json`)).json();
  const showcaseDivs = drawArchive(manifest, gen, dir);
  if (autoOpenPending && manifest.cells.length) {
    autoOpenPending = false;       // skip the demo: open straight onto an elite
    const best = manifest.cells.reduce((a, b) =>
      b.steps > a.steps || (b.steps === a.steps && b.score > a.score) ? b : a);
    const div = showcaseDivs.get(`${best.i},${best.j}`);
    if (div) loadCell(dir, best, div);
  }
}

function drawArchive(manifest, gen, dir) {
  const grid = run.info.config.grid;
  const stepsMax = run.info.config.steps;
  const g = $('archive-grid');
  g.style.gridTemplateColumns = `repeat(${grid}, 1fr)`;
  g.innerHTML = '';
  const filled = new Map((manifest.archive || []).map(c => [`${c.i},${c.j}`, c]));
  const showcase = new Map(manifest.cells.map(c => [`${c.i},${c.j}`, c]));
  const showcaseDivs = new Map();
  for (let i = grid - 1; i >= 0; i--) {      // height (i) increases upward
    for (let j = 0; j < grid; j++) {
      const key = `${i},${j}`;
      const div = document.createElement('div');
      div.className = 'acell';
      const cell = filled.get(key);
      if (cell) {                            // shade by steps survived
        const a = 0.15 + 0.75 * Math.min(1, cell.steps / stepsMax);
        div.style.background = `rgba(159, 211, 255, ${a.toFixed(2)})`;
        div.title = `cell (${cell.i},${cell.j}) · ${cell.steps} steps · ` +
                    `h ${cell.height} m · span ${cell.span} m · since gen ${cell.gen_discovered}`;
      }
      const sc = showcase.get(key);
      if (sc) {
        div.classList.add('clickable');
        if (key === activeCellKey) div.classList.add('active');
        div.addEventListener('click', () => loadCell(dir, sc, div));
        showcaseDivs.set(key, div);
      }
      g.appendChild(div);
    }
  }
  $('gen-label').textContent = `gen ${gen}`;
  $('train-info').textContent =
    `coverage ${(manifest.coverage * 100).toFixed(1)}% · ` +
    `${(manifest.archive || []).length} cells filled · ` +
    `${manifest.cells.length} watchable` +
    (manifest.showcase_seed != null ? ` · showcase seed ${manifest.showcase_seed}` : '');
  return showcaseDivs;
}

async function loadCell(dir, cell, div) {
  activeCellKey = `${cell.i},${cell.j}`;
  for (const el of document.querySelectorAll('.acell.active')) el.classList.remove('active');
  div.classList.add('active');
  const name = `${run.name}/${dir}/${cell.episode}`;
  try {
    const ep = await (await fetch(`${runsBase}${name}`)).json();
    loadEpisode(ep, name);
    setPlaying(true);                        // watchable: replay immediately
  } catch (err) {
    $('file-name').textContent = 'load failed: ' + err.message;
  }
}

(async function initTraining() {
  const runs = await listRuns();
  $('training').style.display = 'block';
  if (!runs.length) {
    // visible hint instead of a silent fall-back to the 3-step demo
    for (const id of ['run-select', 'gen-row', 'seed-row', 'archive-grid', 'axes'])
      $(id).style.display = 'none';
    $('train-info').textContent = 'no training runs found — serve from ' +
      'lab/birdnest (python -m http.server) to browse them';
    loadDemo();
    return;
  }
  const sel = $('run-select');
  for (const name of runs) sel.add(new Option(name, name));
  sel.value = runs[runs.length - 1];
  sel.addEventListener('change', () => selectRun(sel.value));
  $('gen-slider').addEventListener('input', e => showGen(+e.target.value));
  $('seed-select').addEventListener('change', e => showGen(
    +$('gen-slider').value, e.target.value === '' ? null : +e.target.value));
  autoOpenPending = true;          // auto-open latest run, latest generation
  selectRun(sel.value);
})();

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
