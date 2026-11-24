//! Copy/add scripts. Copy offsets are absolute and may move backwards.
use crate::{bad, take, u16_from, Result};
use std::collections::BTreeMap;

pub fn encode(base: &[u8], data: &[u8], ceiling: usize) -> Option<Vec<u8>> {
    const KEY: usize = 8;
    let mut index = BTreeMap::new();
    for (offset, key) in base.windows(KEY).enumerate() {
        index.entry(key).or_insert(offset);
    }
    let mut output = Vec::new();
    let mut position = 0;
    let mut literal = 0;
    while position + KEY <= data.len() {
        let Some(&offset) = index.get(&data[position..position + KEY]) else {
            position += 1;
            continue;
        };
        let length = KEY
            + base[offset + KEY..]
                .iter()
                .zip(&data[position + KEY..])
                .take_while(|(a, b)| a == b)
                .count();
        add(&data[literal..position], &mut output);
        output.push(1);
        output.extend_from_slice(&(offset as u16).to_le_bytes());
        output.extend_from_slice(&(length as u16).to_le_bytes());
        if output.len() >= ceiling {
            return None;
        }
        position += length;
        literal = position;
    }
    add(&data[literal..], &mut output);
    (output.len() < ceiling).then_some(output)
}

fn add(bytes: &[u8], output: &mut Vec<u8>) {
    if !bytes.is_empty() {
        output.push(0);
        output.extend_from_slice(&(bytes.len() as u16).to_le_bytes());
        output.extend_from_slice(bytes);
    }
}

pub fn decode(base: &[u8], mut script: &[u8], length: usize) -> Result<Vec<u8>> {
    let mut output = Vec::with_capacity(length);
    while !script.is_empty() {
        let tag = take(&mut script, 1)?[0];
        let offset = match tag {
            0 => 0,
            1 => u16_from(&mut script)?,
            _ => return Err(bad("delta operation")),
        };
        let count = u16_from(&mut script)?;
        if count == 0 || count > length - output.len() {
            return Err(bad("delta length"));
        }
        let bytes = if tag == 0 {
            take(&mut script, count)?
        } else {
            base.get(offset..offset + count)
                .ok_or_else(|| bad("delta extent"))?
        };
        output.extend_from_slice(bytes);
    }
    if output.len() != length {
        return Err(bad("delta output length"));
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn handles_moves_and_literal_changes() {
        let base = b"abcdefghijklmno---------ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        let data = b"ABCDEFGHIJKLMNO!!!abcdefghijklmno";
        let script = encode(base, data, data.len()).unwrap();
        assert_eq!(decode(base, &script, data.len()).unwrap(), data);
    }
}
