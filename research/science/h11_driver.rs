use std::{env,fs};
use preflate_rs::{PreflateConfig,preflate_whole_deflate_stream,recreate_whole_deflate_stream,h11_parts,h11_restore};
fn run()->Result<(),Box<dyn std::error::Error>>{
 let a:Vec<String>=env::args().collect();
 if a[1]=="trace"{
  assert_eq!(a.len(),4);let b=fs::read(&a[2])?;
  let c=PreflateConfig{max_chain_length:4096,plain_text_limit:262144,verify_compression:true};
  let (r,p)=preflate_whole_deflate_stream(&b,&c).map_err(|e|format!("{e:?}"))?;
  assert_eq!(r.compressed_size,b.len());assert_eq!(recreate_whole_deflate_stream(p.text(),&r.corrections).map_err(|e|format!("{e:?}"))?,b);
  let (params,n,events,features,sizes)=h11_parts(&r.corrections).map_err(|e|format!("{e:?}"))?;
  let d=std::path::Path::new(&a[3]);
  fs::write(d.join("params"),params)?;fs::write(d.join("plain"),p.text())?;
  let mut ev=Vec::new();for (c,v) in events{ev.push(c as u8);ev.extend(v.to_le_bytes());}fs::write(d.join("events"),ev)?;
  let mut feat=Vec::new();for (l,d,y) in features{feat.extend(l.to_le_bytes());feat.extend(d.to_le_bytes());feat.push(y as u8);}fs::write(d.join("features"),feat)?;
  println!("{} {}",r.corrections.len(),n);for x in sizes{print!("{x} ");}println!();
 }else{
  assert_eq!(a.len(),6);let p=fs::read(&a[2])?;let params=fs::read(&a[3])?;let b=fs::read(&a[4])?;
  let mut i=0;let mut lanes=Vec::new();
  for _ in 0..17{let n=u32::from_le_bytes(b[i..i+4].try_into()?) as usize;i+=4;assert!(n<=1000000);let mut v=Vec::with_capacity(n);for _ in 0..n{v.push(u32::from_le_bytes(b[i..i+4].try_into()?));i+=4;}lanes.push(v);}
  assert_eq!(i,b.len());fs::write(&a[5],h11_restore(&p,&params,lanes).map_err(|e|format!("{e:?}"))?)?;
 }
 Ok(())
}
fn main(){if let Err(e)=run(){eprintln!("{e}");std::process::exit(2)}}
