# Contributing to Reclamation Evidence Ledger

Thank you for your interest in contributing! This project is an independent satellite watchdog monitoring Alberta orphan well reclamation from orbit. We welcome contributions that improve data accuracy, add analytical rigor, improve documentation, or streamline operations.

## Code of Conduct

All contributors and participants are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to Contribute

* **Report bugs or data discrepancies:** If you find a data discrepancy, a coordinate translation issue, or an edge case in change detection, open an issue using the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml) template.
* **Question or audit evidence:** If you want to audit or dispute an evidence packet for a specific site, use the [Evidence Query](.github/ISSUE_TEMPLATE/evidence_inquiry.yml) template.
* **Propose improvements:** New indices, better cloud masking, or workflow performance enhancements can be proposed via [Feature Requests](.github/ISSUE_TEMPLATE/feature_request.yml) or [Discussions](https://github.com/FetchDoge/reclamation-evidence-ledger/discussions).
* **Submit Pull Requests:** Code, documentation, schemas, and test contributions are welcome.

## Development Setup

Requirements:
* Python 3.12+
* Git

```bash
# Clone the repository
git clone https://github.com/FetchDoge/reclamation-evidence-ledger.git
cd reclamation-evidence-ledger

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running Tests

All tests must pass before submitting a pull request:

```bash
# Run pytest test suite
pytest tests/
```

## Schema Validation

Every evidence packet committed under `packets/` must strictly validate against `schemas/evidence-packet.schema.json`:

```bash
# Run packet validation check
python - <<'EOF'
import glob, json, sys, jsonschema
schema = json.load(open("schemas/evidence-packet.schema.json"))
files = sorted(glob.glob("packets/*.json"))
if not files:
    sys.exit("No packets found in packets/")
for f in files:
    jsonschema.validate(json.load(open(f)), schema)
print(f"Validated {len(files)} packets successfully against schema v{schema['properties']['schema_version']['const']}.")
EOF
```

## Commit Conventions (Conventional Commits)

This repository enforces semantic pull request titles and conventional commit standards. PR titles and commits should follow the format:

```text
<type>(<scope>): <short description>
```

Common types:
* `feat`: A new feature (e.g., `feat(change): add SAVI index to spectral analysis`)
* `fix`: A bug fix (e.g., `fix(tests): provide self-contained fixture for determinism test`)
* `docs`: Documentation updates (e.g., `docs: add validation memo and triage register`)
* `test`: Adding or updating test suites
* `chore`: Maintenance, dependencies, or tooling updates
* `ci`: GitHub Actions and automation updates

## Pull Request Guidelines

1. **Branch off `main`**: Name branches descriptively (e.g., `feat/cloud-mask-buffer` or `fix/lsd-geocoding`).
2. **Include Tests**: Add unit tests in `tests/` covering new logic or regressions.
3. **Fill the PR Template**: Ensure every section in the pull request template is completed.
4. **Honest refusal over guessing**: Adhere to the core project guarantee—if there is insufficient evidence (e.g., clouds, seasonal mismatch), the pipeline must refuse to assess rather than fabricate a result.
