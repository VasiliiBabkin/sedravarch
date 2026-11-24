#![cfg_attr(target_os="windows", windows_subsystem="windows")]
use eframe::egui;
use sedravarch::{archive::{self,Archive,Entry,DEFAULT_LIMIT},Options,Preset};
use std::{fs::{self,File,OpenOptions},io::{self,BufReader,BufWriter},path::PathBuf,sync::mpsc::{self,Receiver},time::Duration};

#[derive(Clone)]
enum Task {
    Open(PathBuf), Create(PathBuf,Vec<PathBuf>,Options), Test(PathBuf),
    Extract(PathBuf,PathBuf), ExtractFile(PathBuf,String,PathBuf),
    Pack(PathBuf,PathBuf,Options), Unpack(PathBuf,PathBuf),
}
enum ResultData{Opened(PathBuf,Vec<Entry>,bool),Message(String),Created(PathBuf)}
fn stream(input:PathBuf,output:PathBuf,opts:Option<Options>)->io::Result<()>{
    let input=BufReader::new(File::open(input)?);
    let file=OpenOptions::new().write(true).create_new(true).open(&output)?;
    let result=if let Some(o)=opts{sedravarch::compress_config(input,BufWriter::new(file),o)}
    else{sedravarch::decompress(input,BufWriter::new(file),DEFAULT_LIMIT)};
    if result.is_err(){let _=fs::remove_file(output);}
    result
}
fn execute(task:Task)->io::Result<ResultData>{
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
fn size(n:u64)->String{
    if n>=1024*1024 {format!("{:.2} МиБ",n as f64/1048576.)}
    else if n>=1024{format!("{:.1} КиБ",n as f64/1024.)}else{format!("{n} Б")}
}
fn open_dialog()->rfd::FileDialog{rfd::FileDialog::new().add_filter("SedravArch", &["sda"])}
#[derive(Default,PartialEq)]
enum Page{#[default] Browse,Create}
struct Desktop{
    page:Page, path:Option<PathBuf>, entries:Vec<Entry>, multi:bool, selected:Option<String>,
    filter:String, sources:Vec<PathBuf>, profile:Preset, threads:usize, single_stream:bool,
    status:String, error:bool, job:Option<Receiver<Result<ResultData,String>>>,
}
impl Default for Desktop{
    fn default()->Self{Self{page:Page::Browse,path:None,entries:vec![],multi:false,selected:None,filter:String::new(),sources:vec![],
        profile:Preset::Balanced,threads:std::thread::available_parallelism().map(|n|n.get().min(4)).unwrap_or(1),
        single_stream:false,status:"Откройте архив или создайте новый.".into(),error:false,job:None}}
}
impl Desktop{
    fn start(&mut self,task:Task,ctx:&egui::Context){
        if self.job.is_some(){return;}
        let (tx,rx)=mpsc::channel();let ctx=ctx.clone();
        self.error=false;self.status="Выполняется операция…".into();self.job=Some(rx);
        std::thread::spawn(move||{
            let result=std::panic::catch_unwind(||execute(task)).map_err(|_|"Внутренняя ошибка движка".into())
                .and_then(|r|r.map_err(|e|e.to_string()));
            let _=tx.send(result);ctx.request_repaint();
        });
    }
    fn poll(&mut self,ctx:&egui::Context){
        let Some(rx)=&self.job else{return;};
        let data=match rx.try_recv(){
            Ok(r)=>r,Err(mpsc::TryRecvError::Empty)=>{ctx.request_repaint_after(Duration::from_millis(150));return;},
            Err(mpsc::TryRecvError::Disconnected)=>Err("Рабочий поток завершился неожиданно".into()),
        };
        self.job=None;
        match data{
            Ok(ResultData::Opened(p,entries,multi))=>{
                self.status=format!("Открыт архив: {}",p.display());
                self.path=Some(p);self.entries=entries;self.multi=multi;self.selected=None;self.filter.clear();self.page=Page::Browse;
            }
            Ok(ResultData::Created(p))=>{self.start(Task::Open(p),ctx);}
            Ok(ResultData::Message(s))=>self.status=s,
            Err(e)=>{self.error=true;self.status=e;}
        }
    }
    fn opts(&self)->Options{Options{preset:self.profile,threads:self.threads,..Options::default()}}
    fn add(&mut self,p:PathBuf){if !self.sources.contains(&p){self.sources.push(p);}}
    fn browse(&mut self,ui:&mut egui::Ui,ctx:&egui::Context){
        ui.heading("Содержимое архива");
        let Some(path)=self.path.clone() else{
            ui.add_space(36.);
            ui.vertical_centered(|ui|{
                ui.heading("Ваши архивы");
                ui.label("Откройте .sda, чтобы просмотреть содержимое, проверить или распаковать данные.");
                ui.add_space(12.);
                if ui.button("Открыть архив").clicked(){if let Some(p)=open_dialog().pick_file(){self.start(Task::Open(p),ctx);}}
                if ui.button("Создать новый").clicked(){self.page=Page::Create;}
            });
            return;
        };
        ui.label(path.display().to_string());
        ui.add_space(8.);
        ui.horizontal_wrapped(|ui|{
            if ui.button("Проверить").clicked(){self.start(Task::Test(path.clone()),ctx);}
            if ui.button("Распаковать всё").clicked(){
                if self.multi{
                    if let Some(parent)=rfd::FileDialog::new().pick_folder(){
                        let name=path.file_stem().and_then(|s|s.to_str()).unwrap_or("archive");
                        self.start(Task::Extract(path.clone(),parent.join(format!("{name}-restored"))),ctx);
                    }
                }else if let Some(out)=rfd::FileDialog::new().set_file_name("restored.bin").save_file(){self.start(Task::Unpack(path.clone(),out),ctx);}
            }
            if ui.add_enabled(self.multi&&self.selected.is_some(),egui::Button::new("Извлечь выбранный файл")).clicked(){
                if let Some(name)=self.selected.clone(){
                    let suggested=name.rsplit('/').next().unwrap_or("restored");
                    if let Some(out)=rfd::FileDialog::new().set_file_name(suggested).save_file(){self.start(Task::ExtractFile(path.clone(),name,out),ctx);}
                }
            }
        });
        if !self.multi{ui.add_space(12.);ui.label("Однофайловый поток. Оглавление отсутствует.");return;}
        let files=self.entries.iter().filter(|e|!e.directory).count();
        let total=self.entries.iter().fold(0u64,|n,e|n.saturating_add(e.size));
        ui.add_space(12.);
        ui.horizontal(|ui|{ui.strong(format!("{files} файлов"));ui.label(format!("Исходный объём: {}",size(total)));});
        ui.add(egui::TextEdit::singleline(&mut self.filter).hint_text("Поиск по имени…").desired_width(f32::INFINITY));
        ui.separator();
        let filter=self.filter.to_lowercase();
        let filtered:Vec<_>=self.entries.iter().filter(|e|filter.is_empty()||e.path.to_lowercase().contains(&filter)).collect();
        egui::ScrollArea::vertical().auto_shrink([false,false]).show_rows(ui,26.,filtered.len(),|ui,range|{
            for i in range{
                let e=filtered[i];
                ui.horizontal(|ui|{
                    let label=if e.directory{format!("Каталог  {}",e.path)}else{e.path.clone()};
                    if ui.add_enabled(!e.directory,egui::Button::selectable(self.selected.as_deref()==Some(e.path.as_str()),label)).clicked(){self.selected=Some(e.path.clone());}
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center),|ui|{ui.label(if e.directory{"—".into()}else{size(e.size)});});
                });
            }
        });
    }
    fn create(&mut self,ui:&mut egui::Ui,ctx:&egui::Context){
        ui.heading("Новый архив");
        ui.label("Добавьте файлы и каталоги. Исходные данные не изменяются.");
        ui.add_space(8.);
        ui.horizontal(|ui|{
            if ui.button("Добавить файлы").clicked(){if let Some(ps)=rfd::FileDialog::new().pick_files(){for p in ps{self.add(p);}}}
            if ui.button("Добавить каталог").clicked(){if let Some(p)=rfd::FileDialog::new().pick_folder(){self.add(p);}}
            if ui.button("Очистить").clicked(){self.sources.clear();}
        });
        let mut remove=None;
        egui::ScrollArea::vertical().max_height(190.).show(ui,|ui|{
            for (i,p) in self.sources.iter().enumerate(){
                ui.horizontal(|ui|{if ui.small_button("Удалить").clicked(){remove=Some(i);}ui.label(p.display().to_string());});
            }
        });
        if let Some(i)=remove{self.sources.remove(i);}
        ui.separator();
        ui.strong("Режим сжатия");
        ui.horizontal_wrapped(|ui|{
            for (p,n) in [(Preset::Fast,"Быстрый"),(Preset::Balanced,"Баланс"),(Preset::Deep,"Глубокий"),(Preset::Extreme,"Максимум")]{
                ui.selectable_value(&mut self.profile,p,n);
            }
        });
        ui.label(match self.profile{Preset::Fast=>"Минимум вычислений, без Хаффмана и дельта-патчей.",Preset::Balanced=>"Компромисс между временем и размером.",Preset::Deep=>"Полный поиск вариантов кодирования.",Preset::Extreme=>"Расширенный словарь; может работать существенно дольше."});
        ui.add(egui::Slider::new(&mut self.threads,1..=8).text("Потоки"));
        let single=self.sources.len()==1&&self.sources[0].is_file();
        ui.add_enabled(single,egui::Checkbox::new(&mut self.single_stream,"Однофайловый поток (без оглавления)"));
        ui.add_space(10.);
        if ui.add_enabled(!self.sources.is_empty(),egui::Button::new("Создать архив").min_size(egui::vec2(160.,38.))).clicked(){
            if let Some(p)=open_dialog().set_file_name("archive.sda").save_file(){
                if single&&self.single_stream{self.start(Task::Pack(self.sources[0].clone(),p,self.opts()),ctx);}
                else{self.start(Task::Create(p,self.sources.clone(),self.opts()),ctx);}
            }
        }
    }
}
impl eframe::App for Desktop{
    fn update(&mut self,ctx:&egui::Context,_frame:&mut eframe::Frame){
        self.poll(ctx);
        let busy=self.job.is_some();
        egui::TopBottomPanel::top("header").show(ctx,|ui|{
            ui.horizontal(|ui|{
                ui.heading(egui::RichText::new("SedravArch").color(egui::Color32::from_rgb(90,210,180)));
                ui.label("0.8  /  Desktop");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center),|ui|{
                    if ui.add_enabled(!busy,egui::Button::new("Открыть…")).clicked(){if let Some(p)=open_dialog().pick_file(){self.start(Task::Open(p),ctx);}}
                });
            });
        });
        egui::TopBottomPanel::bottom("status").show(ctx,|ui|{
            ui.horizontal(|ui|{
                if busy{ui.spinner();}
                ui.label(egui::RichText::new(&self.status).color(if self.error{egui::Color32::LIGHT_RED}else{ui.visuals().text_color()}));
            });
            ui.label(egui::RichText::new("Лимит распаковки: 8 ГиБ. Существующие файлы не перезаписываются.").small().weak());
        });
        egui::SidePanel::left("nav").exact_width(165.).resizable(false).show(ctx,|ui|{
            ui.add_space(12.);
            ui.add_enabled_ui(!busy,|ui|{
                if ui.selectable_label(self.page==Page::Browse,"Архив").clicked(){self.page=Page::Browse;}
                if ui.selectable_label(self.page==Page::Create,"Создание").clicked(){self.page=Page::Create;}
            });
            ui.add_space(16.);ui.separator();ui.label("Локальная обработка");
            ui.label(egui::RichText::new("Собственный движок Rust").small().weak());
        });
        egui::CentralPanel::default().show(ctx,|ui|{
            ui.add_enabled_ui(!busy,|ui|{match self.page{Page::Browse=>self.browse(ui,ctx),Page::Create=>self.create(ui,ctx)}});
        });
    }
}
fn main()->eframe::Result<()>{
    let options=eframe::NativeOptions{viewport:egui::ViewportBuilder::default().with_inner_size([960.,620.]).with_min_inner_size([720.,460.]),..Default::default()};
    eframe::run_native("SedravArch",options,Box::new(|cc|{
        cc.egui_ctx.set_visuals(egui::Visuals::dark());
        Ok(Box::new(Desktop::default()))
    }))
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test] fn formatting(){assert_eq!(size(1024),"1.0 КиБ");assert_eq!(size(0),"0 Б");}
    #[test] fn operation_pipeline(){
        let root=std::env::temp_dir().join(format!("sedravarch-desktop-test-{}",std::process::id()));
        fs::create_dir(&root).unwrap();
        let input=root.join("data.txt");let arch=root.join("data.sda");let out=root.join("out");
        fs::write(&input,b"SedravArch desktop").unwrap();
        execute(Task::Create(arch.clone(),vec![input],Options::default())).unwrap();
        let ResultData::Opened(_,entries,true)=execute(Task::Open(arch.clone())).unwrap() else{panic!("missing entries")};
        assert_eq!(entries.len(),1);
        execute(Task::Test(arch.clone())).unwrap();
        execute(Task::ExtractFile(arch,"data.txt".into(),out.clone())).unwrap();
        assert_eq!(fs::read(out).unwrap(),b"SedravArch desktop");
        fs::remove_dir_all(root).unwrap();
    }
}
