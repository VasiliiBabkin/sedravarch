use std::{env,fs};
use entropack_alp::{compress,decompress,Compressed};
fn main(){
 let a:Vec<String>=env::args().collect();assert_eq!(a.len(),4);
 let data=fs::read(&a[2]).unwrap();
 if a[1]=="encode"{
  assert_eq!(data.len()%8,0);
  let v:Vec<f64>=data.chunks_exact(8).map(|x|f64::from_le_bytes(x.try_into().unwrap())).collect();
  fs::write(&a[3],compress(&v).to_bytes()).unwrap();
 }else if a[1]=="decode"{
  let c=Compressed::from_bytes(&data).unwrap();
  let v=decompress(&c);let out:Vec<u8>=v.iter().flat_map(|x|x.to_le_bytes()).collect();
  fs::write(&a[3],out).unwrap();
 }else{panic!("mode")}
}