# hermes-hackaton

Early-stage hackathon project built on top of Hermes Agent.

## Scope

The project target is a local web-based game/simulation where:
- multiple Hermes-backed player agents inhabit the same world
- those agents are treated as separate in-world actors rather than one shared mind
- all player agents use the same common doctrine for how to play
- private state remains isolated per agent
- they face a shared LLM-controlled enemy/opposing force

The goal is not a generic multi-agent demo. The goal is a playable, inspectable game layer where multiple isolated agents react differently inside the same environment.

## Current Status

This repository is still in architecture and adaptation phase. The scope is fixed, but the final game loop and implementation are still in progress.

## Repository State

This repo currently contains project scaffolding and planning material.

Planned canonical structure:
- `docs/` — public project documentation and architecture notes
- `src/` — runtime implementation
- `services/` — optional service-specific modules if the project grows beyond a single runtime

Some local working files used for private process, prompting, and internal agentic operations are intentionally not part of the public project surface.
