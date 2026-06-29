# Agent OS VSCode Plugin

This package provides a lightweight VSCode entry point for Agent OS.

## Responsibilities

- inject Agent OS into the current workspace
- show installation and health status
- open the combined overview page
- keep the panel as an observer, not a chat runtime

## Commands

- `Agent OS: Inject Workspace`
- `Agent OS: Refresh Status`
- `Agent OS: Open Overview`

## Notes

- The plugin reads Agent OS state from the current workspace `.agent-os/` directory.
- User project execution documents still live under `docs/agent-os/`.
- The plugin does not replace the core Agent OS runtime.
