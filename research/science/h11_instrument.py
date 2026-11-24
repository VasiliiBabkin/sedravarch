import pathlib
p=pathlib.Path('src/cabac_codec.rs');s=p.read_text();needle='fn encode_correction(&mut self, c: CodecCorrection, value: u32) {'
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+'\n        crate::h11_record(c,value);'))
p=pathlib.Path('src/token_predictor.rs');s=p.read_text();needle='let predicted_token = self.predict_token(input);'
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+'''
            if let DeflateToken::Reference(r) = predicted_token {
                crate::h11_feature(r.len(),r.dist(),matches!(target_token,DeflateToken::Literal(_)));
            }
'''))
p=pathlib.Path('src/lib.rs')
with p.open('a') as f:f.write("""
static H11_ON: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(true);
static H11_EVENTS: std::sync::Mutex<Vec<(CodecCorrection,u32)>> = std::sync::Mutex::new(Vec::new());
static H11_FEATURES: std::sync::Mutex<Vec<(u32,u32,bool)>> = std::sync::Mutex::new(Vec::new());
fn h11_record(c:CodecCorrection,v:u32){
 if H11_ON.load(std::sync::atomic::Ordering::Relaxed){H11_EVENTS.lock().unwrap().push((c,v));}
}
fn h11_feature(l:u32,d:u32,y:bool){
 if H11_ON.load(std::sync::atomic::Ordering::Relaxed){H11_FEATURES.lock().unwrap().push((l,d,y));}
}
pub use stream_processor::{h11_parts,h11_restore};
""")
p=pathlib.Path('src/stream_processor.rs')
with p.open('a') as f:f.write("""
pub fn h11_parts(blob:&[u8])->Result<(Vec<u8>,usize,Vec<(CodecCorrection,u32)>,Vec<(u32,u32,bool)>,Vec<usize>)>{
 let mut r=ReconstructionData::read(blob)?;
 crate::H11_ON.store(false,std::sync::atomic::Ordering::Relaxed);
 let ev=std::mem::take(&mut *crate::H11_EVENTS.lock().unwrap());
 let features=std::mem::take(&mut *crate::H11_FEATURES.lock().unwrap());
 fn replay(ev:&[(CodecCorrection,u32)],only:Option<usize>)->Vec<u8>{
  let mut b=Vec::new();
  {
   let mut enc=PredictionEncoderCabac::new(VP8Writer::new(&mut b).unwrap());
   for &(c,v) in ev {if only.is_none()||only==Some(c as usize){enc.encode_correction(c,v);}}
   enc.finish();
  }
  b
 }
 assert_eq!(replay(&ev,None),r.corrections);
 let sizes=(0..17).map(|i|replay(&ev,Some(i)).len()).collect();
 let n=r.corrections.len();r.corrections.clear();
 Ok((bitcode::encode(&r),n,ev,features,sizes))
}
struct H11Lanes{lanes:Vec<Vec<u32>>,pos:[usize;17]}
impl PredictionDecoder for H11Lanes{
 fn decode_correction(&mut self,c:CodecCorrection)->u32{
  let i=c as usize;let v=self.lanes[i][self.pos[i]];self.pos[i]+=1;v
 }
 fn decode_verify_state(&mut self,_:&'static str,_:u64){}
}
pub fn h11_restore(plain:&[u8],params:&[u8],lanes:Vec<Vec<u32>>)->Result<Vec<u8>>{
 let r=ReconstructionData::read(params)?;assert!(r.corrections.is_empty());
 let p=PlainText::new_with_data(plain.to_vec());let mut input=PreflateInput::new(&p);
 let mut predictor=TokenPredictor::new(&r.parameters);let mut writer=DeflateWriter::new();
 let mut dec=H11Lanes{lanes,pos:[0;17]};
 recreate_blocks(&mut predictor,&mut dec,&mut writer,&mut input)?;
 assert_eq!(input.remaining(),0);
 for i in 0..17{assert_eq!(dec.pos[i],dec.lanes[i].len());}
 writer.flush();Ok(writer.detach_output())
}
""")
with pathlib.Path('Cargo.toml').open('a') as f:f.write('\n[[bin]]\nname="h11-driver"\npath="h11_driver.rs"\n')
