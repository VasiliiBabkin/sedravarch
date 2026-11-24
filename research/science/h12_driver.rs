use std::{env,fs,path::Path,time::Instant};
use preflate_rs::{PreflateConfig,preflate_whole_deflate_stream,recreate_whole_deflate_stream,h11_parts,h12_make,h12_restore};
fn run()->Result<(),Box<dyn std::error::Error>>{
 let a:Vec<String>=env::args().collect();
 if a[1]=="encode"{
  assert_eq!(a.len(),4);let b=fs::read(&a[2])?;let d=Path::new(&a[3]);
  let cfg=PreflateConfig{max_chain_length:4096,plain_text_limit:2097152,verify_compression:true};
  let t=Instant::now();let (r,p)=preflate_whole_deflate_stream(&b,&cfg).map_err(|e|format!("{e:?}"))?;
  assert_eq!(r.compressed_size,b.len());assert_eq!(recreate_whole_deflate_stream(p.text(),&r.corrections).map_err(|e|format!("{e:?}"))?,b);
  let base_ns=t.elapsed().as_nanos();let (params,_,ev,features,_)=h11_parts(&r.corrections).map_err(|e|format!("{e:?}"))?;
  let labels:Vec<bool>=ev.iter().filter(|(c,_)|(*c as usize)==16).map(|(_,v)|*v!=0).collect();
  assert!(labels.iter().copied().eq(features.iter().map(|x|x.2)));
  fs::write(d.join("plain"),p.text())?;
  let mut base=vec![0];base.extend(r.corrections);
  fs::write(d.join("corr0"),base)?;let mut ns=vec![base_ns];
  for mode in [1,2]{let t=Instant::now();let blob=h12_make(&params,&ev,&features,mode).map_err(|e|format!("{e:?}"))?;ns.push(t.elapsed().as_nanos());fs::write(d.join(format!("corr{mode}")),blob)?;}
  println!("{} {} {} {}",features.len(),ns[0],ns[1],ns[2]);
 }else{
  assert_eq!(a.len(),5);let p=fs::read(&a[2])?;let c=fs::read(&a[3])?;
  fs::write(&a[4],h12_restore(&p,&c).map_err(|e|format!("{e:?}"))?)?;
 }
 Ok(())
}
fn main(){if let Err(e)=run(){eprintln!("{e}");std::process::exit(2)}}
