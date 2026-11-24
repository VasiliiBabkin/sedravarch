use sedravarch::{archive,Options};
use std::{env, fs::{self,File,OpenOptions}, io::{self,BufReader,BufWriter}, path::{Path,PathBuf}, process::ExitCode};
fn run() -> io::Result<()> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let usage = || io::Error::new(io::ErrorKind::InvalidInput,
        "usage: sedravarch pack-profile PRESET THREADS INPUT OUTPUT | create-profile PRESET THREADS ARCHIVE INPUT... | create ARCHIVE INPUT... | list ARCHIVE | extract ARCHIVE NEW_DIR [MAX_BYTES] | extract-file ARCHIVE ENTRY OUTPUT [MAX_BYTES] | pack INPUT OUTPUT | pack-fixed INPUT OUTPUT | pack-independent INPUT OUTPUT | unpack INPUT OUTPUT [MAX_BYTES] | test ARCHIVE [MAX_BYTES]");
    let limit = |i:usize| -> io::Result<u64> {
        match args.get(i) {
            Some(s) => s.to_str().and_then(|s|s.parse().ok()).ok_or_else(usage),
            None => Ok(8*1024*1024*1024),
        }
    };
    let profile=||->io::Result<Options>{
        let preset=args.get(1).and_then(|s|s.to_str()).ok_or_else(usage)?.parse()?;
        let threads=args.get(2).and_then(|s|s.to_str()).and_then(|s|s.parse().ok()).ok_or_else(usage)?;
        Options{preset,threads,..Options::default()}.validate()
    };
    match args.first().and_then(|s|s.to_str()) {
        Some("create-profile") if args.len()>=5 => archive::create_config(Path::new(&args[3]),&args[4..].iter().map(PathBuf::from).collect::<Vec<_>>(),profile()?),
        Some("pack-profile") if args.len()==5 => {
            let opts=profile()?;
            let input=BufReader::new(File::open(&args[3])?);
            let path=Path::new(&args[4]);
            let file=OpenOptions::new().write(true).create_new(true).open(path)?;
            let result=sedravarch::compress_config(input,BufWriter::new(file),opts);
            if result.is_err(){let _=fs::remove_file(path);}
            result
        }
        Some("create") if args.len()>=3 => archive::create(Path::new(&args[1]),&args[2..].iter().map(PathBuf::from).collect::<Vec<_>>()),
        Some("list") if args.len()==2 => {
            let a=archive::Archive::open(Path::new(&args[1]))?;
            for e in a.entries(){println!("{}\t{}\t{}\t{}",if e.directory{"dir"}else{"file"},e.size,e.modified.map_or("-".into(),|v|v.to_string()),e.path);}
            Ok(())
        }
        Some("extract") if (3..=4).contains(&args.len()) => archive::Archive::open(Path::new(&args[1]))?.extract(Path::new(&args[2]),limit(3)?),
        Some("extract-file") if (4..=5).contains(&args.len()) => archive::Archive::open(Path::new(&args[1]))?.extract_file(args[2].to_str().ok_or_else(usage)?,Path::new(&args[3]),limit(4)?),
        Some("test") if (2..=3).contains(&args.len()) => {
            if archive::is_multi(Path::new(&args[1]))? {archive::Archive::open(Path::new(&args[1]))?.test(limit(2)?)}
            else {sedravarch::decompress(BufReader::new(File::open(&args[1])?),io::sink(),limit(2)?)}
        },
        Some(mode @ ("pack"|"pack-fixed"|"pack-independent"|"unpack")) if args.len()==3 || (mode=="unpack" && args.len()==4) => {
            let max = limit(3)?;
            let input = BufReader::new(File::open(&args[1])?);
            let path = Path::new(&args[2]);
            let file = OpenOptions::new().write(true).create_new(true).open(path)?;
            let mut writer = BufWriter::new(file);
            let result = if mode=="pack" { sedravarch::compress(input,&mut writer) }
                else if mode=="pack-independent" { sedravarch::compress_with_options(input,&mut writer,sedravarch::chunking::Mode::Adaptive,false) }
                else if mode=="pack-fixed" { sedravarch::compress_with_mode(input,&mut writer,sedravarch::chunking::Mode::Fixed) }
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
