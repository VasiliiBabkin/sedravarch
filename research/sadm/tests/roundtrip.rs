use sadm::{encode, Archive, Options, MAX_DATA};

fn next(seed: &mut u64) -> u64 {
    *seed ^= *seed << 13;
    *seed ^= *seed >> 7;
    *seed ^= *seed << 17;
    *seed
}

fn extract(archive: &Archive<'_>, file: usize) -> Vec<u8> {
    let mut restored = Vec::new();
    archive.extract(file, &mut restored).unwrap();
    restored
}

#[test]
fn generated_roundtrip_and_determinism() {
    let mut seed = 62319;
    for sample in 0..96 {
        let length = match sample % 4 {
            0 => 4096 + sample,
            1 => sample,
            2 => 16384 - sample,
            _ => next(&mut seed) as usize % 20000,
        };
        let mut original = Vec::new();
        for i in 0..length {
            let byte = next(&mut seed) as u8;
            original.push(match sample % 3 {
                0 => byte,
                1 => byte % 8,
                _ => (i / 4) as u8,
            });
        }
        let mut changed = original.clone();
        if length > 16 {
            changed.rotate_right(9);
            changed.splice(10..15, [4, 2, 9]);
        }
        let files = [&original[..], &[][..], &original[..], &changed[..]];
        let options = Options {
            multiscale: sample & 1 != 0,
            references: sample & 2 != 0,
            delta: sample & 4 != 0,
            rans: sample & 8 != 0,
            predict: sample & 16 != 0,
        };
        let bytes = encode(&files, options).unwrap();
        assert_eq!(bytes, encode(&files, options).unwrap());
        let archive = Archive::open(&bytes, MAX_DATA).unwrap();
        assert_eq!(archive.file_count(), files.len());
        for (id, file) in files.iter().enumerate() {
            assert_eq!(extract(&archive, id), *file, "sample {sample} file {id}");
        }
        assert!(Archive::open(
            &bytes,
            files
                .iter()
                .map(|f| f.len())
                .sum::<usize>()
                .saturating_sub(1)
        )
        .is_err());
    }
}

#[test]
fn exact_references_respect_depth() {
    let block = vec![b'X'; 4096];
    let inputs = vec![&block[..]; 8];
    let bytes = encode(&inputs, Options::default()).unwrap();
    let archive = Archive::open(&bytes, MAX_DATA).unwrap();
    assert_eq!(archive.stats().1[2], 7);
    assert_eq!(extract(&archive, 7), block);
    assert!(archive.extract(8, std::io::sink()).is_err());
}

#[test]
fn every_truncation_of_compact_archive_is_rejected() {
    let bytes = encode(&[&[3; 4096], &[4; 4111]], Options::default()).unwrap();
    for end in 0..bytes.len() {
        assert!(Archive::open(&bytes[..end], MAX_DATA).is_err());
    }
}
