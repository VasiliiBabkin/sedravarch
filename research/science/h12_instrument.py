# Applied after pinned H11 instrumentation.
import pathlib
p=pathlib.Path('src/statistical_codec.rs');s=p.read_text()
needle='    fn decode_correction(&mut self, correction: CodecCorrection) -> u32;'
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+'''
    fn h12_reference(&mut self, _len:u32, _dist:u32)->bool {
        self.decode_misprediction(CodecCorrection::ReferencePredictionWrong)
    }
'''))
p=pathlib.Path('src/token_predictor.rs');s=p.read_text()
needle='codec.decode_misprediction(CodecCorrection::ReferencePredictionWrong)'
assert s.count(needle)==1
p.write_text(s.replace(needle,'codec.h12_reference(r.len(),r.dist())'))
p=pathlib.Path('src/lib.rs')
with p.open('a') as f:f.write('\nmod h12_arithmetic;\npub use stream_processor::{h12_make,h12_restore};\n')
p=pathlib.Path('src/stream_processor.rs')
with p.open('a') as f:f.write("""
use crate::h12_arithmetic::{ArithEncoder,ArithDecoder,Model};
pub fn h12_make(params:&[u8],ev:&[(CodecCorrection,u32)],features:&[(u32,u32,bool)],mode:u8)->Result<Vec<u8>>{
 assert!(mode==1||mode==2);
 let mut r=ReconstructionData::read(params)?;
 let mut b=Vec::new();
 {
  let mut enc=PredictionEncoderCabac::new(VP8Writer::new(&mut b).unwrap());
  for &(c,v) in ev {if c!=CodecCorrection::ReferencePredictionWrong{enc.encode_correction(c,v);}}
  enc.finish();
 }
 r.corrections=b;
 let other=bitcode::encode(&r);
 let mut m=Model::new(mode);let mut a=ArithEncoder::new();
 for &(l,d,y) in features{a.put(y,m.p(l,d));m.update(l,d,y);}
 let bits=a.finish();
 let mut out=vec![mode];out.extend((other.len() as u32).to_le_bytes());out.extend(other);out.extend(bits);Ok(out)
}
struct H12Decoder<'a,D>{other:D,arith:ArithDecoder<'a>,model:Model}
impl<D:PredictionDecoder> PredictionDecoder for H12Decoder<'_,D>{
 fn decode_correction(&mut self,c:CodecCorrection)->u32{
  assert_ne!(c,CodecCorrection::ReferencePredictionWrong);self.other.decode_correction(c)
 }
 fn decode_verify_state(&mut self,m:&'static str,c:u64){self.other.decode_verify_state(m,c)}
 fn h12_reference(&mut self,l:u32,d:u32)->bool{
  let y=self.arith.get(self.model.p(l,d));self.model.update(l,d,y);y
 }
}
pub fn h12_restore(plain:&[u8],frame:&[u8])->Result<Vec<u8>>{
 if frame[0]==0{return recreate_whole_deflate_stream(plain,&frame[1..]);}
 let mode=frame[0];assert!(mode==1||mode==2);
 let n=u32::from_le_bytes(frame[1..5].try_into().unwrap()) as usize;
 let r=ReconstructionData::read(&frame[5..5+n])?;
 let other=PredictionDecoderCabac::new(VP8Reader::new(Cursor::new(r.corrections)).unwrap());
 let mut dec=H12Decoder{other,arith:ArithDecoder::new(&frame[5+n..]),model:Model::new(mode)};
 let p=PlainText::new_with_data(plain.to_vec());let mut input=PreflateInput::new(&p);
 let mut predictor=TokenPredictor::new(&r.parameters);let mut writer=DeflateWriter::new();
 recreate_blocks(&mut predictor,&mut dec,&mut writer,&mut input)?;
 assert_eq!(input.remaining(),0);writer.flush();Ok(writer.detach_output())
}
""")
with pathlib.Path('Cargo.toml').open('a') as f:f.write('\n[[bin]]\nname="h12-driver"\npath="h12_driver.rs"\n')
