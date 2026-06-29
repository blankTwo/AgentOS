# Agent OS VSCode Plugin

This package provides a lightweight VSCode entry point for Agent OS.

## Responsibilities

- inject Agent OS into the current workspace
- show installation and health status
- surface dashboard and report artifacts
- keep the panel as an observer, not a chat runtime

## Commands

- `Agent OS: Inject Workspace`
- `Agent OS: Refresh Status`
- `Agent OS: Open Overview`

## Development

```bash
npm run check
npm run prepare:agent-os
npm run package
```

`prepare:agent-os` copies the Agent OS core into `vscode-plugin/agent-os/` for extension packaging. That generated directory is ignored by Git.

`npm run package` creates a local `.vsix` package. The generated VSIX is ignored by Git.

## Notes

- The plugin reads Agent OS state from the current workspace `.agent-os/` directory.
- User project execution documents still live under `docs/agent-os/`.
- The plugin does not replace the core Agent OS runtime.
