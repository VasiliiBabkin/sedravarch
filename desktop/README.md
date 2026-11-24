# SedravArch Desktop 0.8 (prototype)

Native Rust desktop client using eframe/egui 0.32 and rfd file dialogs; the core crate remains free of third-party dependencies.

From the repository root:
```sh
cargo run --release --manifest-path desktop/Cargo.toml
cargo test --manifest-path desktop/Cargo.toml
```

Russian interface, archive browser with search and selection, multi-file creation (files and directories), four compression profiles, 1–8 workers, verification, extraction of all or selected files, and legacy single-stream pack/unpack. File operations run on a worker thread; controls are disabled while busy. Normal close requests are ignored during work. Output paths must not exist. Full extraction creates a new directory named <archive>-restored under the chosen parent. GUI has an 8 GiB extraction budget. Files are processed locally.

Linux requires a working graphical session, OpenGL and system file-dialog support (XDG desktop portal or supported fallback). Windows/macOS require native platform runtime and toolchain. Native dialogs may differ by platform. No progress percentage, cancellation, installer, file association, or encryption yet. Closing the process forcibly can leave partial output; never use sole copies of valuable data. See root README for core security and format limitations.

Build and visual testing status is documented separately. The headless UI test does not exercise native window creation or native dialogs.
