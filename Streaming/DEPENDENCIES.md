# Browser streaming dependency

Epic's PixelStreamingInfrastructure, matching Unreal Engine 5.8:

- Repository: https://github.com/EpicGamesExt/PixelStreamingInfrastructure
- Branch: UE5.8
- Tested revision: `558bc52ba404dd289ba01abb6c34bf684245f342`
- License: upstream MIT; retained in `Infrastructure/LICENSE.md`.
- Local tool versions: Node 24.15.0, npm 11.12.1.

The dependency checkout is deliberately separate from the game source. Its installed files are ignored by the parent project's `.gitignore`. No upstream source files were changed. `server.cjs` uses Epic's signalling library and serves its built reference player, with the game's own HTML wrapper and localhost listeners.

To recreate the existing local setup from the project root (requires Git, Node and network access):

```powershell
git clone --branch UE5.8 https://github.com/EpicGamesExt/PixelStreamingInfrastructure.git Streaming/Infrastructure
git -C Streaming/Infrastructure checkout 558bc52ba404dd289ba01abb6c34bf684245f342
Set-Location Streaming/Infrastructure
npm install --workspace Common --workspace Signalling --workspace SignallingWebServer --workspace Frontend/library --workspace Frontend/ui-library --workspace Frontend/implementations/typescript --include-workspace-root --ignore-scripts --no-audit --no-fund
npm run build:all:cjs
```

Then return to the project root and run `Browser.cmd`. Do not clone over an existing checkout. Install these dependencies on each development machine.
