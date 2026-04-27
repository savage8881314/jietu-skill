# web-capture-layout

`web-capture-layout` is a Codex skill for capturing public product pages and generating screenshot-based competitor analysis outputs.

## Repository layout

```text
web-capture-layout-repo/
├─ README.md
├─ .gitignore
├─ install.ps1
└─ skill/
   ├─ SKILL.md
   ├─ agents/
   │  └─ openai.yaml
   ├─ references/
   │  └─ manifest.example.json
   └─ scripts/
      └─ capture_and_layout.py
```

## Install on another computer

1. Clone this repository.
2. Run:

```powershell
.\install.ps1
```

By default the script installs the skill to:

```text
C:\Users\<YourUser>\.codex\skills\web-capture-layout
```

## Runtime requirements

- Python with `playwright`
- A Chromium-based browser runtime

Example:

```powershell
pip install playwright
playwright install chromium
```

If you prefer Microsoft Edge, set the manifest browser channel to `msedge`.
