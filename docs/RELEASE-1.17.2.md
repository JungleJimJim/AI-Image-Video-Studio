# Studio 1.17.2 — OpenJutsu embedded workspace connection

Studio previously advertised the OpenJutsu workspace as running as soon as its processes existed. Status polling could load the iframe before Next.js accepted connections. The browser then retained its connection-refused page after the editor became healthy.

The workspace now exposes its editor URL only after both the editor HTTP request and proxy health check succeed. Process liveness remains checked during startup, and closing the workspace clears HTTP readiness.

This update preserves existing editor, backend and model installations. It includes the slower-drive startup allowance from [1.17.1](RELEASE-1.17.1.md).
