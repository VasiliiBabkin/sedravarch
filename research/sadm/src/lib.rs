mod delta;
mod entropy;
mod plan;
mod predict;
mod search;

use std::io;

pub const MAX_DATA: usize = 64 * 1024 * 1024;
pub const MAX_ARCHIVE: usize = MAX_DATA + 4 * 1024 * 1024;
const MAX_FILES: usize = 1024;
const GRID: usize = 4096;
const BLOCK: usize = GRID * 4;
const DEPTH: usize = 3;
const MAGIC: &[u8; 8] = b"SADM\x01\r\n\0";
type Result<T> = io::Result<T>;

fn bad(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}
fn take<'a>(bytes: &mut &'a [u8], count: usize) -> Result<&'a [u8]> {
    let (head, tail) = bytes
        .split_at_checked(count)
        .ok_or_else(|| bad("truncated input"))?;
    *bytes = tail;
    Ok(head)
}
fn u16_from(bytes: &mut &[u8]) -> Result<usize> {
    Ok(u16::from_le_bytes(take(bytes, 2)?.try_into().unwrap()) as usize)
}
fn u32_from(bytes: &mut &[u8]) -> Result<u32> {
    Ok(u32::from_le_bytes(take(bytes, 4)?.try_into().unwrap()))
}

const fn crc_table() -> [u32; 256] {
    let mut table = [0u32; 256];
    let mut i = 0;
    while i < 256 {
        let mut value = i as u32;
        let mut bit = 0;
        while bit < 8 {
            value = (value >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(value & 1));
            bit += 1;
        }
        table[i] = value;
        i += 1;
    }
    table
}
fn crc(bytes: &[u8]) -> u32 {
    const TABLE: [u32; 256] = crc_table();
    let mut state = u32::MAX;
    for &byte in bytes {
        state = (state >> 8) ^ TABLE[(state as u8 ^ byte) as usize];
    }
    !state
}

#[derive(Clone, Copy)]
pub struct Options {
    pub multiscale: bool,
    pub references: bool,
    pub delta: bool,
    pub rans: bool,
    pub predict: bool,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            multiscale: false,
            references: true,
            delta: true,
            rans: true,
            predict: true,
        }
    }
}

pub fn encode(files: &[&[u8]], options: Options) -> Result<Vec<u8>> {
    if files.len() > MAX_FILES {
        return Err(bad("file count limit"));
    }
    let mut total = 0usize;
    let mut archive = MAGIC.to_vec();
    archive.extend_from_slice(&(files.len() as u32).to_le_bytes());
    let mut history = Vec::new();
    let mut index = search::Index::default();
    for &data in files {
        if data.len() > MAX_DATA - total {
            return Err(bad("input size limit"));
        }
        total += data.len();
        let path = plan::segment(data, &history, &index, options);
        archive.extend_from_slice(&(data.len() as u32).to_le_bytes());
        archive.extend_from_slice(&(path.len() as u32).to_le_bytes());
        let mut offset = 0;
        for block in path {
            archive.push(block.tag);
            archive.extend_from_slice(&(block.size as u16).to_le_bytes());
            archive.extend_from_slice(&(block.payload.len() as u32).to_le_bytes());
            archive.extend_from_slice(&block.base.to_le_bytes());
            archive.extend_from_slice(&block.crc.to_le_bytes());
            archive.extend_from_slice(&block.payload);
            let bytes = &data[offset..offset + block.size];
            if options.references {
                index.insert(history.len(), search::fingerprint(bytes));
            }
            history.push((bytes, block.depth));
            offset += block.size;
        }
    }
    archive.extend_from_slice(&crc(&archive).to_le_bytes());
    Ok(archive)
}

struct Record<'a> {
    tag: u8,
    size: usize,
    base: usize,
    crc: u32,
    depth: usize,
    payload: &'a [u8],
}

pub struct Archive<'a> {
    records: Vec<Record<'a>>,
    files: Vec<std::ops::Range<usize>>,
    decoded: usize,
}

impl<'a> Archive<'a> {
    pub fn open(bytes: &'a [u8], limit: usize) -> Result<Self> {
        if !(16..=MAX_ARCHIVE).contains(&bytes.len()) {
            return Err(bad("archive size limit"));
        }
        let (mut stream, mut footer) = bytes.split_at(bytes.len() - 4);
        if take(&mut stream, MAGIC.len())? != MAGIC {
            return Err(bad("SADM magic or version"));
        }
        if crc(&bytes[..bytes.len() - 4]) != u32_from(&mut footer)? {
            return Err(bad("archive CRC"));
        }
        let count = u32_from(&mut stream)? as usize;
        if count > MAX_FILES {
            return Err(bad("file count limit"));
        }
        let mut records = Vec::<Record<'a>>::new();
        let mut files = Vec::with_capacity(count);
        let mut decoded = 0usize;
        for _ in 0..count {
            let size = u32_from(&mut stream)? as usize;
            let blocks = u32_from(&mut stream)? as usize;
            if size > limit.min(MAX_DATA) - decoded || blocks > size.div_ceil(GRID) {
                return Err(bad("file size or block count limit"));
            }
            decoded += size;
            let first = records.len();
            let mut remaining = size;
            for ordinal in 0..blocks {
                let tag = take(&mut stream, 1)?[0];
                let length = u16_from(&mut stream)?;
                let packed = u32_from(&mut stream)? as usize;
                let reference = u32_from(&mut stream)?;
                let crc = u32_from(&mut stream)?;
                if length == 0
                    || length > BLOCK
                    || length > remaining
                    || (ordinal + 1 < blocks && length % GRID != 0)
                    || packed > length
                {
                    return Err(bad("block extents"));
                }
                let base = reference as usize;
                let depth = match tag {
                    0 if reference == u32::MAX && packed == length => 0,
                    1 | 4..=7 if reference == u32::MAX && packed > 0 => 0,
                    2 | 3 if base < first => {
                        let prior = &records[base];
                        if prior.depth >= DEPTH
                            || (tag == 2 && (packed != 0 || length != prior.size))
                            || (tag == 3 && packed == 0)
                        {
                            return Err(bad("dependency extent or depth"));
                        }
                        prior.depth + 1
                    }
                    _ => return Err(bad("codec or dependency")),
                };
                records.push(Record {
                    tag,
                    size: length,
                    base,
                    crc,
                    depth,
                    payload: take(&mut stream, packed)?,
                });
                remaining -= length;
            }
            if remaining != 0 {
                return Err(bad("file length"));
            }
            files.push(first..records.len());
        }
        if !stream.is_empty() {
            return Err(bad("trailing input"));
        }
        Ok(Self {
            records,
            files,
            decoded,
        })
    }
    pub fn file_count(&self) -> usize {
        self.files.len()
    }
    pub fn stats(&self) -> (usize, [usize; 8]) {
        let mut counts = [0; 8];
        for record in &self.records {
            counts[record.tag as usize] += 1;
        }
        (self.decoded, counts)
    }
    fn block(&self, id: usize) -> Result<Vec<u8>> {
        let record = &self.records[id];
        let data = match record.tag {
            0 => record.payload.to_vec(),
            2 => self.block(record.base)?,
            3 => delta::decode(&self.block(record.base)?, record.payload, record.size)?,
            _ => {
                let mut data = entropy::decode(record.payload, record.size)?;
                if record.tag >= 4 {
                    predict::restore(&mut data, plan::LAGS[record.tag as usize - 4]);
                }
                data
            }
        };
        if crc(&data) != record.crc {
            return Err(bad("decoded block CRC"));
        }
        Ok(data)
    }
    pub fn extract(&self, file: usize, mut output: impl io::Write) -> Result<()> {
        let range = self.files.get(file).ok_or_else(|| bad("file ordinal"))?;
        for id in range.clone() {
            output.write_all(&self.block(id)?)?;
        }
        Ok(())
    }
    pub fn verify(&self) -> Result<()> {
        for file in 0..self.file_count() {
            self.extract(file, io::sink())?;
        }
        Ok(())
    }
}

pub fn analyze(data: &[u8]) -> (f64, f64, f64, usize) {
    let mut minimum: f64 = 8.0;
    let mut maximum: f64 = 0.0;
    let mut distinct = std::collections::BTreeSet::new();
    let mut repeats = 0;
    for bytes in data.chunks(GRID) {
        let h = entropy::shannon(bytes);
        minimum = minimum.min(h);
        maximum = maximum.max(h);
        if !distinct.insert(bytes) {
            repeats += 1;
        }
    }
    (
        entropy::shannon(data),
        if data.is_empty() { 0.0 } else { minimum },
        maximum,
        repeats,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn crc_vector() {
        assert_eq!(crc(b"123456789"), 0xcbf43926);
    }
    #[test]
    fn malformed_records_past_outer_crc() {
        let raw = Options {
            rans: false,
            ..Options::default()
        };
        let archive = encode(&[b"example"], raw).unwrap();
        for (offset, value) in [(20, 2), (21, 0), (23, 255), (27, 0), (16, 255)] {
            let mut bytes = archive.clone();
            bytes[offset] = value;
            let end = bytes.len() - 4;
            let checksum = crc(&bytes[..end]);
            bytes[end..].copy_from_slice(&checksum.to_le_bytes());
            assert!(Archive::open(&bytes, MAX_DATA).is_err());
        }
        let mut bytes = archive;
        bytes[35] ^= 1;
        let end = bytes.len() - 4;
        let checksum = crc(&bytes[..end]);
        bytes[end..].copy_from_slice(&checksum.to_le_bytes());
        assert!(Archive::open(&bytes, MAX_DATA).unwrap().verify().is_err());
    }
}

#[cfg(test)]
mod fuzz {
    use super::*;
    fn random(seed: &mut u64) -> usize {
        *seed ^= *seed << 13;
        *seed ^= *seed >> 7;
        *seed ^= *seed << 17;
        *seed as usize
    }

    #[test]
    fn decoder_mutation_budget() {
        let mut seed = 20261124;
        let periodic: Vec<_> = (0..8192).map(|i| (i / 3) as u8).collect();
        let options = Options {
            multiscale: false,
            ..Options::default()
        };
        let archive = encode(&[&periodic, &periodic, &[0x33; 4096]], options).unwrap();
        let base: Vec<_> = (0..384).map(|_| random(&mut seed) as u8).collect();
        let mut changed = base.clone();
        changed.splice(187..191, [13, 17, 23]);
        let edits = encode(&[&base, &changed], options).unwrap();
        assert_eq!(Archive::open(&edits, MAX_DATA).unwrap().stats().1[3], 1);
        let seeds = [archive, edits];
        for case in 0..20_000 {
            let mut bytes = seeds[case % seeds.len()].clone();
            let end = bytes.len() - 4;
            for _ in 0..1 + case % 5 {
                let position = 8 + random(&mut seed) % (end - 8);
                bytes[position] ^= (random(&mut seed) % 255 + 1) as u8;
            }
            let checksum = crc(&bytes[..end]);
            bytes[end..].copy_from_slice(&checksum.to_le_bytes());
            if let Ok(parsed) = Archive::open(&bytes, 32_000) {
                let _ = parsed.verify();
            }
            let size = random(&mut seed) % 256;
            let noise: Vec<_> = (0..size).map(|_| random(&mut seed) as u8).collect();
            let _ = entropy::decode(&noise, 4096);
            let _ = delta::decode(&periodic, &noise, 8192);
        }
    }
}
