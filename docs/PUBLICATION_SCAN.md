# Public snapshot preparation

Prepared November 1, 2026. The public repository uses a new source snapshot and GitHub noreply commit identity. Local development history, personal author email metadata and internal planning records are excluded.

## What was checked

- Gitleaks 8.30.1 scanned all 76 reachable local development commits before export. Its one historical finding was geographic wording in an internal plan, not an account credential. That plan and history are not published.
- The curated public source was scanned separately. Prepared editor assets and runtime files were scanned, and all 1,751 runtime PAK entries were unpacked for configuration inspection.
- Supplemental byte inspection covered approximately 2.29 GB, including all four uncompressed Blender sources, Unreal assets, exported meshes, runtime binaries, source and screenshots. ASCII and NUL-stripped representations were checked for known credential formats and home-folder paths.
- The six gameplay screenshots have no embedded author, location or text metadata and are exact copies of actual game captures.
- Both ZIP archives passed complete CRC checks. Their SHA256 digests, sizes and file counts are pinned in `release-manifest.json` and supplied separately in `SHA256SUMS.txt`.

## Cleanup performed

- The original private engine configuration was excluded. The public engine configuration contains the safe cooked rendering/map settings and the correct game mode.
- Four Blender files contained a remembered file-browser Documents directory. Only their `FileSelectParams.dir` UI field was reset to a project-relative directory. Every byte outside that field is identical to the original model file.
- An unused vendor SDK client credential setting was cleared in the public runtime configuration. The executable and cooked scene containers retain their previously tested hashes. The rebuilt PAK passed integrity testing and exact extraction read-back.
- Website scripts and analytics beacons were removed from four cached license-page copies. Visible license text and source links were verified unchanged. Original downloads remain preserved locally.
- Debug symbols, saved games, logs, crash dumps, installed development tools, caches, private configuration and the original Git history are excluded.

Remaining automated findings were independently classified: six source-script SHA256 hashes, a stock engine metadata redirect and a stock Vulkan diagnostic identifier. A supplemental NUL-stripping match in an unchanged ICU resource joined separate language identifiers; it was not a raw credential. These classifications are tied to the exact files/values or vendor-file hashes, rather than blanket scanner exclusions.

Publication provenance, screenshot hashes and asset cleanup hashes are recorded in `PUBLICATION.json`. The asset installer verifies pinned downloads, rejects unsafe archive paths and symlinks, and preserves different existing files. Its normal/repeated-install and rejection cases were checked on Windows PowerShell 5.1.

This is a targeted pre-publication scan, not a guarantee that every possible sensitive-data format can be detected. No game window or editor was launched during publication preparation. The game remains an experimental preview; the original native performance result does not establish a fresh-machine runtime test of the public archive.
