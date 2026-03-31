# Configuration & Disability Profile Engine — Prototype
### RUXAILAB GSoC 2026 | Shreya Rajesh Sanap

This is a working prototype demonstrating the core concept of the
Configuration & Disability Profile Engine project.

---

## What it does

Given one or more disability profiles, this engine:
1. Loads and validates each profile against a JSON schema
2. Filters WCAG success criteria by the target conformance level (A / AA / AAA)
3. Merges criteria across multiple profiles, escalating priority where profiles overlap
4. Outputs a structured, profile-aware accessibility test matrix

---

## Project structure

```
disability_profile_engine/
├── config/
│   ├── schemas/
│   │   └── disability_profile_schema.json   # JSON Schema for profile validation
│   └── profiles/
│       ├── hearing.json                     # Hearing impairment profile
│       ├── visual.json                      # Visual impairment profile
│       └── motor.json                       # Motor impairment profile
└── engine/
    └── engine.py                            # Core loader, validator, matrix generator
```

---

## How to run

```bash
pip install jsonschema
python engine/engine.py
```

This runs two examples:
- Single profile: hearing only at WCAG AA
- Multi-profile: hearing + visual combined at WCAG AA

---

## Example output (hearing profile, WCAG AA)

```
Profiles : hearing
Target   : WCAG AA
ATs      : closed_captions, transcripts, visual_alerts ...

Total criteria : 6
By priority    : critical=3  high=2  medium=0  low=1
By test type   : manual=4  automated=1  both=1

[1] WCAG 1.2.2  Level A  |  Priority: CRITICAL  |  Test: manual
    Rationale: Captions for prerecorded video are the primary way
               deaf users access spoken content...
```

---

## Design decisions

**Why JSON Schema for profiles?**
Profiles need to be human-readable, version-controlled, and extensible.
JSON Schema provides validation without requiring a database, and new
profiles can be added by simply creating a new `.json` file.

**Why is hearing marked mostly manual?**
Caption quality — accuracy, synchronization, speaker identification —
cannot be reliably automated. Most 1.2.x criteria require a human
evaluator. This is a deliberate design decision informed by lived
experience with captioning systems.

**Why does priority escalate across profiles?**
When two profiles both reference the same criterion but assign it
different priorities, the higher priority wins. This ensures multi-profile
matrices don't underweight criteria that are critical for any one group.
