// H04 native arithmetic kernel. Identical integer model and format to the Python reference.
#include <cstdint>
#include <vector>
#include <cmath>
#include <algorithm>
#include <cstddef>
using U=uint32_t;using W=uint64_t;
constexpr U Q=32768, H=0x80000000u, T=0x40000000u, R=0xc0000000u;
struct Model {
  U history=0,prefix=1; int count; U masks[4],key[4],p[4],w[4]={16384,16384,16384,16384};
  std::vector<U> z[4],o[4];
  explicit Model(int idx):count(idx==4?4:1){
    const U ms[]={0,255,65535,0xffffffffu};
    for(int i=0;i<count;++i){masks[i]=ms[idx==4?i:idx];z[i].resize(65536);o[i].resize(65536);}
  }
  U predict(){
    W sum=0,den=0;
    for(int i=0;i<count;++i){
      U k=(((history&masks[i])*257u+prefix)*2654435761u)>>16; key[i]=k;
      U a=z[i][k],b=o[i][k];p[i]=std::clamp((2*b+1)*Q/(2*(a+b)+2),1u,Q-1);
      sum+=W(w[i])*p[i];den+=w[i];
    }
    return count==1?p[0]:std::clamp(U(sum/den),1u,Q-1);
  }
  void update(U b){
    for(int i=0;i<count;++i){
      auto &a=z[i][key[i]],&c=o[i][key[i]];if(b)++c;else++a;
      if(a+c>=4096){a/=2;c/=2;}
    }
    if(count==4){W v[4],s=0;for(int i=0;i<4;++i){v[i]=W(w[i])*(b?p[i]:Q-p[i]);s+=v[i];}
      for(int i=0;i<4;++i)w[i]=64+U(65280ull*v[i]/s);}
    prefix=prefix*2+b;if(prefix>=256){history=(history<<8)|(prefix-256);prefix=1;}
  }
};
extern "C" int h04_encode(const uint8_t* data,size_t n,int idx,uint8_t* out,size_t cap,double* loss){
 if(n>8192||idx<0||idx>4)return -1;
 Model m(idx);U lo=0,hi=0xffffffffu;size_t pending=0,k=0;U acc=0,nb=0;bool ok=true;*loss=0;
 auto emit=[&](U b){acc=acc*2+b;if(++nb==8){if(k>=cap){ok=false;return;}out[k++]=uint8_t(acc);acc=nb=0;}};
 auto flush=[&](U b){emit(b);while(pending){emit(1-b);--pending;}};
 for(size_t i=0;i<n;++i)for(int j=7;j>=0;--j){
   U b=(data[i]>>j)&1,p=m.predict();*loss-=std::log2(double(b?p:Q-p)/Q);
   U cut=U(W(lo)+(W(hi)-lo+1)*(Q-p)/Q-1);if(b)lo=cut+1;else hi=cut;
   for(;;){if(hi<H)flush(0);else if(lo>=H){flush(1);lo-=H;hi-=H;}else if(lo>=T&&hi<R){++pending;lo-=T;hi-=T;}else break;
     lo<<=1;hi=(hi<<1)|1u;}
   if(!ok)return -2;m.update(b);
 }
 ++pending;flush(lo<T?0:1);if(!ok)return -2;
 if(nb){if(k>=cap)return -2;out[k++]=uint8_t(acc<<(8-nb));}return int(k);
}
extern "C" int h04_decode(const uint8_t* data,size_t size,int idx,uint8_t* out,size_t n){
 if(n>8192||idx<0||idx>4)return -1;
 size_t pos=0;auto read=[&](){U b=pos<size*8?((data[pos>>3]>>(7-(pos&7)))&1u):0u;++pos;return b;};
 U lo=0,hi=0xffffffffu,val=0;for(int i=0;i<32;++i)val=(val<<1)|read();
 Model m(idx);
 for(size_t i=0;i<n;++i){U byte=0;for(int j=0;j<8;++j){
   U p=m.predict(),cut=U(W(lo)+(W(hi)-lo+1)*(Q-p)/Q-1),b=val>cut;
   if(b)lo=cut+1;else hi=cut;
   for(;;){if(hi<H){}else if(lo>=H){lo-=H;hi-=H;val-=H;}else if(lo>=T&&hi<R){lo-=T;hi-=T;val-=T;}else break;
     lo<<=1;hi=(hi<<1)|1u;val=(val<<1)|read();}
   byte=2*byte+b;m.update(b);
 }out[i]=uint8_t(byte);}return 0;
}
