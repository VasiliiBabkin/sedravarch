//! UI-independent desktop operations, also exercised by the core integration suite.
use sedravarch::{archive::{self,Archive,Entry,DEFAULT_LIMIT},Options};
use std::{fs::{self,File,OpenOptions},io::{self,BufReader,BufWriter},path::PathBuf};
#[derive(Clone)]
pub enum Task {
    Open(PathBuf), Create(PathBuf,Vec<PathBuf>,Options), Test(PathBuf),
    Extract(PathBuf,PathBuf), ExtractFile(PathBuf,String,PathBuf),
    Pack(PathBuf,PathBuf,Options), Unpack(PathBuf,PathBuf),
}
pub enum ResultData{Opened(PathBuf,Vec<Entry>,bool),Message(String),Created(PathBuf)}
fn stream(input:PathBuf,output:PathBuf,opts:Option<Options>)->io::Result<()>{
    let input=BufReader::new(File::open(input)?);
    let file=OpenOptions::new().write(true).create_new(true).open(&output)?;
    let result=if let Some(o)=opts{sedravarch::compress_config(input,BufWriter::new(file),o)}
    else{sedravarch::decompress(input,BufWriter::new(file),DEFAULT_LIMIT)};
    if result.is_err(){let _=fs::remove_file(output);}
    result
}
pub fn execute(task:Task)->io::Result<ResultData>{
    match task{
        Task::Open(p)=>{
            let multi=archive::is_multi(&p)?;
            if multi{let a=Archive::open(&p)?;Ok(ResultData::Opened(p,a.entries().to_vec(),true))}
            else{
                // Validate legacy stream before presenting it as an archive.
                sedravarch::decompress(BufReader::new(File::open(&p)?),io::sink(),DEFAULT_LIMIT)?;
                Ok(ResultData::Opened(p,Vec::new(),false))
            }
        }
        Task::Create(p,inputs,o)=>{archive::create_config(&p,&inputs,o)?;Ok(ResultData::Created(p))}
        Task::Test(p)=>{
            if archive::is_multi(&p)?{Archive::open(&p)?.test(DEFAULT_LIMIT)?;}
            else{sedravarch::decompress(BufReader::new(File::open(p)?),io::sink(),DEFAULT_LIMIT)?;}
            Ok(ResultData::Message("Проверка завершена. Ошибок не обнаружено.".into()))
        }
        Task::Extract(p,d)=>{Archive::open(&p)?.extract(&d,DEFAULT_LIMIT)?;Ok(ResultData::Message(format!("Распаковано: {}",d.display())))}
        Task::ExtractFile(p,n,d)=>{Archive::open(&p)?.extract_file(&n,&d,DEFAULT_LIMIT)?;Ok(ResultData::Message(format!("Извлечено: {}",d.display())))}
        Task::Pack(p,d,o)=>{stream(p,d.clone(),Some(o))?;Ok(ResultData::Created(d))}
        Task::Unpack(p,d)=>{stream(p,d.clone(),None)?;Ok(ResultData::Message(format!("Распаковано: {}",d.display())))}
    }
}
pub fn size(n:u64)->String{
    if n>=1024*1024 {format!("{:.2} МиБ",n as f64/1048576.)}
    else if n>=1024{format!("{:.1} КиБ",n as f64/1024.)}else{format!("{n} Б")}
}

#[cfg(test)]
mod tests{
    use super::*;
    struct Temp(PathBuf);
    impl Drop for Temp{fn drop(&mut self){let _=fs::remove_dir_all(&self.0);}}
    #[test] fn formatting(){assert_eq!(size(1024),"1.0 КиБ");assert_eq!(size(0),"0 Б");}
    #[test] fn operation_pipeline(){
        let root=Temp(std::env::temp_dir().join(format!("sedravarch-desktop-test-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos())));
        fs::create_dir(&root.0).unwrap();
        let input=root.0.join("data.txt");let arch=root.0.join("data.sda");let out=root.0.join("out");
        let bytes=b"SedravArch desktop";
        fs::write(&input,bytes).unwrap();
        assert!(matches!(execute(Task::Create(arch.clone(),vec![input.clone()],Options::default())).unwrap(),ResultData::Created(_)));
        let ResultData::Opened(_,entries,true)=execute(Task::Open(arch.clone())).unwrap() else{panic!("missing entries")};
        assert_eq!(entries.len(),1);
        execute(Task::Test(arch.clone())).unwrap();
        execute(Task::ExtractFile(arch.clone(),"data.txt".into(),out.clone())).unwrap();
        assert_eq!(fs::read(&out).unwrap(),bytes);
        assert!(execute(Task::ExtractFile(arch.clone(),"data.txt".into(),out)).is_err());
        let dir=root.0.join("restored");
        execute(Task::Extract(arch,dir.clone())).unwrap();
        assert_eq!(fs::read(dir.join("data.txt")).unwrap(),bytes);
        let single=root.0.join("single.sda");
        execute(Task::Pack(input,single.clone(),Options::default())).unwrap();
        assert!(matches!(execute(Task::Open(single.clone())).unwrap(),ResultData::Opened(_,_,false)));
        execute(Task::Test(single.clone())).unwrap();
        let dst=root.0.join("single-out");
        execute(Task::Unpack(single,dst.clone())).unwrap();
        assert_eq!(fs::read(dst).unwrap(),bytes);
    }
}
