# 1.11.2

Launching an uninstalled application copy from a build or download folder now opens the verified registered Studio installation. The copy no longer attempts to create Library migration data beside itself when an installation already exists. This fixes the startup error referencing `assets/library-layout-v2` when Windows blocks writes in the source folder.

Explicit `--root` profiles and separate portable installations retain their existing paths. Settings, models and Library media are unchanged. Includes the 1.11.1 bounded Ref2VA/MiniMax model reader.
