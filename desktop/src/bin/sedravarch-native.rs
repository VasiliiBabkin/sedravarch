#![cfg_attr(windows,windows_subsystem="windows")]
#[cfg(windows)]
#[path="../ops.rs"] mod ops;
#[cfg(windows)]
#[path="../startup.rs"] mod startup;

#[cfg(windows)]
mod win{
    use super::{ops::{self,Task,ResultData},startup};
    use sedravarch::{Options,Preset,archive::Entry};
    use std::{cell::RefCell,path::PathBuf,ptr::null_mut,sync::mpsc::{self,Receiver}};
    use windows_sys::Win32::{
        Foundation::{HWND,LPARAM,LRESULT,WPARAM},
        Graphics::Gdi::{GetStockObject,UpdateWindow,DEFAULT_GUI_FONT},
        System::LibraryLoader::GetModuleHandleW,
        UI::WindowsAndMessaging::*,
    };
    const OPEN:usize=101;const ADD_FILES:usize=102;const ADD_DIR:usize=103;
    const CLEAR:usize=104;const CREATE:usize=105;const TEST:usize=106;
    const EXTRACT:usize=107;const ONE:usize=108;const LIST:usize=109;
    const PROFILE:usize=110;const THREADS:usize=111;
    const TIMER:usize=1;
    fn wide(s:&str)->Vec<u16>{s.encode_utf16().chain(Some(0)).collect()}
    fn text(h:HWND,s:&str){unsafe{SetWindowTextW(h,wide(s).as_ptr());}}
    fn send(h:HWND,msg:u32,w:usize,l:isize)->isize{unsafe{SendMessageW(h,msg,w,l)}}
    fn add_string(h:HWND,msg:u32,s:&str){let w=wide(s);send(h,msg,0,w.as_ptr() as isize);}
    fn control(parent:HWND,class:&str,label:&str,style:u32,x:i32,y:i32,w:i32,h:i32,id:usize)->HWND{
        let hwnd=unsafe{CreateWindowExW(0,wide(class).as_ptr(),wide(label).as_ptr(),
            WS_CHILD|WS_VISIBLE|style,x,y,w,h,parent,id as _,GetModuleHandleW(std::ptr::null()),std::ptr::null())};
        if !hwnd.is_null(){
            let font=unsafe{GetStockObject(DEFAULT_GUI_FONT)};
            send(hwnd,WM_SETFONT,font as usize,1);
        }
        hwnd
    }
    fn button(p:HWND,label:&str,x:i32,y:i32,w:i32,id:usize)->HWND{
        control(p,"BUTTON",label,WS_TABSTOP,x,y,w,31,id)
    }
    fn dialog()->rfd::FileDialog{rfd::FileDialog::new().add_filter("SedravArch", &["sda"])}
    struct State{
        path:Option<PathBuf>,entries:Vec<Entry>,multi:bool,sources:Vec<PathBuf>,
        list:HWND,status:HWND,heading:HWND,profile:HWND,threads:HWND,buttons:Vec<HWND>,
        job:Option<Receiver<Result<ResultData,String>>>,smoke:bool,
    }
    thread_local!{static STATE:RefCell<Option<State>>=const{RefCell::new(None)};}
    impl State{
        fn new(p:HWND,smoke:bool)->Result<Self,String>{
            let heading=control(p,"STATIC","SedravArch • 0.8.1 — локальный архиватор",0,16,14,790,26,0);
            let buttons=vec![button(p,"Открыть архив…",16,50,146,OPEN),
                button(p,"Добавить файлы…",170,50,145,ADD_FILES),
                button(p,"Добавить папку…",323,50,145,ADD_DIR),
                button(p,"Очистить",476,50,102,CLEAR),
                button(p,"Создать архив…",586,50,174,CREATE),
                button(p,"Проверить",16,430,140,TEST),
                button(p,"Распаковать всё…",164,430,178,EXTRACT),
                button(p,"Извлечь файл…",350,430,174,ONE)];
            let list=control(p,"LISTBOX","",WS_BORDER|WS_VSCROLL|WS_HSCROLL|WS_TABSTOP|LBS_NOTIFY as u32,
                16,96,744,312,LIST);
            send(list,LB_SETHORIZONTALEXTENT,1600,0);
            control(p,"STATIC","Сжатие:",0,16,480,75,24,0);
            let profile=control(p,"COMBOBOX","",WS_TABSTOP|CBS_DROPDOWNLIST as u32|WS_VSCROLL,94,476,188,160,PROFILE);
            for s in ["Быстрый","Баланс","Глубокий","Максимум"]{add_string(profile,CB_ADDSTRING,s);}
            send(profile,CB_SETCURSEL,1,0);
            control(p,"STATIC","Потоки:",0,306,480,75,24,0);
            let threads=control(p,"COMBOBOX","",WS_TABSTOP|CBS_DROPDOWNLIST as u32|WS_VSCROLL,382,476,100,220,THREADS);
            for n in 1..=8{add_string(threads,CB_ADDSTRING,&n.to_string());}
            send(threads,CB_SETCURSEL,1,0);
            let status=control(p,"STATIC","Откройте архив или добавьте файлы для создания нового.",0,16,522,744,42,0);
            if [heading,list,status,profile,threads].iter().any(|h|h.is_null())||buttons.iter().any(|h|h.is_null()){
                return Err("Не удалось создать элементы окна Windows".into());
            }
            Ok(Self{path:None,entries:vec![],multi:false,sources:vec![],list,status,heading,profile,threads,buttons,job:None,smoke})
        }
        fn set_busy(&self,busy:bool){
            for &h in &self.buttons{unsafe{EnableWindow(h,(!busy) as i32);}}
            for h in [self.list,self.profile,self.threads]{unsafe{EnableWindow(h,(!busy) as i32);}}
        }
        fn launch(&mut self,t:Task){
            if self.job.is_some(){return;}
            let(tx,rx)=mpsc::channel();self.job=Some(rx);
            self.set_busy(true);text(self.status,"Выполняется операция…");
            std::thread::spawn(move||{
                let result=std::panic::catch_unwind(||ops::execute(t))
                    .map_err(|_|"Внутренняя ошибка движка".to_string()).and_then(|r|r.map_err(|e|e.to_string()));
                let _=tx.send(result);
            });
        }
        fn poll(&mut self){
            let Some(rx)=&self.job else{return;};
            let r=match rx.try_recv(){Ok(r)=>r,Err(mpsc::TryRecvError::Empty)=>return,
                Err(mpsc::TryRecvError::Disconnected)=>Err("Рабочий поток прерван".into())};
            self.job=None;self.set_busy(false);
            match r{
                Ok(ResultData::Opened(p,e,m))=>{
                    self.sources.clear();self.path=Some(p);self.entries=e;self.multi=m;
                    self.refresh();text(self.status,"Архив открыт. Нажмите «Проверить» для проверки всех данных.");
                }
                Ok(ResultData::Created(p))=>self.launch(Task::Open(p)),
                Ok(ResultData::Message(m))=>text(self.status,&m),
                Err(e)=>{text(self.status,&format!("Ошибка: {e}"));startup::log(&format!("operation failed: {e}"));}
            }
        }
        fn refresh(&self){
            send(self.list,LB_RESETCONTENT,0,0);
            if let Some(p)=&self.path{
                text(self.heading,&format!("Архив: {}",p.display()));
                if !self.multi{add_string(self.list,LB_ADDSTRING,"Однофайловый поток (без оглавления)");}
                for e in &self.entries{add_string(self.list,LB_ADDSTRING,&format!("{}    {}    {}",if e.directory{"[Папка]"}else{"[Файл]"},e.path,ops::size(e.size)));}
            }else{
                text(self.heading,"Создание архива — выбранные источники");
                for p in &self.sources{add_string(self.list,LB_ADDSTRING,&p.display().to_string());}
            }
        }
        fn add(&mut self,ps:Vec<PathBuf>){
            if self.path.take().is_some(){self.entries.clear();self.sources.clear();}
            for p in ps{if !self.sources.contains(&p){self.sources.push(p);}}
            self.refresh();
        }
        fn options(&self)->Options{
            let preset=match send(self.profile,CB_GETCURSEL,0,0){0=>Preset::Fast,2=>Preset::Deep,3=>Preset::Extreme,_=>Preset::Balanced};
            let threads=(send(self.threads,CB_GETCURSEL,0,0)+1).clamp(1,8) as usize;
            Options{preset,threads,..Options::default()}
        }
        fn command(&mut self,id:usize){
            if self.job.is_some(){return;}
            match id{
                OPEN=>{if let Some(p)=dialog().pick_file(){self.launch(Task::Open(p));}}
                ADD_FILES=>{if let Some(ps)=rfd::FileDialog::new().pick_files(){self.add(ps);}}
                ADD_DIR=>{if let Some(p)=rfd::FileDialog::new().pick_folder(){self.add(vec![p]);}}
                CLEAR=>{self.path=None;self.entries.clear();self.sources.clear();self.refresh();text(self.status,"Список очищен.");}
                CREATE=>{if self.sources.is_empty(){text(self.status,"Сначала добавьте файлы или каталог.");}
                    else if let Some(p)=dialog().set_file_name("archive.sda").save_file(){self.launch(Task::Create(p,self.sources.clone(),self.options()));}}
                TEST=>{if let Some(p)=self.path.clone(){self.launch(Task::Test(p));}}
                EXTRACT=>{if let Some(p)=self.path.clone(){
                    if self.multi{if let Some(parent)=rfd::FileDialog::new().pick_folder(){
                        let stem=p.file_stem().and_then(|s|s.to_str()).unwrap_or("archive");
                        let target=parent.join(format!("{stem}-restored"));self.launch(Task::Extract(p,target));
                    }}else if let Some(out)=rfd::FileDialog::new().set_file_name("restored.bin").save_file(){self.launch(Task::Unpack(p,out));}
                }}
                ONE=>{if let Some(p)=self.path.clone(){
                    let i=send(self.list,LB_GETCURSEL,0,0);
                    if let Some(e)=self.entries.get(i as usize).filter(|e|!e.directory){
                        let n=e.path.clone();let suggested=n.rsplit('/').next().unwrap_or("restored");
                        if let Some(out)=rfd::FileDialog::new().set_file_name(suggested).save_file(){self.launch(Task::ExtractFile(p,n,out));}
                    }else{text(self.status,"Выберите файл, а не каталог.");}
                }}
                _=>{}
            }
        }
    }
    unsafe extern "system" fn proc(hwnd:HWND,msg:u32,w:WPARAM,l:LPARAM)->LRESULT{
        match msg{
            WM_COMMAND=>{
                STATE.with(|s|{if let Ok(mut s)=s.try_borrow_mut(){if let Some(state)=s.as_mut(){state.command(w&0xffff);}}});0
            }
            WM_TIMER=>{
                let smoke=STATE.with(|s|{if let Ok(mut s)=s.try_borrow_mut(){if let Some(state)=s.as_mut(){state.poll();return state.smoke;}}false});
                if smoke{startup::log("native smoke timer reached");DestroyWindow(hwnd);}0
            }
            WM_CLOSE=>{
                let busy=STATE.with(|s|s.try_borrow().map(|s|s.as_ref().is_some_and(|s|s.job.is_some())).unwrap_or(true));
                if !busy{DestroyWindow(hwnd);}0
            }
            WM_DESTROY=>{PostQuitMessage(0);0}
            _=>DefWindowProcW(hwnd,msg,w,l),
        }
    }
    pub fn run()->Result<(),String>{
        let smoke=std::env::args_os().any(|a|a=="--smoke-test");
        unsafe{
            let instance=GetModuleHandleW(std::ptr::null());
            if instance.is_null(){return Err(std::io::Error::last_os_error().to_string());}
            let class=wide("SedravArchNative");
            let wc=WNDCLASSW{style:0,lpfnWndProc:Some(proc),cbClsExtra:0,cbWndExtra:0,
                hInstance:instance,hIcon:null_mut(),hCursor:LoadCursorW(null_mut(),IDC_ARROW),
                hbrBackground:6usize as _,lpszMenuName:std::ptr::null(),lpszClassName:class.as_ptr()};
            if RegisterClassW(&wc)==0{return Err(format!("RegisterClassW: {}",std::io::Error::last_os_error()));}
            let hwnd=CreateWindowExW(0,class.as_ptr(),wide("SedravArch 0.8.1").as_ptr(),
                WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,CW_USEDEFAULT,CW_USEDEFAULT,800,620,
                null_mut(),null_mut(),instance,std::ptr::null());
            if hwnd.is_null(){return Err(format!("CreateWindowExW: {}",std::io::Error::last_os_error()));}
            let state=State::new(hwnd,smoke)?;
            STATE.with(|s|*s.borrow_mut()=Some(state));
            if SetTimer(hwnd,TIMER,if smoke{1000}else{120},None)==0{return Err("SetTimer failed".into());}
            ShowWindow(hwnd,SW_SHOW);UpdateWindow(hwnd);
            startup::log("native window created");
            let mut msg:MSG=std::mem::zeroed();
            loop{
                let rc=GetMessageW(&mut msg,null_mut(),0,0);
                if rc==-1{return Err(format!("GetMessageW: {}",std::io::Error::last_os_error()));}
                if rc==0{break;}
                TranslateMessage(&msg);DispatchMessageW(&msg);
            }
            startup::log("native window closed");
        }
        Ok(())
    }
}
#[cfg(windows)]
fn main()->std::process::ExitCode{
    startup::init("native");
    match std::panic::catch_unwind(win::run){
        Ok(Ok(()))=>std::process::ExitCode::SUCCESS,
        Ok(Err(e))=>{startup::fatal(&e);std::process::ExitCode::FAILURE},
        Err(_)=>{startup::fatal("Внутренняя ошибка запуска. См. журнал.");std::process::ExitCode::FAILURE}
    }
}
#[cfg(not(windows))]
fn main(){eprintln!("Native fallback is Windows-only.");}
