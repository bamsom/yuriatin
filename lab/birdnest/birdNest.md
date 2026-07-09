# birdNest.md — improvisational structure growth by RL (discussion handoff)

Status: design discussion, no code yet. This file summarizes a conversation arc
so a new session can continue it. Owner: Sung. Related projects: iSketcher2
(sketch→3D pairs, style-as-displacement), rl_style1 (procedural line-drawing
dataset with style axes), the wedge/orthographic-reconstruction discussion.

---

## 1. The idea, in its final form

Grow a 3D structure from straight rigid sticks ("twigs", "matchsticks"), one
stick at a time, by an RL policy. Purely idealized — no real-world construction,
no friction: every stick **welds rigidly where it touches** (as if 3D-printed).
The structure is therefore always a rigid space frame, and its mechanics are
classical linear structural analysis, not contact simulation.

The defining move: **improvisation over an accident**, not design.
- The episode begins with a **seed**: dump a handful of sticks with random poses,
  let them settle once under ordinary rigid-body physics (the only contact sim,
  offline, per-episode), then freeze by welding all contacts. The seed is an
  arbitrary, fragile, nobody-chose-it frame — often leaning, sometimes one stick
  from toppling ("barely stands" is controllable: fewer sticks, or select seeds
  with small toppling margin).
- The agent then grows the structure stick by stick. Each placement welds on
  contact. Reward comes from structural mechanics (below).
- Canonical shapes (hemisphere, toroid) are deliberately NOT targets. The
  question is what forms emerge; canonical forms appearing as attractors is a
  finding, not an input.

Framing: this is the **emergence pole** opposite the "wedge" — the trapezoidal
prism reconstructed from three orthographic views in an earlier discussion,
which stands for fully-determined, reasoning-recoverable structure. Wedge =
global plan, symbolic reconstruction. Nest = no plan, grown coherence.

## 2. Evolution of the idea (three versions)

1. **Frictional version (discarded).** Original framing: loose twigs, reward =
   "static mechanics stability." Assessment: a loose twig pile is statically
   indeterminate and contact-rich; friction/jamming IS the mechanism; the reward
   would secretly require a frictional contact solver (settling displacement,
   friction-cone margins). Feasible but heavy.
2. **Welded/idealized version.** Weld all contacts → space frame → direct
   stiffness method (frame FEM) solves in milliseconds. "Stability" becomes:
   toppling margin (COM over support polygon), peak member stress under
   self-weight + payload, compliance under standard load, Euler buckling factor
   for slender members in compression (the one place thin idealized sticks
   still bite). RL becomes fast, deterministic, even differentiable if wanted.
   Cost of the idealization, named honestly: we study nest FORM, not the nest
   MECHANISM (which is friction). That is the intent.
3. **Improvisational version (current).** Random dumped seeds + growth. Random
   seeds force the policy to be conditional on the structure it finds — it must
   READ the heap (support polygon, lean, stiff subassemblies) and respond.
   Generalization across held-out seeds IS the evaluation. The first-twig
   degeneracy of earlier versions disappears: the dump is the opening.

## 3. The two most recent refinements (this session's last exchange)

**2D is demoted.** Prior plan staged 2D-first for cheap reward debugging. Sung's
challenge — 2D is too trivial to generate anything unusual — is conceded for
emergence: enclosure barely exists in 2D, no torsion, no out-of-plane buckling,
and the tangent-lattice weave of real nests is impossible in-plane; a 2D agent
builds silhouettes. New role for 2D: a few days of unit tests on the frame
solver + reward (verify it ranks hand-built good continuations above bad ones),
then straight to 3D. Keep only the discipline: validate reward on hand-made
cases before training.

**Growth drive via intrinsic novelty, not hand-designed ambition.** Sung
proposed using "the usual RL exploration" instead of a growth reward, to avoid
prematurely settling into safe shapes. Important distinction:
- Exploration (entropy bonus, ε-greedy, curiosity during training) shapes the
  SEARCH, not the OBJECTIVE. With a stability-only reward, "add nothing / lay
  flat" is the GLOBAL optimum; exploration finds it faster. Exploration cannot
  substitute for a drive.
- But the legitimate version of the instinct: make novelty part of the
  objective — intrinsic motivation / quality-diversity (novelty search,
  MAP-Elites). Reward producing structures DIFFERENT from those produced
  before; stability becomes a constraint/filter, novelty the drive. Output is
  an ARCHIVE of diverse stable forms grown from accidental seeds — closer to
  improvisation than any reward-maximizing builder, and it avoids smuggling
  the hemisphere in through a height/enclosure bonus.
- Honest cost: QD needs a behavior descriptor (what makes two structures
  "different": height/span/enclosure stats or learned embeddings). Authorship
  of the drive doesn't vanish; it moves to a weaker, less form-committal place.
- The hemisphere/toroid question becomes clean: canonical forms = dense archive
  regions the novelty pressure keeps rediscovering = genuine attractors.
  Prediction on record: LOCAL canonical motifs (triangulated clusters, buttress
  fans) recur inside globally idiosyncratic forms — grammar without a blueprint.

## 4. Current technical sketch

- **Stick**: rigid capsule/segment; fixed length initially. Action = pose of
  next stick (continuous); welds at contacts.
- **Seed**: N sticks dumped in rigid-body sim → settle → weld → freeze.
  Seed difficulty controlled by N and toppling-margin selection.
- **Structure state**: welded frame = graph (sticks = members, welds = joints).
  Encoder: GNN over the joint/member graph or permutation-invariant set encoder.
- **Reward / viability**: frame FEM (direct stiffness) per placement: member
  stresses, deflection, buckling factors; plus rigid toppling margin. Structure
  "survives" if margins positive. Drive = QD novelty over a behavior descriptor;
  stability = constraint. (Alternative kept in back pocket: explicit
  ambition-vs-margin weighting as a STYLE AXIS over growth policies — two
  weightings improvising on the same seed = content/style factorization in
  statics, echoing the iSketcher2 style-displacement idea.)
- **Evaluation**: held-out seeds; growth quality + archive coverage on unseen
  accidents.
- **Reward hacking watch**: flat rafts/pancakes are stress-optimal and
  nest-unlike; with QD they are one archive cell, not the whole outcome. If
  using explicit drives instead, a cavity/payload term is what forces cup
  morphology.

## 5. Build path (post-refinement)

1. Frame-FEM reward module + unit tests on hand-built 2D/3D examples (days,
   not a project stage). Separate, testable module — same discipline as keeping
   the raw ray-cast pristine in iSketcher2.
2. Seed generator: dump → settle → weld, with difficulty knobs.
3. Scripted improviser baselines: greedy-by-margin, greedy-by-height, random.
4. QD loop (MAP-Elites or novelty search) with the GNN policy in 3D.
5. Analysis: attractor question; motif statistics; seed-conditioned behavior.

## 6. Open questions for the next session

- Behavior descriptor for QD: hand stats (height, span, enclosed volume,
  anisotropy) vs learned embedding. This choice shapes everything downstream.
- Weld model: rigid joints everywhere, or joint stiffness as a parameter?
- Stick length: fixed vs sampled vs agent-chosen (enlarges action space).
- Simulator/solver choice: any rigid-body engine for the seed settle; frame
  FEM is simple enough to hand-roll (direct stiffness, ~hundreds of members).
- Relation to rl_style1: whether growth-policy weightings should be formalized
  as style axes now or after the QD version works.
