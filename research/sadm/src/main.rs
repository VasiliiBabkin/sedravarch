use sadm::{Archive, Options, MAX_ARCHIVE, MAX_DATA};
use std::fs::{self, File};
use std::io::{self, BufWriter, Read, Write};
use std::path::Path;
use std::process::ExitCode;

fn read(path: &str, limit: usize) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    File::open(path)?
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > limit {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "input size limit",
        ));
    }
    Ok(bytes)
}

fn write(
    path: &str,
    operation: impl FnOnce(&mut BufWriter<File>) -> io::Result<()>,
) -> io::Result<()> {
    let mut output = BufWriter::new(File::create_new(path)?);
    let result = operation(&mut output).and_then(|()| output.flush());
    drop(output);
    if result.is_err() {
        let _ = fs::remove_file(Path::new(path));
    }
    result
}

fn run() -> io::Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let usage = || {
        io::Error::new(io::ErrorKind::InvalidInput,
        "sadm encode [--multiscale|--no-multiscale|--no-references|--no-delta|--no-rans|--no-predict]... ARCHIVE INPUT... | decode ARCHIVE OUTPUT | extract ARCHIVE ORDINAL OUTPUT | verify ARCHIVE | stats ARCHIVE | analyze INPUT")
    };
    match args.first().map(String::as_str) {
        Some("encode") => {
            let mut options = Options::default();
            let mut rest = &args[1..];
            while let Some(flag) = rest.first().filter(|arg| arg.starts_with("--")) {
                match flag.as_str() {
                    "--multiscale" => options.multiscale = true,
                    "--no-multiscale" => options.multiscale = false,
                    "--no-references" => options.references = false,
                    "--no-delta" => options.delta = false,
                    "--no-rans" => options.rans = false,
                    "--no-predict" => options.predict = false,
                    "--" => {
                        rest = &rest[1..];
                        break;
                    }
                    _ => return Err(usage()),
                }
                rest = &rest[1..];
            }
            if !(2..=1025).contains(&rest.len()) {
                return Err(usage());
            }
            let mut files = Vec::new();
            let mut remaining = MAX_DATA;
            for path in &rest[1..] {
                let data = read(path, remaining)?;
                remaining -= data.len();
                files.push(data);
            }
            let archive = sadm::encode(
                &files.iter().map(Vec::as_slice).collect::<Vec<_>>(),
                options,
            )?;
            write(&rest[0], |writer| writer.write_all(&archive))
        }
        Some("analyze") if args.len() == 2 => {
            let data = read(&args[1], MAX_DATA)?;
            let (entropy, min, max, repeated) = sadm::analyze(&data);
            println!("{{\"bytes\":{},\"entropy\":{entropy},\"local_min\":{min},\"local_max\":{max},\"repeated_blocks\":{repeated}}}", data.len());
            Ok(())
        }
        Some("verify" | "stats" | "decode" | "extract") if args.len() >= 2 => {
            let bytes = read(&args[1], MAX_ARCHIVE)?;
            let archive = Archive::open(&bytes, MAX_DATA)?;
            match args[0].as_str() {
                "verify" if args.len() == 2 => archive.verify(),
                "stats" if args.len() == 2 => {
                    let (decoded, tags) = archive.stats();
                    println!("{{\"archive_bytes\":{},\"decoded_bytes\":{decoded},\"files\":{},\"tags\":{tags:?}}}", bytes.len(), archive.file_count());
                    Ok(())
                }
                "decode" if args.len() == 3 && archive.file_count() == 1 => {
                    write(&args[2], |writer| archive.extract(0, writer))
                }
                "extract" if args.len() == 4 => {
                    let file = args[2].parse().map_err(|_| usage())?;
                    write(&args[3], |writer| archive.extract(file, writer))
                }
                _ => Err(usage()),
            }
        }
        _ => Err(usage()),
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("sadm: {error}");
            ExitCode::FAILURE
        }
    }
}
