# Desktop 0.8 prototype — verification status, 2026-11-24

Core 0.7 is verified and in main (see docs/benchmarks/2026-11-24-v07.md). Desktop source remains in dev/desktop-gui, based on 0.7. The separately compiled UI-independent adapter in commit 86118c1d41a450cc4e25c901253ebdcd73287afd passed 2/2 tests on the VDS (cargo test --offline --test desktop_ops), covering multi-file creation, opening and listing, integrity check, selective and full extraction, rejection of overwrite, legacy stream packing and unpacking.

A full graphical build was attempted from commit 24e62ed16082c79972ab9cab3f4154faa8549b65. Cargo reached crates.io index resolution but downloaded index entries slowly; the job was cancelled before lockfile generation or compilation completed. The temporary workspace was explicitly removed after confirmed cancellation. Final GUI source is not compiler-verified. No desktop binaries, lockfile, screenshots, native window/dialog tests or Windows/macOS builds have been produced. The VDS has no graphical session. No system packages were installed; no GitHub Actions used.

Next: resolve dependencies and commit desktop/Cargo.lock, run cargo check/test/build on the exact final GUI commit, perform visual and native dialog tests on a graphical machine, then decide whether to merge desktop into main. Do not advertise the prototype as a finished desktop release.


## Windows alpha.1 field report and alpha.2 remediation

The published alpha.1 passed core and headless UI tests, but a user reported that the executable immediately exits without a persistent process or visible window. The exact cause is unknown. The alpha.1 PE import table confirms dependencies on opengl32.dll and VCRUNTIME140.dll. Alpha.2 introduces a separate native Win32 frontend (no OpenGL), sets static CRT for Windows CI, preserves the original frontend as SedravArch-OpenGL.exe and records startup/panic failures in %LOCALAPPDATA%\SedravArch\startup.log. The native frontend provides file/directory selection, archive listing, creation, testing and full/selected extraction. It is deliberately simpler than the egui frontend; no search box or resizable layout in this first native version. Release requires a real native-window creation and message-loop smoke test on the Windows runner, in addition to the existing unit tests. This does not establish that the user's exact machine has been fixed. If it still fails, ask for the startup log; if no log exists, investigate process-loader errors and Windows security history without disabling security controls.


## Alpha.2 release verification and field report (2026-11-24)

Supersedes the earlier pre-release build status above. Release v0.8.1-alpha.2 was built from 77ff560c9db00c0614685d79dd973509447169a8. Windows CI run 45406873825 completed core tests (45+2), desktop tests (3+2), native-window creation, message-loop smoke and packaging. The published ZIP was downloaded to the VDS and verified against SHA256SUMS.txt; its native EXE imports neither opengl32.dll nor VCRUNTIME140.dll. User confirmed that the native GUI opens on their Windows computer and reported successful archive creation. Screenshot shows native window, Russian controls and empty initial list.

User-reported approximate sizes, not independently measured: PDF directory 28 MB original, 21.8 MB Balanced (about 22.1% reduction), 20 MB Extreme (about 28.6% reduction). An unspecified EXE produced a larger archive than the original. No original test files, exact byte sizes, timing, comparison with other archivers or explicit byte-equality extraction result provided. Do not infer complete field acceptance or general performance from these observations.

Next research priorities: representative executable and PDF corpus; measure against gzip/xz/zstd and distinguish already compressed/packed EXEs from ordinary PE binaries; investigate reversible executable-specific transforms and cross-file deduplication. Report input/output sizes and expansion honestly. Native UI is a compatibility-first prototype; improve usability independently of the codec. Preserve decoding support for earlier archive versions.
