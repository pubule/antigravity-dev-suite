# /dev — Magnitude-Aware SDLC Pipeline Suite

Pipeline SDLC deterministica e magnitude-aware per **Claude Code**.
Automatizza lo sviluppo software dall'idea al codice pronto per il rilascio, calibrando la cerimonia (triage, brainstorming, design council, pianificazione, TDD con worktree isolati, adversarial code review e quality gate) in base alla complessità della task.

---

## ⚡ Caratteristiche

- **Routing Table Deterministica:**
  - **TRIVIAL:** Fix rapidi, typo, bump dipendenze (salta council e worktree, test e audit rapidi).
  - **STANDARD:** Nuove feature, bug complessi (brainstorming, piani, workflow paralleli, ship council).
  - **COMPLEX:** Moduli greenfield, architettura critica (Design Council, piani rigorosi, doppia review avversaria).
- **Quality Gates Bloccanti:**
  - Gate G1: Design Council GO obbligatorio per task complesse.
  - Gate G2.5: Impeccable Quality Gate per coding standards ed error handling.
  - Gate G2.5b: Error & Logging Strategy obbligatoria per codice greenfield.
  - Gate G2.6: UI Quality Gate per frontend (anti-pattern & a11y detector).
  - Gate G3: Ship Council GO per rilascio.
- **Workflow Engine Parallelo:** Esecuzione di task TDD in git worktrees paralleli, merge automatico, loop di auto-debug e review avversaria (maestro review + refutazione).
- **Session Recovery & Handoff:** Tracking dello stato in `.dev-pipeline-state.json` e `HANDOFF.md` persistente per riprendere il lavoro anche dopo `/clear` o riavvio sessione.

---

## 📦 Prerequisiti

1. **Git** (disponibile nel `PATH`)
2. **Node.js** (v18+ raccomandata, già richiesta da Claude Code)
3. **Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`)

---

## 🚀 Installazione Rapida (Opzione 2)

Gli script di setup verificano i prerequisiti, scaricano le dipendenze richieste (`superpowers` e `llm-council`) e registrano la suite `/dev`.

### macOS / Linux
```bash
git clone <URL_QUESTO_REPO>
cd antigravity-dev-suite
chmod +x setup.sh
./setup.sh
```

### Windows (PowerShell)
```powershell
git clone <URL_QUESTO_REPO>
cd antigravity-dev-suite
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### In alternativa via Marketplace Claude Code
```bash
/plugin marketplace add <owner>/<repo>
/plugin install dev --marketplace <owner>/<repo>
```

---

## 🧩 Dipendenze Integrate da Setup

Lo script `setup` installa automaticamente:

| Dipendenza | Tipo | Ruolo nella Pipeline |
|---|---|---|
| `superpowers@claude-plugins-official` | Plugin Claude Code | Brainstorming, scrittura piani, worktree Git, chiusura branch |
| `llm-council` | Skill Claude Code | Design Council (Phase 2) e Ship Council (Phase 9) multi-prospettiva |
| `dev` | Plugin / Skill | Orchestratore `/dev`, hook di handoff e workflow paralleli |

---

## 🛠️ Utilizzo

All'interno di qualsiasi sessione Claude Code nella root del tuo progetto:

```bash
# Avvio interattivo
/dev

# oppure con descrizione diretta della task
/dev implementa il supporto al retry con backoff esponenziale nel client HTTP
```

### Ripresa da sessioni interrotte

Se una task viene interrotta o la sessione viene pulita con `/clear`:
- Il SessionStart hook rileva automaticamente la presenza di un `HANDOFF.md` in corso.
- Esegui `/dev`: la pipeline verificherà lo stato e ti chiederà se riprendere dalla fase interrotta.

---

## 🗑️ Disinstallazione

- **macOS / Linux:** `./uninstall.sh`
- **Windows:** `powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`
