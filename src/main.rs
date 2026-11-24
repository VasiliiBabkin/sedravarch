use std::{env, fs::{self,File,OpenOptions}, io::{self,BufReader,BufWriter}, path::Path, process::ExitCode};
fn run() -> io::Result<()> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let usage = || io::Error::new(io::ErrorKind::InvalidInput,
        "usage: sedravarch pack INPUT OUTPUT | unpack INPUT OUTPUT [MAX_BYTES] | test ARCHIVE [MAX_BYTES]");
    let limit = |i:usize| -> io::Result<u64> {
        match args.get(i) {
            Some(s) => s.to_str().and_then(|s|s.parse().ok()).ok_or_else(usage),
            None => Ok(8*1024*1024*1024),
        }
    };
    match args.first().and_then(|s|s.to_str()) {
        Some("test") if (2..=3).contains(&args.len()) =>
            sedravarch::decompress(BufReader::new(File::open(&args[1])?),io::sink(),limit(2)?),
        Some(mode @ ("pack"|"unpack")) if args.len()==3 || (mode=="unpack" && args.len()==4) => {
            let max = limit(3)?;
            let input = BufReader::new(File::open(&args[1])?);
            let path = Path::new(&args[2]);
            let file = OpenOptions::new().write(true).create_new(true).open(path)?;
            let mut writer = BufWriter::new(file);
            let result = if mode=="pack" { sedravarch::compress(input,&mut writer) }
                else { sedravarch::decompress(input,&mut writer,max) };
            drop(writer);
            if result.is_err() { let _ = fs::remove_file(path); }
            result
        }
        _ => Err(usage()),
    }
}
fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => { eprintln!("sedravarch: {e}"); ExitCode::FAILURE }
    }
}
