# Version 1.14.0

Reference controls appear only for compatible models:

- Images: FLUX.2 Klein and Viggle accept up to three references; FLUX 3 Klein accepts ten. Choose from Library or local files and remove or clear selections. Prompts explain the model-specific image numbering.
- Video: MiniMax H3 Ref2VA accepts the primary reference plus eight extra character references. Its primary image is labelled Reference image 1. Wan, LTX and MiniMax Turbo retain starting-frame controls without claiming extra reference support.
- Image Editor hides extra-reference controls for single-image repainting models.

References use native conditioning nodes, preserve their aspect ratios, and remain distinct from output size. They are saved with queue jobs, restored on editing/reuse, and recorded in output metadata. Model changes retain separate reference selections. Duplicate, missing and excess references are rejected. Reference use increases memory requirements.

No AI image/video generation was performed for validation. Existing settings, models, media and Canvas projects are preserved.
