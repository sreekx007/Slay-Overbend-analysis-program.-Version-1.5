"""
config.py -- the one place every constant used across the S-Lay overbend
toolchain lives.

This module holds no logic beyond loading and validating its data. Every
actual default value lives in the companion file `slay_config.yaml`, sitting
next to this file on disk. config.py's job is to locate that file, parse it,
confirm every expected section is present, resolve the one piece of real
computation it contains (the one-sided-roller rule), and re-expose every
value as a plain module-level constant under the same name every other
module already imports (e.g. `N_VR`, `D_O_DEF`).

Editing a default means editing slay_config.yaml, not this file. A
per-case override (trying a different parameter for one study) does not
belong here either -- that goes through slay_spec.py's case-level override
mechanism, which layers a value on top of what this module supplies for one
run only and leaves the shared file untouched.

Failure policy: if the YAML file is missing, fails to parse, or is missing
an expected section, this module raises immediately and loudly, naming the
specific problem. There is no hidden fallback to built-in defaults -- the
whole point of moving these numbers into their own file is that the file
becomes the one true source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Locate and load
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _CONFIG_DIR / "slay_config.yaml"

if not _CONFIG_PATH.exists():
    raise FileNotFoundError(
        f"slay_config.yaml not found at {_CONFIG_PATH}. "
        "config.py loads every default from this file and has no built-in "
        "fallback -- create it or check the path."
    )

with open(_CONFIG_PATH, "r") as _f:
    try:
        _raw: dict[str, Any] = yaml.safe_load(_f)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"slay_config.yaml at {_CONFIG_PATH} failed to parse as YAML: {exc}"
        ) from exc

# ---------------------------------------------------------------------------
# Validate: every expected top-level section must be present
# ---------------------------------------------------------------------------

_EXPECTED_SECTIONS = (
    "reference_pipeline",
    "stinger_rollers",
    "mesh",
    "materials",
    "physical_constants",
    "section",
    "solver",
)

for _section in _EXPECTED_SECTIONS:
    if _section not in _raw:
        raise KeyError(
            f"slay_config.yaml is missing section: '{_section}'. "
            f"Expected all of: {_EXPECTED_SECTIONS}."
        )

# Section presence is not enough. Checking only sections let a missing
# reference_pipeline.E_Pa reach the assignment below and surface as a bare
# `KeyError: 'E_Pa'` from a line of arithmetic -- which reads like a fault
# in whatever imported this module, not like a malformed YAML. This
# docstring promises a failure that NAMES the problem, so the keys the
# module is about to read are checked where that promise is made.
_EXPECTED_KEYS = {
    "reference_pipeline": ("OD_pipe_m", "t_wall_m", "R_default_m", "E_Pa"),
    "physical_constants": ("rho_steel_kg_m3",),
}
for _section, _keys in _EXPECTED_KEYS.items():
    for _key in _keys:
        if _key not in _raw[_section]:
            raise KeyError(
                f"slay_config.yaml section '{_section}' is missing key "
                f"'{_key}'. Expected all of: {_keys}."
            )

_materials = _raw["materials"]
for _mat in ("j2", "ro"):
    if _mat not in _materials:
        raise KeyError(
            f"slay_config.yaml 'materials' section is missing sub-section: '{_mat}'."
        )

# ---------------------------------------------------------------------------
# Unpack: straight 1:1 copies from YAML to named constants
# ---------------------------------------------------------------------------

_ref = _raw["reference_pipeline"]
OD_PIPE_DEF: float = _ref["OD_pipe_m"]
T_WALL_DEF: float = _ref["t_wall_m"]
R_STINGER_DEF: float = _ref["R_default_m"]
# Coerced explicitly -- same bare-exponential PyYAML parsing gap noted
# below for the material tables and solver constants (E_Pa: 210.0e9 is
# exactly the pattern that silently parses as str, not float).
STEEL_E: float = float(_ref["E_Pa"])

_sr = _raw["stinger_rollers"]
ROLLER_SPACING: float = _sr["spacing_m"]
N_SR: int = _sr["n_sr"]
N_VR: int = _sr["n_vr"]
ROLLER_RADIUS_DEF: float = _sr["roller_radius_default_m"]
_one_sided_rule: dict[str, Any] = _sr["one_sided_rollers_default"]

_mesh = _raw["mesh"]
OD_MULTIPLE: float = _mesh["od_multiple"]

_j2 = _materials["j2"]
MATERIAL_J2_E: float = float(_j2["E_Pa"])
# PyYAML's YAML-1.1 float resolver does not reliably match bare
# exponential literals like '360.0e6' inside nested list items -- it
# silently falls through to str instead of raising, so every entry here
# is coerced to float explicitly rather than trusted from the parse.
MATERIAL_J2_TABLE: list[list[float]] = [
    [float(stress), float(strain)] for stress, strain in _j2["yield_plastic_strain_table"]
]

_ro = _materials["ro"]
MATERIAL_RO_E: float = float(_ro["E_Pa"])
MATERIAL_RO_SIG_YS: float = float(_ro["sig_ys_Pa"])
MATERIAL_RO_N: float = float(_ro["N_RO"])
MATERIAL_RO_ALPHA_DNV: float = float(_ro["alpha_DNV"])

_phys = _raw["physical_constants"]
RHO_STEEL: float = _phys["rho_steel_kg_m3"]
G: float = _phys["g_m_s2"]

_sec = _raw["section"]
SECTION_DEFAULT_TYPE: str = _sec["default_type"]
N_POINTS_POLAR_DEF: int = _sec["n_points_polar_default"]
N_FIBRES_DEF: int = _sec["n_fibres_default"]

_solver = _raw["solver"]
# PEN_STEP0/PEN_SHIFT coerced explicitly -- same PyYAML bare-exponential
# parsing gap as the material tables above (see note there).
PEN_STEP0: float = float(_solver["pen_step0"])
PEN_SHIFT: float = float(_solver["pen_shift"])
N_INCREMENTS_STEP0: int = int(_solver["n_increments_step0"])
N_INCREMENTS_SHIFT: int = int(_solver["n_increments_shift"])
REG_MULT_DEFAULT: float = float(_solver["reg_mult_default"])
# k_spring intentionally has no constant here: tested, rejected, removed
# 12 Aug 2026. Not reintroduced as a default with any value, including 0.
# Do not add a K_SPRING_DEFAULT without a specific, documented reason to
# revisit that finding.

# ---------------------------------------------------------------------------
# Resolve: the one-sided-roller rule (real computation, not a direct copy)
# ---------------------------------------------------------------------------


def _resolve_one_sided_rollers(rule: dict[str, Any], n_sr: int) -> frozenset[str]:
    """
    Expand the one-sided-roller rule into a concrete set of roller names.

    Rule shape (from slay_config.yaml):
        stinger: 'all' | list[str]   -- 'all' expands to SR1..SRn_sr
        vessel:  list[str]           -- explicit names, not expanded

    Every SR roller is one-sided (it can only push the pipe along the
    stinger arc, never hold it down against it) -- expressed as a rule
    rather than a fixed list so it scales automatically if n_sr changes.
    VR1 and VR2 (nearest the stinger) are also one-sided. Every other
    vessel roller (VR3 onward) is bilateral by omission -- it is simply
    not in this set.
    """
    stinger_rule = rule.get("stinger")
    if stinger_rule == "all":
        stinger_names = {f"SR{i}" for i in range(1, n_sr + 1)}
    elif isinstance(stinger_rule, list):
        stinger_names = set(stinger_rule)
    else:
        raise ValueError(
            f"slay_config.yaml one_sided_rollers_default.stinger must be "
            f"'all' or a list of names, got: {stinger_rule!r}"
        )

    vessel_names = set(rule.get("vessel", []))

    return frozenset(stinger_names | vessel_names)


ONE_SIDED_ROLLERS_DEFAULT: frozenset[str] = _resolve_one_sided_rollers(
    _one_sided_rule, N_SR
)

# ---------------------------------------------------------------------------
# Expose
# ---------------------------------------------------------------------------

__all__ = [
    "OD_PIPE_DEF",
    "T_WALL_DEF",
    "R_STINGER_DEF",
    "STEEL_E",
    "ROLLER_SPACING",
    "N_SR",
    "N_VR",
    "ROLLER_RADIUS_DEF",
    "OD_MULTIPLE",
    "MATERIAL_J2_E",
    "MATERIAL_J2_TABLE",
    "MATERIAL_RO_E",
    "MATERIAL_RO_SIG_YS",
    "MATERIAL_RO_N",
    "MATERIAL_RO_ALPHA_DNV",
    "RHO_STEEL",
    "G",
    "SECTION_DEFAULT_TYPE",
    "N_POINTS_POLAR_DEF",
    "N_FIBRES_DEF",
    "PEN_STEP0",
    "PEN_SHIFT",
    "N_INCREMENTS_STEP0",
    "N_INCREMENTS_SHIFT",
    "REG_MULT_DEFAULT",
    "ONE_SIDED_ROLLERS_DEFAULT",
]
