"""
Configuration & Disability Profile Engine
RUXAILAB GSoC 2026 Prototype

This module loads disability profiles, validates them against a JSON schema,
and generates a profile-aware accessibility test matrix.
"""

import json
import os
from typing import Optional


# ── Schema validation (uses jsonschema if available, else skips gracefully) ──

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_profile(profile: dict, schema: dict) -> tuple[bool, list[str]]:
    """
    Validate a disability profile against the JSON schema.
    Returns (is_valid, list_of_errors).
    """
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errors = [e.message for e in validator.iter_errors(profile)]
        return (len(errors) == 0, errors)
    except ImportError:
        # jsonschema not installed — skip validation, warn user
        return (True, ["jsonschema not installed, validation skipped"])


# ── WCAG catalogue loader ─────────────────────────────────────────────────────

class WCAGCatalogue:
    """
    Loads the WCAG criteria catalogue and provides lookups by criterion ID.
    Used to enrich test matrix entries with official criterion names.
    """

    def __init__(self, catalogue_path: str):
        raw = _load_json(catalogue_path)
        self._index: dict[str, dict] = {}
        for principle in raw.get("principles", []):
            for guideline in principle.get("guidelines", []):
                for criterion in guideline.get("criteria", []):
                    self._index[criterion["id"]] = criterion
        print(f"[OK] WCAG catalogue loaded: {len(self._index)} criteria")

    def get(self, criterion_id: str) -> Optional[dict]:
        return self._index.get(criterion_id)

    def get_name(self, criterion_id: str) -> str:
        c = self.get(criterion_id)
        return c["name"] if c else "Unknown"


# ── Profile loader ────────────────────────────────────────────────────────────

class ProfileLoader:
    """
    Loads one or more disability profiles from the config/profiles directory.
    """

    def __init__(self, profiles_dir: str, schema_path: str):
        self.profiles_dir = profiles_dir
        self.schema = _load_json(schema_path)

    def load(self, profile_id: str) -> Optional[dict]:
        """Load and validate a single profile by its ID."""
        path = os.path.join(self.profiles_dir, f"{profile_id}.json")

        if not os.path.exists(path):
            print(f"[ERROR] Profile not found: {profile_id}")
            return None

        profile = _load_json(path)
        is_valid, errors = validate_profile(profile, self.schema)

        if not is_valid:
            print(f"[ERROR] Profile '{profile_id}' failed validation:")
            for e in errors:
                print(f"  - {e}")
            return None

        print(f"[OK] Profile loaded and validated: {profile_id}")
        return profile

    def load_multiple(self, profile_ids: list[str]) -> list[dict]:
        """Load multiple profiles, skipping any that fail."""
        profiles = []
        for pid in profile_ids:
            p = self.load(pid)
            if p:
                profiles.append(p)
        return profiles


# ── Test matrix generator ─────────────────────────────────────────────────────

class TestMatrixGenerator:
    """
    Given one or more disability profiles, generates a structured
    profile-aware accessibility test matrix.
    """

    def generate(self, profiles: list[dict], conformance_level: str = "AA", catalogue: "WCAGCatalogue" = None) -> dict:
        """
        Generate a test matrix from a list of profiles.

        Args:
            profiles: List of loaded disability profile dicts
            conformance_level: Target WCAG conformance level (A, AA, AAA)

        Returns:
            A structured test matrix dict
        """
        level_order = {"A": 1, "AA": 2, "AAA": 3}
        target_rank = level_order.get(conformance_level, 2)
        self.catalogue = catalogue

        # Collect and deduplicate criteria across all profiles
        criteria_map: dict[str, dict] = {}

        for profile in profiles:
            for criterion in profile.get("wcag_criteria", []):
                cid = criterion["criterion_id"]
                crit_rank = level_order.get(criterion["level"], 1)

                # Only include criteria at or below the target conformance level
                if crit_rank > target_rank:
                    continue

                if cid not in criteria_map:
                    official_name = catalogue.get_name(cid) if catalogue else ""
                    criteria_map[cid] = {
                        "criterion_id": cid,
                        "name": official_name,
                        "level": criterion["level"],
                        "test_type": criterion["test_type"],
                        "priority": criterion["priority"],
                        "rationale": criterion.get("rationale", ""),
                        "applicable_profiles": [profile["profile_id"]]
                    }
                else:
                    # Criterion already added by another profile — merge
                    existing = criteria_map[cid]

                    # Escalate priority if higher
                    priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                    if priority_order.get(criterion["priority"], 0) > priority_order.get(existing["priority"], 0):
                        existing["priority"] = criterion["priority"]

                    # Add this profile to applicable list
                    if profile["profile_id"] not in existing["applicable_profiles"]:
                        existing["applicable_profiles"].append(profile["profile_id"])

                    # Escalate test type: both > manual > automated
                    if existing["test_type"] != "both":
                        if criterion["test_type"] == "both":
                            existing["test_type"] = "both"
                        elif criterion["test_type"] != existing["test_type"]:
                            existing["test_type"] = "both"

        # Sort by priority then criterion ID
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        sorted_criteria = sorted(
            criteria_map.values(),
            key=lambda c: (-priority_order.get(c["priority"], 0), c["criterion_id"])
        )

        # Build summary counts
        summary = {
            "total_criteria": len(sorted_criteria),
            "by_priority": {
                "critical": sum(1 for c in sorted_criteria if c["priority"] == "critical"),
                "high":     sum(1 for c in sorted_criteria if c["priority"] == "high"),
                "medium":   sum(1 for c in sorted_criteria if c["priority"] == "medium"),
                "low":      sum(1 for c in sorted_criteria if c["priority"] == "low"),
            },
            "by_test_type": {
                "manual":    sum(1 for c in sorted_criteria if c["test_type"] == "manual"),
                "automated": sum(1 for c in sorted_criteria if c["test_type"] == "automated"),
                "both":      sum(1 for c in sorted_criteria if c["test_type"] == "both"),
            }
        }

        # Collect all assistive technologies across profiles
        all_at = []
        for profile in profiles:
            for at in profile.get("assistive_technologies", []):
                if at not in all_at:
                    all_at.append(at)

        return {
            "evaluation_config": {
                "profiles_used": [p["profile_id"] for p in profiles],
                "conformance_target": conformance_level,
                "assistive_technologies": all_at,
            },
            "summary": summary,
            "test_matrix": sorted_criteria
        }


# ── Pretty printer ────────────────────────────────────────────────────────────

def print_matrix(matrix: dict) -> None:
    config = matrix["evaluation_config"]
    summary = matrix["summary"]

    print("\n" + "="*60)
    print("  ACCESSIBILITY EVALUATION TEST MATRIX")
    print("="*60)
    print(f"  Profiles : {', '.join(config['profiles_used'])}")
    print(f"  Target   : WCAG {config['conformance_target']}")
    print(f"  ATs      : {', '.join(config['assistive_technologies'])}")
    print("-"*60)
    print(f"  Total criteria : {summary['total_criteria']}")
    print(f"  By priority    : critical={summary['by_priority']['critical']}  "
          f"high={summary['by_priority']['high']}  "
          f"medium={summary['by_priority']['medium']}  "
          f"low={summary['by_priority']['low']}")
    print(f"  By test type   : manual={summary['by_test_type']['manual']}  "
          f"automated={summary['by_test_type']['automated']}  "
          f"both={summary['by_test_type']['both']}")
    print("="*60)

    for i, criterion in enumerate(matrix["test_matrix"], 1):
        name_str = f" — {criterion['name']}" if criterion.get("name") else ""
        print(f"\n  [{i}] WCAG {criterion['criterion_id']}{name_str}")
        print(f"      Level {criterion['level']}  |  "
              f"Priority: {criterion['priority'].upper()}  |  "
              f"Test: {criterion['test_type']}")
        print(f"      Profiles : {', '.join(criterion['applicable_profiles'])}")
        if criterion["rationale"]:
            # Wrap rationale at 55 chars
            words = criterion["rationale"].split()
            line, lines = [], []
            for word in words:
                if sum(len(w) for w in line) + len(line) + len(word) > 55:
                    lines.append(" ".join(line))
                    line = [word]
                else:
                    line.append(word)
            if line:
                lines.append(" ".join(line))
            print(f"      Rationale: {lines[0]}")
            for extra in lines[1:]:
                print(f"                 {extra}")

    print("\n" + "="*60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    profiles_dir  = os.path.join(base, "../config/profiles")
    schema_path   = os.path.join(base, "../config/schemas/disability_profile_schema.json")
    catalogue_path = os.path.join(base, "../config/wcag/wcag_22_criteria.json")

    loader    = ProfileLoader(profiles_dir, schema_path)
    generator = TestMatrixGenerator()
    catalogue = WCAGCatalogue(catalogue_path)

    # ── Example 1: Single hearing profile ────────────────────────────────────
    print("\n>>> Example 1: Hearing profile only (WCAG AA)")
    profiles = loader.load_multiple(["hearing"])
    matrix = generator.generate(profiles, conformance_level="AA", catalogue=catalogue)
    print_matrix(matrix)

    out_path = os.path.join(base, "../output_hearing.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)
    print(f"[Saved] {out_path}")

    # ── Example 2: Multi-profile (hearing + visual) ───────────────────────────
    print("\n>>> Example 2: Hearing + Visual profiles combined (WCAG AA)")
    profiles = loader.load_multiple(["hearing", "visual"])
    matrix = generator.generate(profiles, conformance_level="AA", catalogue=catalogue)
    print_matrix(matrix)

    out_path = os.path.join(base, "../output_hearing_visual.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)
    print(f"[Saved] {out_path}")
