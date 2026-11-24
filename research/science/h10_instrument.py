import pathlib
p=pathlib.Path('src/cabac_codec.rs');s=p.read_text();needle='fn encode_correction(&mut self, c: CodecCorrection, value: u32) {'
assert s.count(needle)==1
s=s.replace(needle,needle+'\n        crate::h10_record(c as usize,value);')
p.write_text(s)
p=pathlib.Path('src/lib.rs')
with p.open('a') as f:
 f.write("""
static H10_ALL: [std::sync::atomic::AtomicU64;17] = [const {std::sync::atomic::AtomicU64::new(0)};17];
static H10_NONZERO: [std::sync::atomic::AtomicU64;17] = [const {std::sync::atomic::AtomicU64::new(0)};17];
fn h10_record(i:usize,v:u32){
 use std::sync::atomic::Ordering::Relaxed;
 H10_ALL[i].fetch_add(1,Relaxed);
 if v!=0 { H10_NONZERO[i].fetch_add(1,Relaxed); }
}
pub fn h10_counts()->[(u64,u64);17]{
 use std::sync::atomic::Ordering::Relaxed;
 std::array::from_fn(|i|(H10_ALL[i].load(Relaxed),H10_NONZERO[i].load(Relaxed)))
}
""")
with pathlib.Path('Cargo.toml').open('a') as f:f.write('\n[[bin]]\nname="h10-driver"\npath="h10_driver.rs"\n')
