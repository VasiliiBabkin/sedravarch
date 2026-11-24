//! Deterministic content-defined Gear chunking. Encoder policy only.
use std::io::{self,BufRead};
use crate::BLOCK;
pub const MIN:usize=32*1024;
const MASK:u64=(1<<15)-1;
#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub enum Mode { Adaptive, Fixed }
const fn table()->[u64;256] {
    let mut t=[0;256];let mut i=0;
    let mut state=0x5344415243480004u64;
    while i<256 {
        state=state.wrapping_add(0x9e3779b97f4a7c15);
        let mut z=state;
        z=(z^(z>>30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z=(z^(z>>27)).wrapping_mul(0x94d049bb133111eb);
        t[i]=z^(z>>31);i+=1;
    }
    t
}
const GEAR:[u64;256]=table();

/// Read one chunk, reusing caller storage. EOF is returned as an empty chunk.
/// Boundaries do not depend on the size of individual reads.
pub fn read_chunk(input:&mut impl BufRead, out:&mut Vec<u8>, mode:Mode)->io::Result<()> {
    out.clear();
    let mut hash=0u64;
    loop {
        let bytes=match input.fill_buf() {
            Ok(b)=>b,
            Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
            Err(e)=>return Err(e)
        };
        if bytes.is_empty(){return Ok(());}
        let cap=(BLOCK-out.len()).min(bytes.len());
        let mut used=cap;
        let mut cut=false;
        if mode==Mode::Adaptive {
            for (i,&b) in bytes[..cap].iter().enumerate() {
                hash=hash.wrapping_shl(1).wrapping_add(GEAR[b as usize]);
                if out.len()+i+1>=MIN && hash&MASK==0 {used=i+1;cut=true;break;}
            }
        }
        out.extend_from_slice(&bytes[..used]);
        input.consume(used);
        if cut || out.len()==BLOCK {return Ok(());}
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::BufReader;
    fn random(n:usize)->Vec<u8>{
        let mut x=123456u32;
        (0..n).map(|_|{x^=x<<13;x^=x>>17;x^=x<<5;x as u8}).collect()
    }
    fn split(d:&[u8],cap:usize,mode:Mode)->Vec<Vec<u8>>{
        let mut r=BufReader::with_capacity(cap,d);let mut v=Vec::new();let mut out=Vec::new();
        loop {read_chunk(&mut r,&mut out,mode).unwrap();if out.is_empty(){break;}v.push(out.clone());}
        v
    }
    #[test] fn bounds_and_reconstruction(){
        for n in [0,1,MIN-1,MIN,BLOCK,BLOCK+1,500000] {
            let d=random(n);
            for mode in [Mode::Adaptive,Mode::Fixed] {
                let s=split(&d,4096,mode);
                assert_eq!(s.concat(),d);
                for c in s.iter().take(s.len().saturating_sub(1)) {
                    assert!((MIN..=BLOCK).contains(&c.len()));
                    if mode==Mode::Fixed {assert_eq!(c.len(),BLOCK);}
                }
                assert!(s.iter().all(|c|c.len()<=BLOCK));
            }
        }
    }
    #[test] fn read_sizes_do_not_change_boundaries(){
        let d=random(600000);
        let expected=split(&d,65536,Mode::Adaptive);
        assert_eq!(expected,split(&d,1,Mode::Adaptive));
        assert_eq!(expected,split(&d,777,Mode::Adaptive));
    }
    #[test] fn insertion_resynchronizes(){
        let d=random(2*1024*1024);let mut edited=d.clone();
        edited.splice(100000..100000,vec![42;137]);
        let a=split(&d,8192,Mode::Adaptive);let b=split(&edited,8192,Mode::Adaptive);
        let common=a.iter().filter(|c|b.contains(c)).count();
        assert!(common>=a.len()/2,"shared {common}/{}",a.len());
        let fa=split(&d,8192,Mode::Fixed);let fb=split(&edited,8192,Mode::Fixed);
        assert_eq!(fa.iter().filter(|c|fb.contains(c)).count(),1);
    }
    #[test] fn variable_lengths(){
        let d=random(2*1024*1024);
        let a=split(&d,4096,Mode::Adaptive);
        assert!(a.iter().take(a.len()-1).any(|c|c.len()<BLOCK));
    }
}
