//! Bounded dependency DAG over already reconstructed blocks.
use std::{collections::VecDeque,io};
use crate::{invalid,encode_preset,Preset};
pub const WINDOW:usize=128;
pub const MAX_DEPTH:u8=4;
const SAMPLES:usize=64;
const CANDIDATES:usize=3;
struct Entry { data:Vec<u8>, crc:u32, depth:u8 }
pub(crate) struct History { entries:VecDeque<Entry> }
impl History {
    pub(crate) fn new()->Self {Self{entries:VecDeque::new()}}
    pub(crate) fn push(&mut self,d:&[u8],crc:u32,depth:u8) {
        if self.entries.len()==WINDOW {self.entries.pop_front();}
        self.entries.push_back(Entry{data:d.to_vec(),crc,depth});
    }
    #[cfg(test)]
    pub(crate) fn choose(&self,d:&[u8],crc:u32)->(u8,Vec<u8>,u8){self.choose_with(d,crc,Preset::Deep,None)}
    pub(crate) fn choose_with(&self,d:&[u8],crc:u32,preset:Preset,precomputed:Option<(u8,Vec<u8>)>)->(u8,Vec<u8>,u8) {
        // A 2-byte exact reference is minimal for nontrivial blocks. Prefer shallow bases.
        if d.len()>2 {
            if let Some((i,e))=self.entries.iter().rev().enumerate()
                .filter(|(_,e)|e.depth<MAX_DEPTH && e.crc==crc && e.data==d)
                .min_by_key(|(i,e)|(e.depth,*i)) {
                return (14,((i+1) as u16).to_le_bytes().to_vec(),e.depth+1);
            }
        }
        let (tag,p)=precomputed.unwrap_or_else(||encode_preset(d,preset));
        let mut best=(tag,p,0);
        if best.1.len()<=6 || preset==Preset::Fast {return best;}
        let mut candidates=Vec::new();
        for (i,e) in self.entries.iter().rev().enumerate() {
            if e.depth>=MAX_DEPTH || e.data.len()!=d.len() {continue;}
            let score=(0..SAMPLES).filter(|&s|{let pos=s*d.len()/SAMPLES;e.data[pos]==d[pos]}).count();
            if score>=48 {candidates.push((std::cmp::Reverse(score),e.depth,i));}
        }
        candidates.sort_unstable();
        for (_,_,i) in candidates.into_iter().take(if preset==Preset::Extreme{8}else if preset==Preset::Balanced{1}else{CANDIDATES}) {
            let e=&self.entries[self.entries.len()-1-i];
            if let Some(p)=patch(&e.data,d,i+1,best.1.len()) {
                best=(15,p,e.depth+1);
            }
        }
        best
    }
    pub(crate) fn restore(&self,tag:u8,p:&[u8],n:usize)->io::Result<(Vec<u8>,u8)> {
        if p.len()<2 {return Err(invalid("short dependency"));}
        let dist=u16::from_le_bytes([p[0],p[1]]) as usize;
        if dist==0 || dist>self.entries.len() || dist>WINDOW {return Err(invalid("dependency outside history"));}
        let e=&self.entries[self.entries.len()-dist];
        if e.depth>=MAX_DEPTH || e.data.len()!=n {return Err(invalid("dependency depth or length mismatch"));}
        let mut out=e.data.clone();
        if tag==14 {
            if p.len()!=2 {return Err(invalid("invalid exact reference"));}
        } else if tag==15 {
            if p.len()<=2 {return Err(invalid("empty patch"));}
            let (mut i,mut end)=(2,0);
            while i<p.len() {
                if p.len()-i<4 {return Err(invalid("truncated patch header"));}
                let off=u16::from_le_bytes([p[i],p[i+1]]) as usize;
                let len=u16::from_le_bytes([p[i+2],p[i+3]]) as usize;
                i+=4;
                if len==0 || off<end || off>n || len>n-off || len>p.len()-i {return Err(invalid("invalid patch range"));}
                out[off..off+len].copy_from_slice(&p[i..i+len]);
                end=off+len;i+=len;
            }
        } else {return Err(invalid("unknown dependency"));}
        Ok((out,e.depth+1))
    }
}
// Replacement runs, merging gaps of at most four bytes to reduce overhead.
// Only same-length blocks are eligible. Return None as soon as the budget cannot win.
fn patch(base:&[u8],d:&[u8],dist:usize,limit:usize)->Option<Vec<u8>> {
    let mut p=(dist as u16).to_le_bytes().to_vec();
    let mut i=0;
    while i<d.len() {
        if base[i]==d[i] {i+=1;continue;}
        let start=i;let mut end=i+1;i+=1;
        while i<d.len() && i-start<65535 {
            if base[i]!=d[i] {end=i+1;}
            else if i-end>=4 {break;}
            i+=1;
        }
        let len=end-start;
        if p.len()+4+len>=limit {return None;}
        p.extend_from_slice(&(start as u16).to_le_bytes());
        p.extend_from_slice(&(len as u16).to_le_bytes());
        p.extend_from_slice(&d[start..end]);
        i=end;
    }
    if p.len()>2 {Some(p)} else {None}
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn patch_ranges() {
        let d=vec![1;65536];let mut e=d.clone();e[0]=3;e[3]=7;e[65535]=8;
        let p=patch(&d,&e,1,100).unwrap();
        let mut h=History::new();h.push(&d,1,0);
        assert_eq!(h.restore(15,&p,d.len()).unwrap(),(e,1));
    }
    #[test] fn limits() {
        let mut h=History::new();
        assert!(h.restore(14,&[1,0],4).is_err());
        h.push(b"abcd",0,MAX_DEPTH);
        assert!(h.restore(14,&[1,0],4).is_err());
        h.push(b"efgh",0,0);
        for p in [&[0,0][..],&[3,0][..],&[1,0,0][..]] {assert!(h.restore(14,p,4).is_err());}
        assert!(h.restore(14,&[1,0],3).is_err());
        for p in [&[1,0][..],&[1,0,0,0,0,0][..],&[1,0,3,0,2,0,1,2][..],&[1,0,0,0,2,0,1,2,1,0,1,0,3][..]] {
            assert!(h.restore(15,p,4).is_err());
        }
    }
    #[test] fn eviction() {
        let mut h=History::new();h.push(b"first",0,0);
        for _ in 0..WINDOW {h.push(b"later",1,0);}
        assert_eq!(h.entries.len(),WINDOW);
        assert!(h.restore(14,&[129,0],5).is_err());
        assert_eq!(h.restore(14,&[128,0],5).unwrap().0,b"later");
    }
    #[test] fn collision_is_not_identity() {
        let mut h=History::new();h.push(b"aaaaaaaa",1,0);
        assert_ne!(h.choose(b"bbbbbbbb",1).0,14);
    }
    #[test] fn shallow_reference() {
        let mut h=History::new();h.push(b"abcdefgh",1,0);h.push(b"abcdefgh",1,3);
        assert_eq!(h.choose(b"abcdefgh",1),(14,vec![2,0],1));
    }
}
