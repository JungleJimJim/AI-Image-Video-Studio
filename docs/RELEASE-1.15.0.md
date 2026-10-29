# Studio 1.15.0 — Canvas workspace

The interface follows the Photoshop-inspired Canvas concept: charcoal panels, blue selections, a slim tool rail, document headers, a central preview and a right-hand properties dock.

All 13 existing tools remain available: Images, Image Editor, Canvas, Faceswap, Video, Talking Avatar, Voice, Upscale, Library, Models, LoRAs, Settings and Queue. Existing forms, model choices, generation handlers, imports, editing, references and queue operations are reused.

New workspace features:

- Recent Library filmstrip with image/video filters, cached thumbnails, media details and refresh.
- Focus mode expands previews and Canvas; switching tools restores the controls.
- Adjustable properties width (280–460 px on wide windows).
- Saved local workspace preferences and Reset workspace.
- Accessible tool names, current-page indicators and keyboard focus styling.

The filmstrip uses the existing authenticated Library API. It never starts generation and does not modify media. The full Library and layered Canvas remain available.

Validation completed:

- 288 Python regression tests and 19 UI test suites passed.
- All 13 tools were checked in Edge at 1366×768 and 760×600, with no horizontal page overflow or clipped action buttons.
- Workspace navigation, unsaved prompts, media filters, saved panel preferences, reset, Canvas operations and queue payloads were checked.
- Packaged UI assets matched the source, and the installed toolbar cleanup was verified.
- The app-only update preserved settings, 166 model files and 129 media files.

No AI inference or generation-performance benchmark was run for this interface change.
