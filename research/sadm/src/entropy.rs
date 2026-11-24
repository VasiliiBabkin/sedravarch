//! Byte-alphabet rANS with an explicit normalized model per stream.
use crate::{bad, Result};

const LOWER: u32 = 1 << 23;

pub fn shannon(data: &[u8]) -> f64 {
    let mut counts = [0u32; 256];
    for &byte in data {
        counts[byte as usize] += 1;
    }
    counts
        .iter()
        .filter(|&&n| n != 0)
        .map(|&n| {
            let p = f64::from(n) / data.len() as f64;
            -p * p.log2()
        })
        .sum()
}

pub fn encode(data: &[u8], precision: u8) -> Vec<u8> {
    let mut counts = [0u32; 256];
    for &byte in data {
        counts[byte as usize] += 1;
    }
    let total = 1u32 << precision;
    let distinct = counts.iter().filter(|&&n| n > 0).count() as u32;
    let spare = total - distinct;
    let mut freq = [0u32; 256];
    let mut ranks = Vec::new();
    let mut remainder = spare;
    for (symbol, &count) in counts.iter().enumerate().filter(|(_, n)| **n > 0) {
        let scaled = spare * count;
        freq[symbol] = 1 + scaled / data.len() as u32;
        remainder -= freq[symbol] - 1;
        ranks.push((std::cmp::Reverse(scaled % data.len() as u32), symbol));
    }
    ranks.sort_unstable();
    for &(_, symbol) in ranks.iter().take(remainder as usize) {
        freq[symbol] += 1;
    }
    let mut output = vec![precision];
    output.extend_from_slice(&(distinct as u16).to_le_bytes());
    let mut starts = [0u32; 256];
    let mut start = 0;
    for (symbol, &f) in freq.iter().enumerate().filter(|(_, f)| **f > 0) {
        starts[symbol] = start;
        start += f;
        output.push(symbol as u8);
        output.extend_from_slice(&(f as u16).to_le_bytes());
    }
    let mut state = LOWER;
    let mut tail = Vec::new();
    for &symbol in data.iter().rev() {
        let f = freq[symbol as usize];
        let ceiling = ((LOWER >> precision) << 8) * f;
        while state >= ceiling {
            tail.push(state as u8);
            state >>= 8;
        }
        state = ((state / f) << precision) + state % f + starts[symbol as usize];
    }
    output.extend_from_slice(&state.to_le_bytes());
    output.extend(tail.into_iter().rev());
    output
}

pub fn decode(mut stream: &[u8], length: usize) -> Result<Vec<u8>> {
    let precision = crate::take(&mut stream, 1)?[0];
    if !matches!(precision, 8 | 10 | 12) {
        return Err(bad("rANS precision"));
    }
    let total = 1usize << precision;
    let distinct = crate::u16_from(&mut stream)?;
    if !(1..=256).contains(&distinct) || length == 0 {
        return Err(bad("rANS alphabet"));
    }
    let mut table = Vec::with_capacity(total);
    let mut previous = None;
    for _ in 0..distinct {
        let symbol = crate::take(&mut stream, 1)?[0];
        let f = crate::u16_from(&mut stream)?;
        if previous.is_some_and(|p| symbol <= p) || f == 0 || table.len() + f > total {
            return Err(bad("rANS model"));
        }
        previous = Some(symbol);
        let start = table.len();
        table.resize(start + f, (symbol, start as u32, f as u32));
    }
    if table.len() != total {
        return Err(bad("rANS frequency sum"));
    }
    let mut state = crate::u32_from(&mut stream)?;
    if !(LOWER..LOWER << 8).contains(&state) {
        return Err(bad("rANS initial state"));
    }
    let mut output = Vec::with_capacity(length);
    for _ in 0..length {
        let slot = state & (total as u32 - 1);
        let (symbol, start, f) = table[slot as usize];
        output.push(symbol);
        state = f * (state >> precision) + slot - start;
        while state < LOWER {
            state = (state << 8) | u32::from(crate::take(&mut stream, 1)?[0]);
        }
    }
    if state != LOWER || !stream.is_empty() {
        return Err(bad("rANS terminal state"));
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normalized_models_roundtrip() {
        for data in [
            vec![42; 16384],
            (0..=255).cycle().take(16384).collect(),
            b"banana".to_vec(),
        ] {
            for precision in [8, 10, 12] {
                let packed = encode(&data, precision);
                assert_eq!(decode(&packed, data.len()).unwrap(), data);
                assert!(decode(&packed[..packed.len() - 1], data.len()).is_err());
            }
        }
    }
}
