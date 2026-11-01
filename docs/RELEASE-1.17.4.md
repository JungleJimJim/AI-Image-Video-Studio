# Studio 1.17.4 — LoRA list and queue visibility

- Remove an adapter from the LoRA list with its Remove button or right-click menu. Its file stays on disk; import it again to restore it. Removing an adapter clears its saved enabled selections in shared model libraries.
- Import and download messages now refer to the installed list and saving the selection.
- When jobs are waiting in a paused queue, the status bar shows the paused state and offers a Resume queue button. Existing paused queues remain paused until resumed.

Tests cover LoRA removal, restoration and shared selections, and starting a queued job after an import. Generation is mocked in these tests; no AI inference was run for this release.
