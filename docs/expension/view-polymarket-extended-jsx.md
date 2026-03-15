# Viewing `polymarket-agents-extended-arch.jsx` Visually

This file is a React component, so the fastest way to view it is to run it in a tiny Vite React app.

## Quick Preview (Recommended)

```bash
cd /tmp
npm create vite@latest jsx-viewer -- --template react
cd jsx-viewer
npm install
cp /Users/djbeatbug/RoadToMillion/polyagents/docs/polymarket-agents-extended-arch.jsx src/App.jsx
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`).

## Re-open Later

If you already created the viewer once:

```bash
cd /tmp/jsx-viewer
cp /Users/djbeatbug/RoadToMillion/polyagents/docs/polymarket-agents-extended-arch.jsx src/App.jsx
npm run dev
```

## Why This Approach

- The repo is Python-first and does not currently include a React runtime setup.
- Vite gives an isolated, disposable preview environment without changing this project.
