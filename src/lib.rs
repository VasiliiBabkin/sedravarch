//! SedravArch experimental block codec, format v4.
mod graph;
mod entropy;
mod dictionary;
pub mod chunking;
use std::io::{self, BufReader, Read, Write};

pub const BLOCK: usize = 65_536;
const MAGIC: &[u8; 8] = b"SDARCH\x04\x00";
const V3_MAGIC: &[u8; 8] = b"SDARCH\x03\x00";
const V2_MAGIC: &[u8; 8] = b"SDARCH\x02\x00";
const LEGACY_MAGIC: &[u8; 8] = b"SDARCH\x01\x00";

fn invalid(msg: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, msg)
}
fn crc32(data: &[u8]) -> u32 {
    !crc_update(!0u32, data)
}
const fn crc_table() -> [u32;256] {
    let mut table = [0;256];
    let mut i=0;
    while i<256 {
        let mut v=i as u32;
        let mut j=0;
        while j<8 { v=(v>>1) ^ (0xedb88320 & 0u32.wrapping_sub(v&1)); j+=1; }
        table[i]=v; i+=1;
    }
    table
}
const CRC_TABLE: [u32;256] = crc_table();
fn crc_update(mut crc: u32, data: &[u8]) -> u32 {
    for &b in data { crc=(crc>>8)^CRC_TABLE[((crc^u32::from(b))&255) as usize]; }
    crc
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
    for (tag, payload) in [(0,data.to_vec()),(1,rle(data)),(2,lz(data)),(3,rle(&diff)),(4,lz(&diff))] {
        if let Some(encoded) = entropy::encode_below(&payload,best.1.len()) {
            best = (tag+5,encoded);
        }
        if payload.len() < best.1.len() { best = (tag,payload); }
    }
    for (tag,payload) in [(10,dictionary::encode(data)),(11,dictionary::encode(&diff))] {
        if let Some(encoded) = entropy::encode_below(&payload,best.1.len()) {
            best = (tag+2,encoded);
        }
        if payload.len() < best.1.len() { best = (tag,payload); }
    }
    best
}
fn decode(tag: u8, p: &[u8], n: usize) -> io::Result<Vec<u8>> {
    if (5..=9).contains(&tag) {
        let intermediate = entropy::decode(p, 2*n)?;
        return decode(tag-5, &intermediate, n);
    }
    if (12..=13).contains(&tag) {
        let intermediate = entropy::decode(p,2*n)?;
        return decode(tag-2,&intermediate,n);
    }
    if tag == 10 || tag == 11 {
        let mut out = dictionary::decode(p,n)?;
        if tag == 11 { let mut prev = 0u8; for b in &mut out { *b = b.wrapping_add(prev); prev = *b; } }
        return Ok(out);
    }
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
fn u64_read(r: &mut impl Read) -> io::Result<u64> {
    let mut b = [0;8]; r.read_exact(&mut b)?; Ok(u64::from_le_bytes(b))
}
/// Default content-defined chunking with bounded backward dependencies.
pub fn compress(input: impl Read, output: impl Write) -> io::Result<()> {
    compress_with_mode(input,output,chunking::Mode::Adaptive)
}
pub fn compress_with_mode(input: impl Read, output: impl Write, mode:chunking::Mode) -> io::Result<()> {
    compress_with_options(input,output,mode,true)
}
pub fn compress_with_options(input: impl Read, mut output: impl Write, mode:chunking::Mode, dependencies:bool) -> io::Result<()> {
    output.write_all(if dependencies { MAGIC } else { V3_MAGIC })?;
    let mut history=graph::History::new();
    let mut input=BufReader::with_capacity(BLOCK,input);
    let mut buf=Vec::with_capacity(BLOCK);
    let (mut total, mut blocks, mut stream_crc) = (0u64,0u64,!0u32);
    loop {
        chunking::read_chunk(&mut input,&mut buf,mode)?;
        let n=buf.len();
        if n == 0 { break; }
        total = total.checked_add(n as u64).ok_or_else(|| invalid("size overflow"))?;
        blocks += 1;
        stream_crc = crc_update(stream_crc,&buf[..n]);
        let crc=crc32(&buf);
        let (tag,payload,depth)=if dependencies { history.choose(&buf,crc) } else { let (tag,p)=encode(&buf); (tag,p,0) };
        if dependencies { history.push(&buf,crc,depth); }
        output.write_all(&[tag])?;
        output.write_all(&(n as u32).to_le_bytes())?;
        output.write_all(&(payload.len() as u32).to_le_bytes())?;
        output.write_all(&crc.to_le_bytes())?;
        output.write_all(&payload)?;
    }
    output.write_all(&[255])?;
    output.write_all(&total.to_le_bytes())?;
    output.write_all(&blocks.to_le_bytes())?;
    output.write_all(&(!stream_crc).to_le_bytes())?;
    output.flush()
}
pub fn decompress(mut input: impl Read, mut output: impl Write, max_output: u64) -> io::Result<()> {
    let mut magic = [0;8]; input.read_exact(&mut magic)?;
    let legacy = &magic == LEGACY_MAGIC;
    let max_tag = if legacy {4} else if &magic == V2_MAGIC {9} else if &magic == V3_MAGIC {13} else if &magic == MAGIC {15} else { return Err(invalid("bad archive header")); };
    let mut history=graph::History::new();
    let (mut total, mut blocks, mut stream_crc) = (0u64,0u64,!0u32);
    loop {
        let mut tag = [0]; input.read_exact(&mut tag)?;
        if tag[0] == 255 {
            if !legacy && (u64_read(&mut input)? != total || u64_read(&mut input)? != blocks || u32_read(&mut input)? != !stream_crc) {
                return Err(invalid("stream integrity mismatch"));
            }
            let mut extra = [0];
            if input.read(&mut extra)? != 0 { return Err(invalid("trailing data")); }
            return output.flush();
        }
        let n = u32_read(&mut input)? as usize;
        let p = u32_read(&mut input)? as usize;
        let crc = u32_read(&mut input)?;
        if tag[0] > max_tag || n == 0 || n > BLOCK || p == 0 || p > n || (tag[0] == 0 && p != n) {
            return Err(invalid("invalid block header"));
        }
        total = total.checked_add(n as u64).ok_or_else(|| invalid("size overflow"))?;
        if total > max_output { return Err(invalid("output limit exceeded")); }
        let mut payload = vec![0;p]; input.read_exact(&mut payload)?;
        let (decoded,depth)=if tag[0]>=14 { history.restore(tag[0],&payload,n)? } else { (decode(tag[0],&payload,n)?,0) };
        if crc32(&decoded) != crc { return Err(invalid("checksum mismatch")); }
        if max_tag>=15 { history.push(&decoded,crc,depth); }
        blocks += 1;
        stream_crc = crc_update(stream_crc,&decoded);
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
    #[test] fn legacy_archive() {
        let mut a = LEGACY_MAGIC.to_vec();
        let d = b"abc";
        a.push(0); a.extend(3u32.to_le_bytes()); a.extend(3u32.to_le_bytes());
        a.extend(crc32(d).to_le_bytes()); a.extend(d); a.push(255);
        let mut out = Vec::new();
        decompress(&a[..], &mut out, 3).unwrap(); assert_eq!(out,d);
    }
    #[test] fn removed_block() {
        let mut a=Vec::new(); compress_with_mode(&vec![42;BLOCK*2][..],&mut a,chunking::Mode::Fixed).unwrap();
        let p = u32::from_le_bytes(a[13..17].try_into().unwrap()) as usize;
        let mut broken = a[..8].to_vec(); broken.extend(&a[21+p..]);
        assert!(decompress(&broken[..],io::sink(),u64::MAX).is_err());
    }
    #[test] fn reordered_blocks() {
        let mut data = vec![42;BLOCK]; data.extend(vec![13;BLOCK]);
        let mut a=Vec::new(); compress_with_mode(&data[..],&mut a,chunking::Mode::Fixed).unwrap();
        let p = u32::from_le_bytes(a[13..17].try_into().unwrap()) as usize;
        let end = a.len()-21;
        let mut broken = a[..8].to_vec(); broken.extend(&a[21+p..end]); broken.extend(&a[8..21+p]); broken.extend(&a[end..]);
        assert!(decompress(&broken[..],io::sink(),u64::MAX).is_err());
    }
    #[test] fn entropy_selected() {
        let d = b"abracadabra".repeat(5000);
        let (tag,p) = encode(&d);
        assert!(tag >= 5);
        assert_eq!(decode(tag,&p,d.len()).unwrap(),d);
    }
    #[test] fn smart_selected() {
        let d = b"abracadabra".repeat(5000);
        let (tag,p) = encode(&d);
        assert!(tag >= 10); assert!(p.len()<64);
        assert_eq!(decode(tag,&p,d.len()).unwrap(),d);
    }
    #[test] fn v2_rejects_new_tags() {
        let mut a = packed(&b"abcde".repeat(10000));
        assert!(a[8]>=10); a[..8].copy_from_slice(V2_MAGIC);
        assert!(decompress(&a[..],io::sink(),u64::MAX).is_err());
    }
    #[test] fn crc_table_matches_bitwise() {
        let data:Vec<u8>=(0..65536).map(|i| (i*31) as u8).collect();
        let mut slow=!0u32;
        for &b in &data {slow^=u32::from(b);for _ in 0..8 {slow=(slow>>1)^(0xedb88320 & 0u32.wrapping_sub(slow&1));}}
        assert_eq!(crc32(&data),!slow);
        assert_eq!(crc_update(crc_update(!0,&data[..123]),&data[123..]),slow);
    }
    #[test] fn fixed_and_adaptive_roundtrip() {
        let d=b"SedravArch adaptive test".repeat(10000);
        for mode in [chunking::Mode::Adaptive,chunking::Mode::Fixed] {
            let mut a=Vec::new(); compress_with_mode(&d[..],&mut a,mode).unwrap();
            let mut out=Vec::new();decompress(&a[..],&mut out,d.len() as u64).unwrap(); assert_eq!(out,d);
        }
    }
    #[test] fn graph_roundtrip_and_v3_rejection() {
        let mut x=98765u32;
        let d:Vec<u8>=(0..BLOCK).map(|_|{x^=x<<13;x^=x>>17;x^=x<<5;x as u8}).collect();
        let mut edited=d.clone(); edited[100..110].fill(1);
        let mut data=d.clone();data.extend(&d);data.extend(&edited);
        let mut a=Vec::new();compress_with_mode(&data[..],&mut a,chunking::Mode::Fixed).unwrap();
        let p=u32::from_le_bytes(a[13..17].try_into().unwrap()) as usize;
        assert_eq!(a[21+p],14);assert_eq!(a[21+p+15],15);
        let mut restored=Vec::new();decompress(&a[..],&mut restored,data.len() as u64).unwrap();assert_eq!(restored,data);
        let mut broken=a.clone();broken[21+p+13]=0;broken[21+p+14]=0;
        assert!(decompress(&broken[..],io::sink(),u64::MAX).is_err());
        a[..8].copy_from_slice(V3_MAGIC);
        assert!(decompress(&a[..],io::sink(),u64::MAX).is_err());
    }
    #[test] fn independent_v3() {
        let d=vec![12;BLOCK*2];let mut a=Vec::new();
        compress_with_options(&d[..],&mut a,chunking::Mode::Fixed,false).unwrap();
        assert_eq!(&a[..8],V3_MAGIC);
        let mut out=Vec::new();decompress(&a[..],&mut out,d.len() as u64).unwrap();assert_eq!(out,d);
    }
    #[test] fn invalid_match() { assert!(decode(2,&[128,0,0],3).is_err()); }
    #[test] fn invalid_rle() { assert!(decode(1,&[0,1],1).is_err()); }
}
