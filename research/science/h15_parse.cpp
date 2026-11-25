// H15-H17: exact restricted DAG optimization under additive surrogate costs.
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>
using U=uint32_t;using I=int64_t;
struct Match{U len=0,dist=0;};
struct Command{U pos,len,dist;};
using Parse=std::vector<Command>;
using Graph=std::vector<std::array<Match,4>>;
struct Hist{std::array<U,256> n{};U total=0;void add(U x){assert(x<256);++n[x];++total;}};
struct Prices{std::array<I,256> lit,len,lo,hi;};
std::array<I,256> price(const Hist& h){std::array<I,256> p{};for(U x=0;x<256;++x)p[x]=std::llround(-256*std::log2((h.n[x]+0.5)/(h.total+128.0)));return p;}
U copies(U l,U d){U k=0;while(l){U t=std::min(l,d);l-=t;d+=t;++k;}return k;}
Graph graph(const std::vector<unsigned char>& b){
 U n=b.size();Graph g(n);std::unordered_map<U,std::array<U,4>> tab;tab.reserve(n);
 for(U i=0;i+4<=n;++i){
  U key;std::memcpy(&key,b.data()+i,4);auto [it,ins]=tab.try_emplace(key,std::array<U,4>{0,0,0,0});auto& a=it->second;
  for(U k=0;k<4&&a[k];++k){U q=a[k]-1,d=i-q;if(d>65535)break;U lo=4,hi=std::min<U>(258,n-i);
   while(lo<hi){U m=(lo+hi+1)/2;if(std::memcmp(b.data()+q,b.data()+i,m)==0)lo=m;else hi=m-1;}
   g[i][k]={lo,d};
  }
  for(int k=3;k>0;--k)a[k]=a[k-1];a[0]=i+1;
 }
 return g;
}
Parse greedy(const Graph&g){Parse p;for(U i=0;i<g.size();){Match m{};for(auto c:g[i])if(c.len>m.len)m=c;if(m.len){p.push_back({i,m.len,m.dist});i+=m.len;}else ++i;}return p;}
Prices empirical(const std::vector<unsigned char>&b,const Parse&p){
 Hist lit,len,lo,hi;U i=0;for(auto c:p){while(i<c.pos)lit.add(b[i++]);len.add(c.len-4);lo.add(c.dist&255);hi.add(c.dist>>8);i=c.pos+c.len;}while(i<b.size())lit.add(b[i++]);
 return {price(lit),price(len),price(lo),price(hi)};
}
I edge(const Prices&p,U l,U d,int lambda){return 2048+p.len[l-4]+p.lo[d&255]+p.hi[d>>8]+I(lambda)*256*copies(l,d);}
I score(const std::vector<unsigned char>&b,const Parse&pp,const Prices&p,int lambda){
 I s=0;U i=0;for(auto c:pp){assert(c.pos>=i&&c.pos+c.len<=b.size()&&c.dist<=c.pos&&c.dist>0);while(i<c.pos)s+=p.lit[b[i++]];assert(!std::memcmp(b.data()+c.pos,b.data()+c.pos-c.dist,c.len));s+=edge(p,c.len,c.dist,lambda);i=c.pos+c.len;}while(i<b.size())s+=p.lit[b[i++]];return s;
}
Parse opt(const std::vector<unsigned char>&b,const Graph&g,const Prices&p,int lambda){
 U n=b.size();std::vector<I> dp(n+1,0);std::vector<Match> next(n);
 for(U i=n;i-->0;){
  dp[i]=dp[i+1]+p.lit[b[i]];next[i]={1,0};
  for(auto c:g[i]){if(!c.len)break;I base=2048+p.lo[c.dist&255]+p.hi[c.dist>>8];U k=1,threshold=c.dist;
   for(U l=4;l<=c.len;++l){while(l>threshold){++k;threshold=threshold*2+c.dist;}I val=dp[i+l]+base+p.len[l-4]+I(lambda)*256*k;
    if(val<dp[i]){dp[i]=val;next[i]={l,c.dist};}
   }
  }
 }
 Parse out;for(U i=0;i<n;){auto m=next[i];assert(m.len);if(m.dist)out.push_back({i,m.len,m.dist});i+=m.len;}assert(score(b,out,p,lambda)==dp[0]);return out;
}
void put(std::ostream&o,uint64_t x,int n){for(int i=0;i<n;++i)o.put(char((x>>(i*8))&255));}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream in(argv[1],std::ios::binary);assert(in);std::vector<unsigned char>b((std::istreambuf_iterator<char>(in)),{});assert(b.size()<=262144);
 auto g=graph(b);auto G=greedy(g);Prices f;for(auto *a:{&f.lit,&f.len,&f.lo,&f.hi})a->fill(2048);auto F=opt(b,g,f,0);
 auto e=empirical(b,G);auto E=opt(b,g,e,0);auto W8=opt(b,g,e,8);auto W32=opt(b,g,e,32);
 assert(score(b,F,f,0)<=score(b,G,f,0));assert(score(b,E,e,0)<=score(b,G,e,0)&&score(b,E,e,0)<=score(b,F,e,0));
 assert(score(b,W8,e,8)<=score(b,E,e,8)&&score(b,W32,e,32)<=score(b,E,e,32));
 std::ofstream out(argv[2],std::ios::binary);assert(out);
 for(auto p:{&G,&F,&E,&W8,&W32}){put(out,p->size(),4);for(auto c:*p){put(out,c.pos,4);put(out,c.len,2);put(out,c.dist,2);}
  put(out,score(b,*p,f,0),8);put(out,score(b,*p,e,0),8);put(out,score(b,*p,e,8),8);put(out,score(b,*p,e,32),8);}
 assert(out);
}
