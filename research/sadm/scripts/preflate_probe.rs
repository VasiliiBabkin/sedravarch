//! Build as a preflate_util example in a scratch checkout of preflate-rs.
use preflate_container::{
    PreflateContainerConfig, PreflateContainerProcessor, ProcessBuffer, RecreateContainerProcessor,
};
use std::fs::File;
use std::io::{Cursor, Read};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    const LIMIT: usize = 16 * 1024 * 1024;
    let path = std::env::args_os().nth(1).ok_or("expected input path")?;
    let mut original = Vec::new();
    File::open(path)?
        .take((LIMIT + 1) as u64)
        .read_to_end(&mut original)?;
    if original.len() > LIMIT {
        return Err("sample exceeds input budget".into());
    }
    let config = PreflateContainerConfig {
        max_chunk_size: LIMIT,
        total_plain_text_limit: LIMIT as u64,
        chunk_plain_text_limit: LIMIT,
        ..PreflateContainerConfig::default()
    };
    let mut encoder = PreflateContainerProcessor::new(&config, 9, false);
    let mut packed = Vec::new();
    encoder.copy_to_end_size(&mut Cursor::new(&original), &mut packed, LIMIT)?;
    let stats = encoder.stats();
    let mut restored = Vec::new();
    let mut decoder = RecreateContainerProcessor::new(LIMIT);
    decoder.copy_to_end_size(&mut Cursor::new(&packed), &mut restored, LIMIT + 1)?;
    assert!(original == restored, "preflate reconstruction mismatch");
    println!(
        "{{\"archive_bytes\":{},\"deflate_bytes_seen\":{},\"correction_bytes\":{}}}",
        packed.len(),
        stats.deflate_compressed_size,
        stats.overhead_bytes
    );
    Ok(())
}
