"""QD-layer gates: policy argmax is deterministic given theta and a fixed
candidate list; archive insert keeps the better individual."""

import numpy as np
import pytest

from birdnest.fem import viability
from birdnest.cases import tripod
from birdnest.policy import (FEATURE_NAMES, N_FEATURES, LinearPolicy,
                             feature_matrix, features, pick_index)
from birdnest.train_qd import Archive, Elite, cell_of


# ------------------------------------------------------------------ policy --

def _fixed_feature_matrix():
    rng = np.random.default_rng(7)
    return rng.normal(size=(9, N_FEATURES))


def test_pick_index_deterministic_given_theta():
    F = _fixed_feature_matrix()
    theta = np.array([1.0, -0.5, 0.2, 0.7, -1.1, 0.3, 0.0])
    expected = int(np.argmax(F @ theta))
    # utilities are distinct, so the rng must not matter
    for rng_seed in (0, 1, 12345):
        assert pick_index(theta, F, np.random.default_rng(rng_seed)) == expected


def test_pick_index_theta_zero_is_random_tiebreak():
    """theta = 0 ties every candidate -> uniform random pick (random_valid
    degenerate case), still deterministic given the rng."""
    F = _fixed_feature_matrix()
    theta = np.zeros(N_FEATURES)
    picks = {pick_index(theta, F, rng)
             for rng in (np.random.default_rng(i) for i in range(200))}
    assert picks == set(range(len(F)))  # every candidate reachable
    rng_a, rng_b = np.random.default_rng(42), np.random.default_rng(42)
    assert pick_index(theta, F, rng_a) == pick_index(theta, F, rng_b)


def test_features_on_real_candidate():
    """features() runs on a real viable-candidate entry and matches the
    documented layout (7 values, bias last)."""
    structure = tripod()
    v0 = viability(structure)
    assert v0.ok
    s2 = structure.copy()
    n_welds_before = len(s2.welds)
    # lay a stick across the apex, touching it
    apex = max((s.p1 for s in structure.sticks), key=lambda p: p[2])
    idx = s2.add_stick(apex + [-0.15, 0, 0.008], apex + [0.15, 0, 0.008], 0.004)
    v = viability(s2)
    entry = (s2, idx, v, [w.point for w in s2.welds[n_welds_before:]])
    f = features(structure, entry, stick_len=0.30)
    assert f.shape == (N_FEATURES,) and np.all(np.isfinite(f))
    assert f[FEATURE_NAMES.index("bias")] == 1.0
    assert f[FEATURE_NAMES.index("n_welds")] >= 1.0
    F = feature_matrix(structure, [entry, entry], 0.30)
    assert F.shape == (2, N_FEATURES)
    # end-to-end: the callable policy returns a member of the candidate list
    pol = LinearPolicy(np.ones(N_FEATURES))
    assert pol(structure, [entry], np.random.default_rng(0)) is entry


def test_linear_policy_rejects_bad_theta():
    with pytest.raises(ValueError):
        LinearPolicy(np.zeros(3))


# ----------------------------------------------------------------- archive --

def _elite(steps, score, gen=0, ind_id=0):
    return Elite(theta=np.zeros(N_FEATURES), steps=steps, score=score,
                 height=0.3, span=0.5, gen=gen, ind_id=ind_id)


def test_archive_insert_keeps_better():
    a = Archive(grid=12)
    cell = (3, 4)
    e1 = _elite(steps=10, score=0.2, ind_id=1)
    assert a.insert(cell, e1) == "new"
    # same steps, better score -> replaced (tiebreak by final score)
    e2 = _elite(steps=10, score=0.5, ind_id=2)
    assert a.insert(cell, e2) == "improved"
    assert a.cells[cell] is e2
    # fewer steps survived loses even with a much better score
    e3 = _elite(steps=9, score=0.9, ind_id=3)
    assert a.insert(cell, e3) is None
    assert a.cells[cell] is e2
    # strictly more steps wins even with a worse score
    e4 = _elite(steps=11, score=0.1, ind_id=4)
    assert a.insert(cell, e4) == "improved"
    assert a.cells[cell] is e4
    assert a.coverage == 1 / 144


def test_cell_of_clamps_to_grid():
    L, g = 0.30, 12
    assert cell_of(0.0, 0.0, L, g) == (0, 0)
    assert cell_of(99.0, 99.0, L, g) == (g - 1, g - 1)  # past range -> edge bin
    i, j = cell_of(0.45, 0.75, L, g)  # 1.5 L height, 2.5 L span
    assert 0 < i < g - 1 and 0 < j < g - 1
