# Desktop 0.8 prototype — verification status, 2026-11-24

Core 0.7 is verified and in main (see docs/benchmarks/2026-11-24-v07.md). Desktop source remains in dev/desktop-gui, based on 0.7. The separately compiled UI-independent adapter in commit 86118c1d41a450cc4e25c901253ebdcd73287afd passed 2/2 tests on the VDS (cargo test --offline --test desktop_ops), covering multi-file creation, opening and listing, integrity check, selective and full extraction, rejection of overwrite, legacy stream packing and unpacking.

A full graphical build was attempted from commit 24e62ed16082c79972ab9cab3f4154faa8549b65. Cargo reached crates.io index resolution but downloaded index entries slowly; the job was cancelled before lockfile generation or compilation completed. The temporary workspace was explicitly removed after confirmed cancellation. Final GUI source is not compiler-verified. No desktop binaries, lockfile, screenshots, native window/dialog tests or Windows/macOS builds have been produced. The VDS has no graphical session. No system packages were installed; no GitHub Actions used.

Next: resolve dependencies and commit desktop/Cargo.lock, run cargo check/test/build on the exact final GUI commit, perform visual and native dialog tests on a graphical machine, then decide whether to merge desktop into main. Do not advertise the prototype as a finished desktop release.
