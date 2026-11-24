//! SedravArch experimental block codec, format v1.
use std::io::{self, Read, Write};

pub const BLOCK: usize = 65_536;
const MAGIC: &[u8; 8] = b"SDARCH\x01\x00";

fn invalid(msg: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, msg)
}
fn crc32(data: &[u8]) -> u32 {
    let mut crc = !0u32;
    for &b in data {
        crc ^= u32::from(b);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}
fn rle(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < data.len() {
        let mut n = 1;
        while n < 255 && i + n < data.len() && data[i+n] == data[i] { n += 1; }
        out.extend([n as u8, data[i]]);
        i += n;
    }
    out
}
fn hash3(d: &[u8], i: usize) -> usize {
    ((u32::from(d[i]) * 251 + u32::from(d[i+1])) * 251 + u32::from(d[i+2])) as usize & 65535
}
fn literals(out: &mut Vec<u8>, data: &[u8]) {
    for chunk in data.chunks(128) {
        out.push((chunk.len()-1) as u8);
        out.extend_from_slice(chunk);
    }
}
fn lz(d: &[u8]) -> Vec<u8> {
    let mut last = vec![usize::MAX; 65536];
    let mut out = Vec::new();
    let (mut i, mut start) = (0, 0);
    while i + 3 <= d.len() {
        let h = hash3(d, i);
        let p = last[h];
        last[h] = i;
        let mut n = 0;
        if p != usize::MAX && i-p <= 65535 {
            while n < 130 && i+n < d.len() && d[p+n] == d[i+n] { n += 1; }
        }
        if n >= 4 {
            literals(&mut out, &d[start..i]);
            out.push(128 | ((n-3) as u8));
            out.extend_from_slice(&((i-p) as u16).to_le_bytes());
            for j in i+1..i+n {
                if j+3 <= d.len() { last[hash3(d,j)] = j; }
            }
            i += n;
            start = i;
        } else { i += 1; }
    }
    literals(&mut out, &d[start..]);
    out
}
fn delta(data: &[u8]) -> Vec<u8> {
    let mut prev = 0u8;
    data.iter().map(|&b| { let v = b.wrapping_sub(prev); prev = b; v }).collect()
}
fn encode(data: &[u8]) -> (u8, Vec<u8>) {
    let mut best = (0, data.to_vec());
    let diff = delta(data);
    for (tag, payload) in [(1,rle(data)),(2,lz(data)),(3,rle(&diff)),(4,lz(&diff))] {
        if payload.len() < best.1.len() { best = (tag,payload); }
    }
    best
}
fn decode(tag: u8, p: &[u8], n: usize) -> io::Result<Vec<u8>> {
    let mut out = Vec::with_capacity(n);
    match tag {
        0 => out.extend_from_slice(p),
        1 | 3 => {
            if p.len()%2 != 0 { return Err(invalid("odd RLE payload")); }
            for pair in p.chunks_exact(2) {
                let k = pair[0] as usize;
                if k == 0 || k > n-out.len() { return Err(invalid("invalid RLE length")); }
                out.resize(out.len()+k,pair[1]);
            }
        }
        2 | 4 => {
            let mut i = 0;
            while i < p.len() {
                let t = p[i]; i += 1;
                if t < 128 {
                    let k = t as usize + 1;
                    if k > p.len()-i || k > n-out.len() { return Err(invalid("invalid literal")); }
                    out.extend_from_slice(&p[i..i+k]); i += k;
                } else {
                    let k = (t & 127) as usize + 3;
                    if p.len()-i < 2 || k > n-out.len() { return Err(invalid("invalid match length")); }
                    let dist = u16::from_le_bytes([p[i],p[i+1]]) as usize; i += 2;
                    if dist == 0 || dist > out.len() { return Err(invalid("invalid match distance")); }
                    for _ in 0..k { out.push(out[out.len()-dist]); }
                }
            }
        }
        _ => return Err(invalid("unknown codec")),
    }
    if out.len() != n { return Err(invalid("wrong decoded length")); }
    if tag == 3 || tag == 4 {
        let mut prev = 0u8;
        for b in &mut out { *b = b.wrapping_add(prev); prev = *b; }
    }
    Ok(out)
}
fn u32_read(r: &mut impl Read) -> io::Result<u32> {
    let mut b = [0;4]; r.read_exact(&mut b)?; Ok(u32::from_le_bytes(b))
}
pub fn compress(mut input: impl Read, mut output: impl Write) -> io::Result<()> {
    output.write_all(MAGIC)?;
    let mut buf = vec![0;BLOCK];
    loop {
        let mut n = 0;
        while n < BLOCK {
            match input.read(&mut buf[n..]) {
                Ok(0) => break,
                Ok(k) => n += k,
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e),
            }
        }
        if n == 0 { break; }
        let (tag, payload) = encode(&buf[..n]);
        output.write_all(&[tag])?;
        output.write_all(&(n as u32).to_le_bytes())?;
        output.write_all(&(payload.len() as u32).to_le_bytes())?;
        output.write_all(&crc32(&buf[..n]).to_le_bytes())?;
        output.write_all(&payload)?;
    }
    output.write_all(&[255])?;
    output.flush()
}
pub fn decompress(mut input: impl Read, mut output: impl Write, max_output: u64) -> io::Result<()> {
    let mut magic = [0;8]; input.read_exact(&mut magic)?;
    if &magic != MAGIC { return Err(invalid("bad archive header")); }
    let mut total = 0u64;
    loop {
        let mut tag = [0]; input.read_exact(&mut tag)?;
        if tag[0] == 255 {
            let mut extra = [0];
            if input.read(&mut extra)? != 0 { return Err(invalid("trailing data")); }
            return output.flush();
        }
        let n = u32_read(&mut input)? as usize;
        let p = u32_read(&mut input)? as usize;
        let crc = u32_read(&mut input)?;
        if tag[0] > 4 || n == 0 || n > BLOCK || p == 0 || p > n || (tag[0] == 0 && p != n) {
            return Err(invalid("invalid block header"));
        }
        total = total.checked_add(n as u64).ok_or_else(|| invalid("size overflow"))?;
        if total > max_output { return Err(invalid("output limit exceeded")); }
        let mut payload = vec![0;p]; input.read_exact(&mut payload)?;
        let decoded = decode(tag[0],&payload,n)?;
        if crc32(&decoded) != crc { return Err(invalid("checksum mismatch")); }
        output.write_all(&decoded)?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packed(d: &[u8]) -> Vec<u8> { let mut a = Vec::new(); compress(d,&mut a).unwrap(); a }
    fn roundtrip(d: &[u8]) {
        let a = packed(d); let mut out = Vec::new();
        decompress(&a[..],&mut out,d.len() as u64).unwrap();
        assert_eq!(out,d);
    }
    #[test] fn empty() { roundtrip(b""); }
    #[test] fn small() { for n in 0..300 { roundtrip(&vec![42;n]); } }
    #[test] fn periodic() { roundtrip(&b"Sedrava Rust archive ".repeat(10000)); }
    #[test] fn ramp() { roundtrip(&(0..200000).map(|i| i as u8).collect::<Vec<_>>()); }
    #[test] fn random() {
        let mut x = 123456u32;
        let d: Vec<u8> = (0..200000).map(|_| { x ^= x<<13; x ^= x>>17; x ^= x<<5; x as u8 }).collect();
        roundtrip(&d);
    }
    #[test] fn crc_reference() { assert_eq!(crc32(b"123456789"),0xcbf43926); }
    #[test] fn truncated() {
        let a = packed(b"abcdefabcdefabcdef");
        for i in 0..a.len() { assert!(decompress(&a[..i],io::sink(),100).is_err()); }
    }
    #[test] fn corrupt() {
        let mut a = packed(b"abcdef"); a[21] ^= 1;
        assert!(decompress(&a[..],io::sink(),100).is_err());
    }
    #[test] fn limit() { assert!(decompress(&packed(b"abc")[..],io::sink(),2).is_err()); }
    #[test] fn trailing() { let mut a = packed(b""); a.push(0); assert!(decompress(&a[..],io::sink(),0).is_err()); }
    #[test] fn invalid_match() { assert!(decode(2,&[128,0,0],3).is_err()); }
    #[test] fn invalid_rle() { assert!(decode(1,&[0,1],1).is_err()); }
}
