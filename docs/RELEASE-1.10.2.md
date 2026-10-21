# Version 1.10.2

Repairs SageAttention fallback in newer ComfyUI engines that use single-owner attention tensor containers. Inputs are unpacked before the guarded attention call, so PyTorch can reuse the tensors if SageAttention rejects an input. The current generation continues without submitting a second job.

SageAttention remains optional in Settings. The compatibility check uses a small GPU math operation and creates no image or video. Model downloads, Library media, and existing preferences are preserved during the application-only update.
