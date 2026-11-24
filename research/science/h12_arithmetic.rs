// H12: 32-bit arithmetic coding, KT quantization, no training outside stream.
const H:u64=1<<31;const Q1:u64=1<<30;const Q3:u64=3<<30;const MAX:u64=(1<<32)-1;
pub struct Model{mode:u8,constant:[u64;2],length:[[u64;2];6],joint:[[[u64;2];5];6]}
fn buckets(l:u32,d:u32)->(usize,usize){
 (([4,5,8,16,32].iter().filter(|&&x|l>=x).count()),([5,33,257,2049].iter().filter(|&&x|d>=x).count()))
}
fn kt(c:[u64;2])->u64{((32768*(2*c[1]+1))/(2*(c[0]+c[1])+2)).clamp(1,32767)}
impl Model{
 pub fn new(mode:u8)->Self{Self{mode,constant:[0;2],length:[[0;2];6],joint:[[[0;2];5];6]}}
 pub fn p(&self,l:u32,d:u32)->u64{let (i,j)=buckets(l,d);if self.mode==1{kt(self.length[i])}else{(kt(self.constant)+kt(self.joint[i][j]))/2}}
 pub fn update(&mut self,l:u32,d:u32,y:bool){let(i,j)=buckets(l,d);let k=usize::from(y);self.constant[k]+=1;self.length[i][k]+=1;self.joint[i][j][k]+=1;}
}
pub struct ArithEncoder{lo:u64,hi:u64,pending:usize,out:Vec<u8>,acc:u8,n:u8}
impl ArithEncoder{
 pub fn new()->Self{Self{lo:0,hi:MAX,pending:0,out:Vec::new(),acc:0,n:0}}
 fn bit(&mut self,b:bool){self.acc=(self.acc<<1)|u8::from(b);self.n+=1;if self.n==8{self.out.push(self.acc);self.acc=0;self.n=0;}}
 fn emit(&mut self,b:bool){self.bit(b);for _ in 0..self.pending{self.bit(!b);}self.pending=0;}
 pub fn put(&mut self,b:bool,p:u64){
  let cut=self.lo+(self.hi-self.lo+1)*(32768-p)/32768;
  if b{self.lo=cut;}else{self.hi=cut-1;}
  loop{
   if self.hi<H{self.emit(false);}
   else if self.lo>=H{self.emit(true);self.lo-=H;self.hi-=H;}
   else if self.lo>=Q1&&self.hi<Q3{self.pending+=1;self.lo-=Q1;self.hi-=Q1;}
   else{break;}
   self.lo*=2;self.hi=self.hi*2+1;
  }
 }
 pub fn finish(mut self)->Vec<u8>{self.pending+=1;self.emit(self.lo>=Q1);if self.n!=0{self.out.push(self.acc<<(8-self.n));}self.out}
}
pub struct ArithDecoder<'a>{data:&'a[u8],pos:usize,lo:u64,hi:u64,val:u64}
impl<'a> ArithDecoder<'a>{
 fn bit(&mut self)->u64{let v=self.data.get(self.pos/8).map_or(0,|b|(b>>(7-self.pos%8))&1);self.pos+=1;u64::from(v)}
 pub fn new(data:&'a[u8])->Self{let mut s=Self{data,pos:0,lo:0,hi:MAX,val:0};for _ in 0..32{s.val=s.val*2+s.bit();}s}
 pub fn get(&mut self,p:u64)->bool{
  let cut=self.lo+(self.hi-self.lo+1)*(32768-p)/32768;
  let b=self.val>=cut;if b{self.lo=cut;}else{self.hi=cut-1;}
  loop{
   if self.hi<H{}
   else if self.lo>=H{self.lo-=H;self.hi-=H;self.val-=H;}
   else if self.lo>=Q1&&self.hi<Q3{self.lo-=Q1;self.hi-=Q1;self.val-=Q1;}
   else{break;}
   self.lo*=2;self.hi=self.hi*2+1;self.val=self.val*2+self.bit();
  }
  b
 }
}
