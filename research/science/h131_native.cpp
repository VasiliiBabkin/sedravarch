// H13.1 native one-shot codec harness, trusted bounded input only.
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <fstream>
#include <vector>
#include <stdexcept>
#include <ctime>
#include <string>
#include <algorithm>
extern "C" {
int LZ4_compressBound(int);
int LZ4_compress_fast(const char*,char*,int,int,int);
int LZ4_compress_HC(const char*,char*,int,int,int);
int LZ4_decompress_safe(const char*,char*,int,int);
size_t ZSTD_compressBound(size_t);
size_t ZSTD_compress(void*,size_t,const void*,size_t,int);
size_t ZSTD_decompress(void*,size_t,const void*,size_t);
unsigned ZSTD_isError(size_t);
struct libdeflate_compressor;struct libdeflate_decompressor;
libdeflate_compressor* libdeflate_alloc_compressor(int);
void libdeflate_free_compressor(libdeflate_compressor*);
size_t libdeflate_gzip_compress_bound(libdeflate_compressor*,size_t);
size_t libdeflate_gzip_compress(libdeflate_compressor*,const void*,size_t,void*,size_t);
libdeflate_decompressor* libdeflate_alloc_decompressor();
void libdeflate_free_decompressor(libdeflate_decompressor*);
int libdeflate_gzip_decompress(libdeflate_decompressor*,const void*,size_t,void*,size_t,size_t*);
unsigned long crc32(unsigned long,const unsigned char*,unsigned int);
}
using B=std::vector<unsigned char>;
static void require(bool x){if(!x)throw std::runtime_error("check failed");}
static uint64_t ns(clockid_t c){timespec t{};require(clock_gettime(c,&t)==0);return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;}
static B read(const char*p){std::ifstream f(p,std::ios::binary|std::ios::ate);require(bool(f));auto n=f.tellg();require(n>=0&&n<=128*1024*1024);B b(static_cast<size_t>(n));f.seekg(0);f.read(reinterpret_cast<char*>(b.data()),n);require(bool(f));return b;}
static void write(const char*p,const B&b,size_t n){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),n);require(bool(f));}
static void put(B&b,size_t i,uint32_t v){for(int j=0;j<4;++j)b[i+j]=v>>(8*j);}
static uint32_t get(const B&b,size_t i){uint32_t v=0;for(int j=0;j<4;++j)v|=uint32_t(b[i+j])<<(8*j);return v;}
int main(int argc,char**argv){try{
 require(argc>=4);std::string mode=argv[1];auto in=read(argv[2]);B out;size_t written=0;uint64_t w=0,c=0;
 if(mode=="enc"){
  require(argc==6);std::string codec=argv[4];int level=std::stoi(argv[5]);size_t n=in.size();require(n>0&&n<=32*1024*1024);
  unsigned tag=codec=="lz4"||codec=="lz4hc"?0:codec=="zstd"?1:codec=="deflate"?2:255;require(tag<3);
  libdeflate_compressor* z=tag==2?libdeflate_alloc_compressor(level):nullptr;if(tag==2)require(z);
  size_t cap=tag==0?size_t(LZ4_compressBound(int(n))):tag==1?ZSTD_compressBound(n):libdeflate_gzip_compress_bound(z,n);
  out.resize(cap+13);
  uint64_t t=ns(CLOCK_MONOTONIC),u=ns(CLOCK_PROCESS_CPUTIME_ID);
  std::memcpy(out.data(),"H131",4);out[4]=tag;put(out,5,n);put(out,9,crc32(0,in.data(),n));
  size_t m=0;
  if(tag==0){int k=codec=="lz4"?LZ4_compress_fast(reinterpret_cast<const char*>(in.data()),reinterpret_cast<char*>(out.data()+13),n,cap,level):LZ4_compress_HC(reinterpret_cast<const char*>(in.data()),reinterpret_cast<char*>(out.data()+13),n,cap,level);require(k>0);m=k;}
  else if(tag==1){m=ZSTD_compress(out.data()+13,cap,in.data(),n,level);require(!ZSTD_isError(m));}
  else{m=libdeflate_gzip_compress(z,in.data(),n,out.data()+13,cap);require(m>0);}
  c=ns(CLOCK_PROCESS_CPUTIME_ID)-u;w=ns(CLOCK_MONOTONIC)-t;written=13+m;
  if(z)libdeflate_free_compressor(z);
 }else{
  require(mode=="dec"&&argc==4&&in.size()>=13&&std::memcmp(in.data(),"H131",4)==0);
  unsigned tag=in[4];size_t n=get(in,5),cap=in.size()-13;require(tag<3&&n<=32*1024*1024);
  out.resize(n);auto z=tag==2?libdeflate_alloc_decompressor():nullptr;if(tag==2)require(z);
  uint64_t t=ns(CLOCK_MONOTONIC),u=ns(CLOCK_PROCESS_CPUTIME_ID);
  if(tag==0){int m=LZ4_decompress_safe(reinterpret_cast<const char*>(in.data()+13),reinterpret_cast<char*>(out.data()),cap,n);require(m>=0&&size_t(m)==n);}
  else if(tag==1){auto m=ZSTD_decompress(out.data(),n,in.data()+13,cap);require(!ZSTD_isError(m)&&m==n);}
  else{size_t m=0;require(libdeflate_gzip_decompress(z,in.data()+13,cap,out.data(),n,&m)==0&&m==n);}
  require(crc32(0,out.data(),n)==get(in,9));c=ns(CLOCK_PROCESS_CPUTIME_ID)-u;w=ns(CLOCK_MONOTONIC)-t;written=n;
  if(z)libdeflate_free_decompressor(z);
 }
 write(argv[3],out,written);std::cout<<w<<" "<<c<<"\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}}
