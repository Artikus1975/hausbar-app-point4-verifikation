# Murats Hausbar App - Phase 1 / Punkt-4-Korrektur

Dieses Verzeichnis ist der **direkt verwendbare Git-Repository-Root**. `.github/`, `site/`, `tools/`, `tests/`, `config/`, `vendor/` und diese README müssen unmittelbar auf der obersten Repository-Ebene liegen. Der Ordner darf nicht zusätzlich in `app/` oder einen Versionsordner verschachtelt werden.

## Status und Umfang

- Privater Korrekturstand: `v0.1.0-preview.3`
- Öffentliche App-Version: unverändert `v0.1.0-preview.1`
- Öffentlicher Bestand: 172 Dateien, byteidentisch zum freigegebenen Phase-1-Stand
- Freigegebener Rezeptbestand: 0
- Reale GitHub-Actions-/Pages-Verifikation: bis zum tatsächlichen Lauf ausstehend

Die Korrektur betrifft ausschließlich Repository-Root, CI-Toolchain und GitHub-Pages-Workflow. Produkt-, Asset-, Export-, Mapping-, Datenschutz- und Fachlogik bleiben unverändert. Zusätzliche Inventar-, Such-, Filter- oder Rezepttests aus Problemregisterpunkt 5 sind ausdrücklich nicht enthalten.

## Verbindlicher Repository-Root

Nach dem Entpacken des separaten Repository-ZIP müssen direkt sichtbar sein:

```text
.github/
config/
site/
tests/
tools/
vendor/
README.md
requirements-lock.txt
```

Vor jedem lokalen Lauf:

```bash
python tools/check_repository_root.py
```

Ein vorgeschalteter Ordner wie `app/` oder `v0.1.0-preview.3/` ist für den GitHub-Upload nicht zulässig.

## Gesperrte Referenzumgebung

- Runnerlabel: `ubuntu-24.04`
- CPython: `3.13.5`
- Node.js: `22.16.0`
- Python-Pakete: openpyxl 3.1.5, Pillow 12.2.0, et_xmlfile 2.0.0
- Python-Installation ausschließlich offline aus `vendor/wheels/`
- Installationsflags: `--no-index`, `--no-deps`, `--require-hashes`
- GitHub Actions ausschließlich über vollständige 40-stellige Commit-SHAs

Der vollständige Vertrag steht in `config/ci-toolchain-lock.json`.

## Lokale Workflow-Simulation

Aus dem Repository-Root:

```bash
python tools/check_repository_root.py
export HAUSBAR_CI_VENV="${TMPDIR:-/tmp}/hausbar-ci-venv"
python tools/bootstrap_clean_environment.py --venv "$HAUSBAR_CI_VENV" --replace
"$HAUSBAR_CI_VENV/bin/python" tools/check_ci_environment.py
"$HAUSBAR_CI_VENV/bin/python" tools/build.py --site site
"$HAUSBAR_CI_VENV/bin/python" -m unittest discover -s tests -v
node tests/runtime_contract.mjs
"$HAUSBAR_CI_VENV/bin/python" tools/verify_public_tree.py --site site
```

Das letzte Gate verlangt exakt 172 öffentliche Dateien und den Tree-Hash:

```text
ed6da5035e0a0943b35fd183e6ffd84771b8abd73d5a3133ecc0c806575b37c4
```

## GitHub Pages einrichten

1. Neues öffentliches GitHub-Repository anlegen oder ein geeignetes bestehendes Repository leeren.
2. **Nur den Inhalt** des separaten `v0.1.0-preview.3_repository.zip` in den Repository-Root hochladen.
3. Standardbranch `main` verwenden.
4. Unter `Settings -> Pages -> Build and deployment -> Source` die Quelle `GitHub Actions` auswählen.
5. Den Workflow `Validate and deploy GitHub Pages` über `Actions` manuell starten oder auf `main` pushen.
6. Erst nach erfolgreichem Build- und Deploy-Job die veröffentlichte URL und die Workflow-Logs prüfen.

Ein realer GitHub-Lauf ist die letzte noch offene Prüfung. Ohne diesen Lauf darf Problemregisterpunkt 4 nicht als vollständig gelöst bezeichnet werden.

## Öffentliche und private Grenze

`site/` ist der einzige veröffentlichte Inhalt. Masterdatei, interne Texte, Quellen, Prüfnotizen, Originalbildinformationen, Auditdaten, private Profile und Zugangsschlüssel dürfen nicht in das Repository kopiert werden. Die Produktdaten folgen der `DENY_BY_DEFAULT`-Allowlist.

## Private v7.66-Reproduktion

Die privaten autoritativen Quellen sind nicht im Repository enthalten. Der bereits freigegebene Punkt-3-Orchestrator bleibt unverändert nutzbar:

```bash
"$HAUSBAR_CI_VENV/bin/python" tools/reproduce_phase1_export.py   --source-dir /privat/v7.66_quellen   --work-dir /tmp/hausbar-phase1-reproduction   --report /tmp/hausbar-phase1-reproduction.json
```

Master v7.66 bleibt die absolute Produktwahrheit.
