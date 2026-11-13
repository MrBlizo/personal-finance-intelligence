# winget

Manifests for the Inno Setup installer from the GitHub release, in the
folder layout of [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).
They were checked against the official 1.6.0 schemas.

The Microsoft Store version can usually be installed by its Store ID
already, without these manifests:

```powershell
winget install 9MZKW4H9F0J5
```

## Submit a version

1. Fork microsoft/winget-pkgs and copy `manifests/m/MrBlizo/PersonalFinanceIntelligence/<version>/`
   into the same path of the fork.
2. On Windows, test it: `winget validate --manifest <folder>` and
   `winget install --manifest <folder>` (needs `winget settings --enable LocalManifestFiles`
   once, from an administrator terminal).
3. Open a pull request to microsoft/winget-pkgs. Automated checks run first, then a moderator reviews it.

For a new release, copy the folder, change `PackageVersion`, `InstallerUrl`,
`ReleaseDate` and `InstallerSha256`. The SHA256 is shown for each release
asset on GitHub, or run `Get-FileHash .\PFI-Setup-<version>.exe` in PowerShell.
