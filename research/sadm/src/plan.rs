use crate::{crc, delta, entropy, predict, search, Options, BLOCK, DEPTH, GRID};

pub const LAGS: [usize; 4] = [1, 2, 4, 8];
pub const RECORD: usize = 15;

pub struct Block {
    pub tag: u8,
    pub base: u32,
    pub size: usize,
    pub crc: u32,
    pub payload: Vec<u8>,
    pub depth: usize,
}

fn candidate(
    data: &[u8],
    history: &[(&[u8], usize)],
    index: &search::Index,
    options: Options,
    budget: &mut usize,
) -> Block {
    let mut best = Block {
        tag: 0,
        base: u32::MAX,
        size: data.len(),
        crc: crc(data),
        payload: data.to_vec(),
        depth: 0,
    };
    let ranked = if options.references {
        index.rank(&search::fingerprint(data))
    } else {
        Vec::new()
    };
    for &id in &ranked {
        let (base, depth) = history[id];
        if depth < DEPTH && base == data {
            best.tag = 2;
            best.base = id as u32;
            best.depth = depth + 1;
            best.payload.clear();
            return best;
        }
    }
    let mut try_model = |bytes: &[u8], tag| {
        if bytes.len() < 16 {
            return;
        }
        let model = entropy::Histogram::new(bytes);
        for precision in [8, 10, 12] {
            if let Some(payload) = model.encode(bytes, precision, best.payload.len()) {
                best.tag = tag;
                best.payload = payload;
            }
        }
    };
    if options.rans {
        try_model(data, 1);
        if options.predict {
            for (i, &lag) in LAGS.iter().enumerate() {
                try_model(&predict::residual(data, lag), 4 + i as u8);
            }
        }
    }
    if options.delta {
        for id in ranked
            .into_iter()
            .filter(|&id| history[id].1 < DEPTH)
            .take(2)
        {
            let (base, depth) = history[id];
            // Charge both scanned buffers against a file-level search allowance.
            let work = base.len() + data.len();
            if work > *budget || best.payload.len() <= 5 {
                continue;
            }
            *budget -= work;
            if let Some(payload) = delta::encode(base, data, best.payload.len()) {
                best.tag = 3;
                best.base = id as u32;
                best.depth = depth + 1;
                best.payload = payload;
            }
        }
    }
    best
}

/// Exact shortest path over the retained edges, with the prior-file index frozen.
pub fn segment(
    data: &[u8],
    history: &[(&[u8], usize)],
    index: &search::Index,
    options: Options,
) -> Vec<Block> {
    let cells = data.len().div_ceil(GRID);
    let mut budget = data.len() * 8;
    if !options.multiscale {
        return data
            .chunks(BLOCK)
            .map(|bytes| candidate(bytes, history, index, options, &mut budget))
            .collect();
    }
    let mut costs = vec![usize::MAX; cells + 1];
    let mut incoming: Vec<Option<(usize, Block)>> = (0..=cells).map(|_| None).collect();
    costs[0] = 0;
    for start in 0..cells {
        for span in [4, 2, 1] {
            let end = start + span;
            if end > cells {
                continue;
            }
            let block = candidate(
                &data[start * GRID..(end * GRID).min(data.len())],
                history,
                index,
                options,
                &mut budget,
            );
            let cost = costs[start] + RECORD + block.payload.len();
            if cost < costs[end] {
                costs[end] = cost;
                incoming[end] = Some((start, block));
            }
        }
    }
    let mut path = Vec::new();
    let mut end = cells;
    while end != 0 {
        let (start, block) = incoming[end].take().unwrap();
        path.push(block);
        end = start;
    }
    path.reverse();
    path
}
