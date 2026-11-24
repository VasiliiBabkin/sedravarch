use std::{env,fs};
use preflate_rs::{PreflateConfig,preflate_whole_deflate_stream,recreate_whole_deflate_stream,h10_counts};
fn run()->Result<(),Box<dyn std::error::Error>>{
 let a:Vec<String>=env::args().collect();assert_eq!(a.len(),5);
 if a[1]=="encode"{
  let b=fs::read(&a[2])?;
  let cfg=PreflateConfig{max_chain_length:4096,plain_text_limit:262144,verify_compression:true};
  let (r,p)=preflate_whole_deflate_stream(&b,&cfg).map_err(|e|format!("{e:?}"))?;
  assert_eq!(r.compressed_size,b.len());
  let restored=recreate_whole_deflate_stream(p.text(),&r.corrections).map_err(|e|format!("{e:?}"))?;
  assert_eq!(restored,b);
  fs::write(&a[3],p.text())?;fs::write(&a[4],&r.corrections)?;
  for (i,(n,z)) in h10_counts().iter().enumerate(){println!("{} {} {}",i,n,z);}
 }else if a[1]=="decode"{
  let p=fs::read(&a[2])?;let c=fs::read(&a[3])?;
  fs::write(&a[4],recreate_whole_deflate_stream(&p,&c).map_err(|e|format!("{e:?}"))?)?;
 }else{return Err("mode".into())}
 Ok(())
}
fn main(){if let Err(e)=run(){eprintln!("{e}");std::process::exit(2)}}
