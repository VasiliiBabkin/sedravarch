//! Indexed multi-file container. Each regular file has its own bounded codec stream.
use std::{collections::BTreeMap,fs::{self,File,OpenOptions},io::{self,BufReader,BufWriter,Read,Seek,SeekFrom,Write},path::{Path,PathBuf},time::UNIX_EPOCH};
use crate::{invalid,crc32};
const MAGIC:&[u8;8]=b"SDAMULT\x01";
const END:&[u8;8]=b"SDAINDEX";
const FOOTER:u64=20;
const MAX_INDEX:usize=16*1024*1024;
const MAX_ENTRIES:usize=100_000;
const MAX_PATH:usize=4096;
const MAX_DEPTH:usize=64;
pub const DEFAULT_LIMIT:u64=8*1024*1024*1024;
#[derive(Debug,Clone,PartialEq,Eq)]
pub struct Entry {pub path:String,pub directory:bool,pub size:u64,pub modified:Option<u64>,offset:u64,packed:u64}
fn fail(msg:&str)->io::Error{invalid(msg)}
fn segment(s:&str)->io::Result<()>{
    if s.is_empty() || s=="." || s==".." || s.len()>255 || s.ends_with('.') || s.ends_with(' ')
       || s.chars().any(|c| c.is_control() || "\\/:*?\"<>|".contains(c)) {
        return Err(fail("unsafe archive path component"));
    }
    let stem=s.split('.').next().unwrap().trim_end_matches(' ').to_ascii_uppercase();
    if matches!(stem.as_str(),"CON"|"PRN"|"AUX"|"NUL"|"CONIN$"|"CONOUT$")
       || (["COM","LPT"].iter().any(|p|stem.strip_prefix(p).is_some_and(|v|matches!(v,"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9"|"¹"|"²"|"³")))) {
        return Err(fail("reserved archive name"));
    }
    Ok(())
}
fn validate_path(s:&str)->io::Result<()>{
    if s.len()>MAX_PATH || s.split('/').count()>MAX_DEPTH {return Err(fail("archive path limit"));}
    for part in s.split('/') {segment(part)?;}
    Ok(())
}
fn portable_key(s:&str)->String{s.to_lowercase()}
fn validate(entries:&[Entry],index_start:u64)->io::Result<()>{
    if entries.len()>MAX_ENTRIES {return Err(fail("entry count limit"));}
    let mut names=BTreeMap::new();
    let mut end=8u64;
    for e in entries{
        validate_path(&e.path)?;
        let key=portable_key(&e.path);
        if names.contains_key(&key){return Err(fail("duplicate or case-colliding entry"));}
        if let Some((parent,_))=e.path.rsplit_once('/'){
            match names.get(&portable_key(parent)){
                Some((true,original)) if *original==parent=>{},
                _=>return Err(fail("missing or invalid parent directory")),
            }
        }
        names.insert(key,(e.directory,e.path.as_str()));
        if e.directory {
            if e.size!=0 || e.offset!=0 || e.packed!=0{return Err(fail("invalid directory metadata"));}
        }else{
            if e.offset!=end || e.packed<29 {return Err(fail("invalid file extent"));}
            end=end.checked_add(e.packed).ok_or_else(||fail("file extent overflow"))?;
            if end>index_start{return Err(fail("file extent beyond data"));}
        }
    }
    if end!=index_start{return Err(fail("unindexed data"));}
    Ok(())
}
fn encode_index(entries:&[Entry])->io::Result<Vec<u8>>{
    let mut b=(entries.len() as u32).to_le_bytes().to_vec();
    for e in entries{
        if b.len()+37+e.path.len()>MAX_INDEX{return Err(fail("index size limit"));}
        b.push(u8::from(e.directory));
        b.extend((e.path.len() as u32).to_le_bytes());b.extend(e.path.as_bytes());
        b.extend(e.size.to_le_bytes());b.extend(e.modified.unwrap_or(u64::MAX).to_le_bytes());
        b.extend(e.offset.to_le_bytes());b.extend(e.packed.to_le_bytes());
    }
    Ok(b)
}
fn take<'a>(b:&mut &'a [u8],n:usize)->io::Result<&'a [u8]>{
    if n>b.len(){return Err(fail("truncated index"));}
    let (a,rest)=b.split_at(n);*b=rest;Ok(a)
}
fn read32(b:&mut &[u8])->io::Result<u32>{Ok(u32::from_le_bytes(take(b,4)?.try_into().unwrap()))}
fn read64(b:&mut &[u8])->io::Result<u64>{Ok(u64::from_le_bytes(take(b,8)?.try_into().unwrap()))}
fn decode_index(mut b:&[u8],start:u64)->io::Result<Vec<Entry>>{
    let count=read32(&mut b)? as usize;
    if count>MAX_ENTRIES || count>b.len()/38{return Err(fail("index entry count limit"));}
    let mut entries=Vec::with_capacity(count);
    for _ in 0..count{
        let directory=match take(&mut b,1)?[0]{0=>false,1=>true,_=>return Err(fail("invalid entry kind"))};
        let n=read32(&mut b)? as usize;
        if n==0 || n>MAX_PATH{return Err(fail("invalid path length"));}
        let path=std::str::from_utf8(take(&mut b,n)?).map_err(|_|fail("non-UTF8 archive name"))?.to_owned();
        let size=read64(&mut b)?;let m=read64(&mut b)?;
        let offset=read64(&mut b)?;let packed=read64(&mut b)?;
        entries.push(Entry{path,directory,size,modified:if m==u64::MAX{None}else{Some(m)},offset,packed});
    }
    if !b.is_empty(){return Err(fail("trailing index data"));}
    validate(&entries,start)?;Ok(entries)
}
pub struct Archive {file:File,entries:Vec<Entry>}
impl Archive {
    pub fn open(path:&Path)->io::Result<Self>{
        let mut file=File::open(path)?;
        let end=file.metadata()?.len();
        if end<8+FOOTER+4{return Err(fail("short multi-file archive"));}
        let mut magic=[0;8];file.read_exact(&mut magic)?;
        if &magic!=MAGIC{return Err(fail("not a multi-file archive"));}
        file.seek(SeekFrom::End(-(FOOTER as i64)))?;
        let mut footer=[0;20];file.read_exact(&mut footer)?;
        if &footer[..8]!=END{return Err(fail("missing archive index"));}
        let n=u64::from_le_bytes(footer[8..16].try_into().unwrap());
        if n<4 || n>MAX_INDEX as u64 || n>end-8-FOOTER{return Err(fail("invalid index length"));}
        let start=end-FOOTER-n;
        file.seek(SeekFrom::Start(start))?;
        let mut index=vec![0;n as usize];file.read_exact(&mut index)?;
        if crc32(&index)!=u32::from_le_bytes(footer[16..20].try_into().unwrap()){return Err(fail("index checksum mismatch"));}
        let entries=decode_index(&index,start)?;
        Ok(Self{file,entries})
    }
    pub fn entries(&self)->&[Entry]{&self.entries}
    fn budget(&self,max:u64)->io::Result<()>{
        let mut sum=0u64;
        for e in &self.entries{
            sum=sum.checked_add(e.size).ok_or_else(||fail("archive size overflow"))?;
            if sum>max{return Err(fail("archive output limit exceeded"));}
        }Ok(())
    }
    fn decode_file(&mut self,e:&Entry,output:impl Write,max:u64)->io::Result<()>{
        if e.directory || e.size>max{return Err(fail("file output limit or directory"));}
        self.file.seek(SeekFrom::Start(e.offset))?;
        let mut input=(&mut self.file).take(e.packed);
        let mut counter=Counter{inner:output,n:0};
        crate::decompress(BufReader::new(&mut input),&mut counter,e.size)?;
        if counter.n!=e.size || input.limit()!=0{return Err(fail("file length mismatch"));}
        Ok(())
    }
    pub fn test(&mut self,max:u64)->io::Result<()>{
        self.budget(max)?;
        for e in self.entries.clone(){if !e.directory{self.decode_file(&e,io::sink(),max)?;}}
        Ok(())
    }
    pub fn extract_file(&mut self,name:&str,out:&Path,max:u64)->io::Result<()>{
        let e=self.entries.iter().find(|e|e.path==name && !e.directory).cloned().ok_or_else(||fail("file not found"))?;
        if e.size>max{return Err(fail("file output limit exceeded"));}
        let f=OpenOptions::new().write(true).create_new(true).open(out)?;
        let result=self.decode_file(&e,BufWriter::new(f),max);
        if result.is_err(){let _=fs::remove_file(out);}
        result
    }
    pub fn extract(&mut self,root:&Path,max:u64)->io::Result<()>{
        self.budget(max)?;
        // A new root prevents archived names from targeting preexisting symlinks/files.
        // Caller must choose a trusted parent and avoid concurrent modifications.
        let mut builder=fs::DirBuilder::new();
        #[cfg(unix)] {use std::os::unix::fs::DirBuilderExt;builder.mode(0o700);}
        builder.create(root)?;
        let result=(||{
            for e in self.entries.clone(){
                let path=root.join(&e.path);
                // Verify the ancestor chain again before each operation.
                let mut parent=path.parent();
                while let Some(p)=parent{
                    let m=fs::symlink_metadata(p)?;
                    if !m.is_dir() || m.file_type().is_symlink(){return Err(fail("unsafe extraction ancestor"));}
                    if p==root{break;}
                    parent=p.parent();
                }
                if e.directory {fs::create_dir(&path)?;}else{
                    let f=OpenOptions::new().write(true).create_new(true).open(&path)?;
                    self.decode_file(&e,BufWriter::new(f),max)?;
                }
            }Ok(())
        })();
        if result.is_err(){let _=fs::remove_dir_all(root);}
        result
    }
}
struct Counter<W>{inner:W,n:u64}
impl<W:Write> Write for Counter<W>{
    fn write(&mut self,b:&[u8])->io::Result<usize>{
        let n=self.inner.write(b)?;self.n+=n as u64;Ok(n)
    }
    fn flush(&mut self)->io::Result<()>{self.inner.flush()}
}
pub fn is_multi(path:&Path)->io::Result<bool>{
    let mut f=File::open(path)?;let mut b=[0;8];f.read_exact(&mut b)?;Ok(&b==MAGIC)
}
struct Source{entry:Entry,path:PathBuf}
fn collect(path:&Path,name:String,out:&mut Vec<Source>,index_bytes:&mut usize)->io::Result<()>{
    validate_path(&name)?;
    if out.len()>=MAX_ENTRIES{return Err(fail("entry count limit"));}
    *index_bytes=index_bytes.checked_add(37+name.len()).ok_or_else(||fail("index overflow"))?;
    if *index_bytes>MAX_INDEX{return Err(fail("index size limit"));}
    let m=fs::symlink_metadata(path)?;
    if m.file_type().is_symlink() || !(m.is_dir() || m.is_file()){return Err(fail("only regular files and directories are supported"));}
    let modified=m.modified().ok().and_then(|v|v.duration_since(UNIX_EPOCH).ok()).map(|v|v.as_secs());
    out.push(Source{entry:Entry{path:name.clone(),directory:m.is_dir(),size:if m.is_dir(){0}else{m.len()},modified,offset:0,packed:0},path:path.to_owned()});
    if m.is_dir(){
        let mut children=Vec::new();
        for child in fs::read_dir(path)?{
            if children.len()>=MAX_ENTRIES{return Err(fail("directory entry limit"));}
            children.push(child?);
        }
        children.sort_by_key(|e|e.file_name());
        for child in children{
            let s=child.file_name().into_string().map_err(|_|fail("non-UTF8 source name"))?;
            segment(&s)?;collect(&child.path(),format!("{name}/{s}"),out,index_bytes)?;
        }
    }Ok(())
}
pub fn create(output:&Path,inputs:&[PathBuf])->io::Result<()>{
    if inputs.is_empty(){return Err(fail("at least one input required"));}
    let parent=output.parent().filter(|p|!p.as_os_str().is_empty()).unwrap_or(Path::new(".")).canonicalize()?;
    let filename=output.file_name().ok_or_else(||fail("invalid output name"))?;
    let target=parent.join(filename);
    let mut sources=Vec::new();let mut index_bytes=4;
    for input in inputs{
        // Reject symlink roots; inputs are trusted and must remain stable during creation.
        let m=fs::symlink_metadata(input)?;
        if m.file_type().is_symlink(){return Err(fail("symlink input"));}
        let canonical=input.canonicalize()?;
        if canonical==target || (m.is_dir() && target.starts_with(&canonical)){return Err(fail("archive output inside input"));}
        let name=canonical.file_name().and_then(|v|v.to_str()).ok_or_else(||fail("invalid input basename"))?;
        collect(&canonical,name.to_owned(),&mut sources,&mut index_bytes)?;
    }
    let mut seen=BTreeMap::new();
    for s in &sources{if seen.insert(portable_key(&s.entry.path),()).is_some(){return Err(fail("duplicate input name"));}}
    let mut file=OpenOptions::new().write(true).create_new(true).open(&target)?;
    let result=(||{
        file.write_all(MAGIC)?;
        for s in &mut sources{
            if s.entry.directory{continue;}
            if !fs::symlink_metadata(&s.path)?.is_file(){return Err(fail("source type changed"));}
            let mut input=File::open(&s.path)?;
            if input.metadata()?.len()!=s.entry.size{return Err(fail("source size changed"));}
            s.entry.offset=file.stream_position()?;
            let mut limited=(&mut input).take(s.entry.size);
            crate::compress(&mut limited,BufWriter::new(&mut file))?;
            if limited.limit()!=0 || input.read(&mut [0])?!=0{return Err(fail("source size changed"));}
            s.entry.packed=file.stream_position()?.checked_sub(s.entry.offset).ok_or_else(||fail("extent overflow"))?;
        }
        let start=file.stream_position()?;
        let entries:Vec<_>=sources.into_iter().map(|s|s.entry).collect();
        validate(&entries,start)?;
        let index=encode_index(&entries)?;
        file.write_all(&index)?;file.write_all(END)?;file.write_all(&(index.len() as u64).to_le_bytes())?;
        file.write_all(&crc32(&index).to_le_bytes())?;file.flush()
    })();
    drop(file);
    if result.is_err(){let _=fs::remove_file(&target);}
    result
}
#[cfg(test)]
mod tests{
    use super::*;
    fn ent(path:&str,directory:bool)->Entry{Entry{path:path.into(),directory,size:0,modified:None,offset:if directory{0}else{8},packed:if directory{0}else{29}}}
    #[test] fn bad_paths(){
        for s in ["","/etc/passwd","../x","x/../y","a//b","C:/x","a\\b","a:stream","CON","nul.txt","COM¹.txt","x.","x ","a\nb"] {assert!(validate_path(s).is_err(),"{s}");}
        assert!(validate_path("папка/текст.txt").is_ok());
    }
    #[test] fn invalid_index(){
        assert!(validate(&[ent("a/b",false)],37).is_err());
        assert!(validate(&[ent("a",true),ent("A",true)],8).is_err());
        assert!(validate(&[ent("a",false),ent("a/b",true)],37).is_err());
        assert!(validate(&[ent("a",true),ent("A/b",false)],37).is_err());
        assert!(validate(&[ent("a",false)],38).is_err());
        let mut e=ent("a",false);e.packed=u64::MAX;assert!(validate(&[e],37).is_err());
    }
    #[test] fn index_roundtrip(){
        let entries=[ent("a",true),ent("a/б",false)];
        let b=encode_index(&entries).unwrap();
        assert_eq!(decode_index(&b,37).unwrap(),entries);
        for i in 0..b.len(){assert!(decode_index(&b[..i],37).is_err());}
    }
}
