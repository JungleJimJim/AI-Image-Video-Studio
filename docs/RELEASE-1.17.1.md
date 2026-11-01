# Studio 1.17.1 — OpenJutsu startup on slower drives

The managed backend's initial imports can take more than four minutes on slower storage. Startup now allows ten minutes and reports elapsed time every five seconds while waiting for the local API. Cancellation and early process-failure detection remain available.

This update reuses the editor, backend, node packs and model files installed by 1.17.0. No model reinstallation is needed. See [managed setup instructions](RELEASE-1.17.0.md).
