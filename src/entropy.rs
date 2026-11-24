//! Deterministic byte Huffman coder, MSB-first, explicit bounded tree.
use std::{cmp::Reverse, collections::BinaryHeap, io};
use crate::invalid;

#[derive(Clone, Copy)]
enum Node { Leaf(u8), Pair(usize,usize) }
struct Bits { bytes: Vec<u8>, n: usize }
impl Bits {
    fn new() -> Self { Self { bytes:Vec::new(), n:0 } }
    fn put(&mut self, b:bool) {
        if self.n%8==0 { self.bytes.push(0); }
        if b { *self.bytes.last_mut().unwrap() |= 1 << (7-self.n%8); }
        self.n+=1;
    }
}
struct Reader<'a> { bytes:&'a [u8], n:usize }
impl Reader<'_> {
    fn bit(&mut self) -> io::Result<bool> {
        let b = *self.bytes.get(self.n/8).ok_or_else(|| invalid("truncated Huffman bits"))?;
        let v = (b >> (7-self.n%8)) & 1 != 0;
        self.n+=1; Ok(v)
    }
    fn byte(&mut self) -> io::Result<u8> {
        let mut b=0;
        for _ in 0..8 { b=(b<<1)|u8::from(self.bit()?); }
        Ok(b)
    }
}
fn tree_write(nodes:&[Node], i:usize, bits:&mut Bits, path:&mut Vec<bool>, codes:&mut [Vec<bool>]) {
    match nodes[i] {
        Node::Leaf(b) => {
            bits.put(true);
            for j in (0..8).rev() { bits.put(b&(1<<j)!=0); }
            codes[b as usize]=path.clone();
        }
        Node::Pair(l,r) => {
            bits.put(false);
            path.push(false); tree_write(nodes,l,bits,path,codes); path.pop();
            path.push(true); tree_write(nodes,r,bits,path,codes); path.pop();
        }
    }
}
pub(crate) fn encode_below(data:&[u8], limit:usize) -> Option<Vec<u8>> {
    assert!(!data.is_empty());
    // Four length bytes plus at least nine tree bits: no payload below six bytes.
    if limit<=6 {return None;}
    let mut freq=[0u32;256];
    for &b in data { freq[b as usize]+=1; }
    let mut heap=BinaryHeap::new();
    let mut nodes=Vec::new();
    for (b,&f) in freq.iter().enumerate() {
        if f!=0 { heap.push(Reverse((f,nodes.len()))); nodes.push(Node::Leaf(b as u8)); }
    }
    while heap.len()>1 {
        let Reverse((a,l))=heap.pop().unwrap();
        let Reverse((b,r))=heap.pop().unwrap();
        heap.push(Reverse((a+b,nodes.len())));
        nodes.push(Node::Pair(l,r));
    }
    let Reverse((_,root))=heap.pop().unwrap();
    let mut bits=Bits::new();
    let mut codes=vec![Vec::new();256];
    tree_write(&nodes,root,&mut bits,&mut Vec::new(),&mut codes);
    let bit_count = bits.n + freq.iter().zip(&codes).map(|(&f,c)| f as usize*c.len()).sum::<usize>();
    if 4+(bit_count+7)/8 >= limit { return None; }
    for &b in data { for &bit in &codes[b as usize] { bits.put(bit); } }
    let mut out=(data.len() as u32).to_le_bytes().to_vec();
    out.extend(bits.bytes); Some(out)
}
fn tree_read(r:&mut Reader<'_>, nodes:&mut Vec<Node>, seen:&mut [bool;256], depth:usize, budget:&mut usize) -> io::Result<usize> {
    if depth>255 || *budget==0 { return Err(invalid("Huffman tree limit")); }
    *budget-=1;
    let node=if r.bit()? {
        let b=r.byte()?;
        if seen[b as usize] { return Err(invalid("duplicate Huffman symbol")); }
        seen[b as usize]=true; Node::Leaf(b)
    } else {
        let l=tree_read(r,nodes,seen,depth+1,budget)?;
        let rr=tree_read(r,nodes,seen,depth+1,budget)?;
        Node::Pair(l,rr)
    };
    let i=nodes.len(); nodes.push(node); Ok(i)
}
pub(crate) fn decode(data:&[u8], max:usize) -> io::Result<Vec<u8>> {
    if data.len()<5 { return Err(invalid("short Huffman payload")); }
    let n=u32::from_le_bytes(data[..4].try_into().unwrap()) as usize;
    if n==0 || n>max { return Err(invalid("Huffman output limit")); }
    let mut r=Reader {bytes:&data[4..],n:0};
    let mut nodes=Vec::new();
    let root=tree_read(&mut r,&mut nodes,&mut [false;256],0,&mut 511)?;
    let mut out=Vec::with_capacity(n);
    for _ in 0..n {
        let mut i=root;
        loop { match nodes[i] {
            Node::Leaf(b) => { out.push(b); break; }
            Node::Pair(l,rr) => { i=if r.bit()? {rr} else {l}; }
        }}
    }
    if (r.n+7)/8!=r.bytes.len() { return Err(invalid("trailing Huffman bytes")); }
    while r.n%8!=0 { if r.bit()? { return Err(invalid("nonzero Huffman padding")); } }
    Ok(out)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn encode(data:&[u8]) -> Vec<u8> { encode_below(data,usize::MAX).unwrap() }
    #[test] fn estimate() {
        let d = b"abracadabra".repeat(1000);
        let a = encode(&d);
        assert!(encode_below(&d,a.len()).is_none());
        assert_eq!(encode_below(&d,a.len()+1).unwrap(),a);
    }
    #[test] fn roundtrip() {
        for d in [vec![8;65536], b"abcabcabc".repeat(500), (0..=255).collect()] {
            let a=encode(&d); assert_eq!(decode(&a,d.len()).unwrap(),d);
            assert_eq!(encode(&d),a);
        }
    }
    #[test] fn malformed() {
        let d=b"abcabc".repeat(100); let a=encode(&d);
        for i in 0..a.len() { assert!(decode(&a[..i],d.len()).is_err()); }
        assert!(decode(&a,d.len()-1).is_err());
        let mut bad=a.clone(); bad.push(0); assert!(decode(&bad,d.len()).is_err());
        let mut single=encode(&[3;8]); *single.last_mut().unwrap()|=1;
        assert!(decode(&single,8).is_err());
    }
}
