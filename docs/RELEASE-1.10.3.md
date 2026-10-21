# Version 1.10.3

Fixes SageAttention startup for isolated engines, including MiniMax H3, Ref2VA, FLUX 3, Qwen Turbo, BFS, and Krea 2. The launcher now enters the engine's main module directly after preparing its dependency paths. Its private installation-folder argument no longer reaches ComfyUI's command-line parser.

The standard PyTorch launcher is unchanged. This repair does not change models, Library media, or generation parameters.

The compatibility check records its library-loading and math-test stages, allows up to three minutes for the initial load, and saves diagnostics to `logs/attention-check.log` on success, failure, or cancellation. Cancellation still terminates only its own check process.
