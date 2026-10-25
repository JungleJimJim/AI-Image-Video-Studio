# Version 1.13.2

Starting-image imports stay available while generation is running, including replacing an existing image on the Video tab. Importing uses an independent CPU request and returns the exact imported Library item directly to the selected tool. It does not modify the current generation, queue progress or result.

Import buttons are disabled only while another source-image import is in flight, or when the editor reference limit has been reached. They recover after failed reads or requests. Clearing the file picker permits selecting the same local file again.

Existing settings, model files, Library media and Canvas projects are preserved.
