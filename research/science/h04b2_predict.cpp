// H04b.2: log-loss only, causal sequential predictors.
#include "h04_native.cpp"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <array>
#include <iterator>
#include <chrono>
using Byte=uint8_t;
static W hash64(W x){x=(x^(x>>30))*0xbf58476d1ce4e5b9ull;x=(x^(x>>27))*0x94d049bb133111ebull;return x^(x>>31);}
struct Counts {uint16_t z=0,o=0;};
double baseline(const std::vector<Byte>& data){
 Model m(4);double loss=0;
 for(auto x:data)for(int j=7;j>=0;--j){U b=(x>>j)&1,p=m.predict();loss-=std::log2(double(b?p:Q-p)/Q);m.update(b);}
 return loss;
}
struct Result {double loss=0;W covered=0,correct=0;};
Result predict(const std::vector<Byte>& data,int mode){
 constexpr U N=1<<18;const W masks[]={0,255,65535,0xffffffffull,~0ull};
 int count=mode==1?5:6;
 std::vector<Counts> tabs[5];for(auto &t:tabs)t.resize(N);
 std::vector<int> last(mode==1?0:N,-1);
 U w[8][6];for(auto &row:w)for(int i=0;i<count;++i)row[i]=65536/count;
 W history=0;int prevmatch=-1;bool prevgood=false;Result res;
 for(size_t pos=0;pos<data.size();++pos){
  int match=-1;
  if(mode!=1&&pos>=4){
   U key=U(hash64(history&0xffffffffull))&(N-1);
   int cand=last[key];last[key]=int(pos);
   if(prevgood&&prevmatch>=0)match=prevmatch+1;
   else if(cand>=4&&size_t(cand)<pos&&std::equal(data.begin()+cand-4,data.begin()+cand,data.begin()+pos-4))match=cand;
   if(match>=0&&size_t(match)>=pos)throw std::runtime_error("noncausal match");
  }
  Byte expected=match>=0?data[match]:0;bool live=match>=0;U prefix=1;
  for(int phase=0;phase<8;++phase){
   U p[6],keys[5];W sum=0,den=0;auto &weights=w[mode==3?phase:0];
   for(int j=0;j<5;++j){
    U key=U(hash64((history&masks[j])*257ull+prefix))&(N-1);keys[j]=key;
    auto c=tabs[j][key];p[j]=std::clamp((2u*c.o+1)*Q/(2u*(c.z+c.o)+2),1u,Q-1);
   }
   U b=(data[pos]>>(7-phase))&1,guess=(expected>>(7-phase))&1;
   if(mode!=1){p[5]=live?(guess?31744u:1024u):16384u;if(live){++res.covered;res.correct+=b==guess;}}
   for(int j=0;j<count;++j){sum+=W(weights[j])*p[j];den+=weights[j];}
   U mixed=std::clamp(U(sum/den),1u,Q-1);
   res.loss-=std::log2(double(b?mixed:Q-mixed)/Q);
   W v[6],total=0;
   for(int j=0;j<count;++j){v[j]=W(weights[j])*(b?p[j]:Q-p[j]);total+=v[j];}
   for(int j=0;j<count;++j)weights[j]=64+U(W(65536-64*count)*v[j]/total);
   for(int j=0;j<5;++j){auto &c=tabs[j][keys[j]];if(b)++c.o;else ++c.z;if(c.o+c.z>=4096){c.o/=2;c.z/=2;}}
   prefix=2*prefix+b;if(live&&b!=guess)live=false;
  }
  prevmatch=match;prevgood=live;history=(history<<8)|data[pos];
 }
 return res;
}
int main(int argc,char**argv){
 if(argc!=2)return 2;std::ifstream in(argv[1],std::ios::binary);if(!in)return 3;
 std::vector<Byte> data((std::istreambuf_iterator<char>(in)),{});if(data.size()>65536)return 4;
 std::cout<<std::setprecision(17);
 for(int mode=0;mode<4;++mode){
  auto start=std::chrono::steady_clock::now();Result r;
  if(mode==0)r.loss=baseline(data);else r=predict(data,mode);
  auto secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  std::cout<<mode<<" "<<r.loss<<" "<<r.covered<<" "<<r.correct<<" "<<secs<<"\n";
 }
}
