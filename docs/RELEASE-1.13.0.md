# Version 1.13.0

Canvas tab next to Image Editor:

- Drag local PNG, JPEG or WebP files and Library thumbnails onto an artboard.
- Arrange image and text layers; move, resize, rotate, change opacity, reorder, duplicate, hide or lock them.
- Wheel zoom, pan, fit view, undo and redo. Source PNG transparency is preserved.
- Set artboard dimensions and background. Side panels scroll independently of the artboard.
- Automatic local draft and named editable projects in `canvas-projects`.
- Save composites as new Library images, or save and send to Image Editor or Video.
- Transfer layer captions, text and positions into a MOSS layout without starting generation. Photo identity requires repainting the composite through Image Editor.

Canvas imports/exports run independently of the generation queue and preserve its active progress. Existing settings, model files and Library media are retained during updates.

Limits: 64 layers, 16,777,216 output pixels, 100 megapixels of decoded source images, and 25 MB per imported/exported image. MOSS layout transfer supports 24 visible elements.
