"""Structure-level behavior on the hand-built cases, including the expected
ordering: tripod scores above cantilever, which scores above the toppler."""

import numpy as np

from birdnest import cases
from birdnest.fem import Material, viability

MAT = Material()


def test_vertical_stick_is_stable():
    v = viability(cases.vertical_stick())
    assert v.ok
    assert all(m > 0 for m in v.margins.values())
    # margin is exactly the contact-patch radius: balanced, barely stable
    assert np.isclose(v.margins["topple"], cases.R_STICK, atol=1e-9)


def test_leaning_stick_topples():
    v = viability(cases.leaning_stick())
    assert not v.ok
    # COM overhangs the single contact by half the horizontal run
    assert np.isclose(v.margins["topple"], cases.R_STICK - 0.075, atol=1e-6)
    assert v.score < 0


def test_tripod_stable_with_symmetric_stresses():
    v = viability(cases.tripod())
    assert v.ok
    assert len(v.mesh.members) == 3
    assert np.all(v.fem.axial < 0)  # every leg in compression
    spread = np.ptp(v.fem.sigma) / np.max(v.fem.sigma)
    assert spread < 1e-6  # symmetric legs, symmetric stresses
    # feet triangle: circumradius 0.12 -> inradius 0.06; plus contact patch
    assert np.isclose(v.margins["topple"], 0.06 + cases.R_STICK, rtol=1e-6)


def test_cantilever_high_root_bending_but_viable():
    v_tri = viability(cases.tripod())
    v_arm = viability(cases.tripod_cantilever())
    assert v_arm.ok
    # the arm member (stick 3) carries the structure's worst bending
    arm_members = [i for i, m in enumerate(v_arm.mesh.members) if m.stick == 3]
    assert len(arm_members) == 1
    arm = arm_members[0]
    assert arm == int(np.argmax(v_arm.fem.moment))
    # root moment is fixed by statics: w L^2 / 2
    w = MAT.density * 9.81 * np.pi * cases.R_STICK**2
    assert np.isclose(v_arm.fem.moment[arm], w * 0.25**2 / 2, rtol=1e-6)
    # and it dwarfs anything in the plain tripod
    assert v_arm.fem.moment[arm] > 5 * np.max(v_tri.fem.moment)
    # the overhung COM eats toppling margin relative to the plain tripod
    assert v_arm.margins["topple"] < v_tri.margins["topple"]


def test_slender_strut_flags_buckling_stocky_does_not():
    s, loads = cases.slender_strut()
    v = viability(s, point_loads=loads)
    assert not v.ok
    assert v.margins["buckling"] < 0
    assert v.margins["stress"] > 0  # buckling, not strength, is the failure
    assert v.margins["topple"] > 0

    s2, loads2 = cases.stocky_strut()
    v2 = viability(s2, point_loads=loads2)
    assert v2.ok
    assert v2.margins["buckling"] > 0


def test_expected_score_ordering():
    s_tripod = viability(cases.tripod()).score
    s_cant = viability(cases.tripod_cantilever()).score
    s_lean = viability(cases.leaning_stick()).score
    assert s_tripod > s_cant > s_lean
    assert s_lean < 0 < s_cant


def test_no_ground_contact_is_fatal():
    from birdnest.fem import Structure

    s = Structure()
    s.add_stick((0, 0, 1.0), (0, 0, 1.3))  # hovering
    v = viability(s)
    assert not v.ok
    assert v.reason == "no ground contact"
    assert v.score == -s.params.score_cap
