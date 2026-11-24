//! Startup diagnostics shared by both Windows frontends.
use std::{fs::{self,OpenOptions},io::Write,path::PathBuf};
pub fn path()->PathBuf{
    if let Some(p)=std::env::var_os("SEDRAVARCH_STARTUP_LOG"){return p.into();}
    let base=std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    base.join("SedravArch").join("startup.log")
}
pub fn log(message:&str){
    let p=path();
    if let Some(dir)=p.parent(){let _=fs::create_dir_all(dir);}
    if let Ok(mut f)=OpenOptions::new().create(true).append(true).open(p){
        let now=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|x|x.as_secs()).unwrap_or(0);
        let _=writeln!(f,"{now} pid={} {message}",std::process::id());
    }
}
pub fn init(frontend:&str){
    log(&format!("start {frontend} {}",env!("CARGO_PKG_VERSION")));
    std::panic::set_hook(Box::new(|info|log(&format!("panic: {info}"))));
}
pub fn fatal(message:&str){
    log(&format!("fatal: {message}"));
    let detail=format!("{message}\n\nЖурнал: {}",path().display());
    #[cfg(windows)] unsafe{
        use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW,MB_OK,MB_ICONERROR};
        let text:Vec<u16>=detail.encode_utf16().chain(Some(0)).collect();
        let title:Vec<u16>="SedravArch — ошибка запуска".encode_utf16().chain(Some(0)).collect();
        // Avoid modal dialogs in automated smoke tests.
        if !std::env::args_os().any(|x|x=="--smoke-test"){MessageBoxW(std::ptr::null_mut(),text.as_ptr(),title.as_ptr(),MB_OK|MB_ICONERROR);}
    }
    #[cfg(not(windows))] eprintln!("{detail}");
}
