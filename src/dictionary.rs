//! Bounded hash-chain dictionary with long matches and one-step lazy parsing.
use crate::{invalid,literals,hash3};
use std::io;
const NONE:usize=usize::MAX;
const SEARCH:usize=32;
const MAX:usize=65535;
struct Chain { head:Vec<usize>, prev:Vec<usize> }
impl Chain {
    fn new(n:usize)->Self { Self {head:vec![NONE;65536],prev:vec![NONE;n]} }
    fn insert(&mut self,d:&[u8],i:usize) {
        if d.len()-i<3 {return;}
        let h=hash3(d,i);
        self.prev[i]=self.head[h]; self.head[h]=i;
    }
    #[cfg(test)]
    fn find(&self,d:&[u8],i:usize)->(usize,usize) {
        self.find_search(d,i,SEARCH)
    }
    fn find_search(&self,d:&[u8],i:usize,search:usize)->(usize,usize){
        let cap=(d.len()-i).min(MAX);
        if cap<4 {return (0,0);}
        let mut p=self.head[hash3(d,i)];
        let (mut len,mut dist)=(0,0);
        for _ in 0..search {
            if p==NONE || i-p>MAX {break;}
            if len<cap && d[p+len]==d[i+len] {
                let mut n=0;
                while n<cap && d[p+n]==d[i+n] {n+=1;}
                if n>len {len=n;dist=i-p;}
                if len==cap {break;}
            }
            p=self.prev[p];
        }
        (len,dist)
    }
}
fn match_cost(n:usize)->usize { if n<=129 {3}else{5} }
pub(crate) fn encode(d:&[u8])->Vec<u8> {encode_search(d,SEARCH,true)}
pub(crate) fn encode_search(d:&[u8],search:usize,lazy:bool)->Vec<u8>{
    let mut chain=Chain::new(d.len());
    let mut out=Vec::new();
    let (mut i,mut start)=(0,0);
    while i<d.len() {
        let (n,dist)=chain.find_search(d,i,search);
        chain.insert(d,i);
        if n>=4 {
            // Defer a match when the next match more than offsets the added literal.
            if lazy && n<d.len()-i {
                let (next,_)=chain.find_search(d,i+1,search);
                if next>=4 && next-match_cost(next)>n-match_cost(n)+1 {
                    i+=1; continue;
                }
            }
            literals(&mut out,&d[start..i]);
            if n<=129 {out.push(128|((n-3) as u8));}
            else {out.push(255);out.extend_from_slice(&(n as u16).to_le_bytes());}
            out.extend_from_slice(&(dist as u16).to_le_bytes());
            for j in i+1..i+n {chain.insert(d,j);}
            i+=n;start=i;
        } else {i+=1;}
    }
    literals(&mut out,&d[start..]); out
}
fn read16(p:&[u8],i:&mut usize)->io::Result<usize> {
    let b=p.get(*i..*i+2).ok_or_else(||invalid("truncated smart match"))?;
    *i+=2;Ok(u16::from_le_bytes([b[0],b[1]]) as usize)
}
pub(crate) fn decode(p:&[u8],n:usize)->io::Result<Vec<u8>> {
    let mut out=Vec::with_capacity(n);
    let mut i=0;
    while i<p.len() {
        let t=p[i];i+=1;
        if t<128 {
            let k=t as usize+1;
            if k>p.len()-i || k>n-out.len() {return Err(invalid("invalid smart literal"));}
            out.extend_from_slice(&p[i..i+k]);i+=k;
        } else {
            let k=if t==255 {
                let k=read16(p,&mut i)?;
                if k<130 {return Err(invalid("noncanonical long match"));}
                k
            } else {(t&127) as usize+3};
            let dist=read16(p,&mut i)?;
            if k>n-out.len() || dist==0 || dist>out.len() {return Err(invalid("invalid smart match"));}
            for _ in 0..k {out.push(out[out.len()-dist]);}
        }
    }
    if out.len()!=n {return Err(invalid("wrong smart decoded length"));}
    Ok(out)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn long_overlap() {
        let d=vec![42;65536]; let p=encode(&d);
        assert_eq!(p.len(),7);assert_eq!(p[2],255);
        assert_eq!(decode(&p,d.len()).unwrap(),d);
    }
    #[test] fn multiple_candidates() {
        let d=b"abcdefghijklmnop-abcQQQQ-abcdefghijklmnop";
        let mut c=Chain::new(d.len());
        let i=d.len()-16;
        for j in 0..i {c.insert(d,j);}
        assert_eq!(c.find(d,i),(16,i));
        assert_eq!(decode(&encode(d),d.len()).unwrap(),d);
    }
    #[test] fn boundary_lengths() {
        for n in [1,2,3,4,127,128,129,130,131,132,255,256,65535,65536] {
            let d=vec![7;n];assert_eq!(decode(&encode(&d),n).unwrap(),d);
        }
    }
    #[test] fn malformed() {
        for p in [&[255,0,0,1,0][..],&[255,130,0,1][..],&[128,0,0][..],&[127,1][..],&[0,1,255,130,0,1,0][..]] {
            assert!(decode(p,100).is_err());
        }
    }
    #[test] fn incompressible() {
        let mut x=123456u32;
        let d:Vec<u8>=(0..65536).map(|_|{x^=x<<13;x^=x>>17;x^=x<<5;x as u8}).collect();
        assert_eq!(decode(&encode(&d),d.len()).unwrap(),d);
    }
}
