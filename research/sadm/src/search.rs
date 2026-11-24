//! Bounded candidate index over bottom-k rolling fingerprints.
use std::collections::{BTreeMap, BTreeSet, VecDeque};

const K: usize = 8;
const WINDOW: usize = 256;

pub fn fingerprint(data: &[u8]) -> BTreeSet<u64> {
    const WIDTH: usize = 16;
    const BASE: u64 = 257;
    let mut hash = 0u64;
    let power = BASE.wrapping_pow(WIDTH as u32);
    let mut bottom = BTreeSet::new();
    for (i, &byte) in data.iter().enumerate() {
        hash = hash.wrapping_mul(BASE).wrapping_add(u64::from(byte) + 1);
        if i >= WIDTH {
            hash = hash.wrapping_sub(power.wrapping_mul(u64::from(data[i - WIDTH]) + 1));
        }
        if i + 1 >= WIDTH {
            // Finalizer makes selection independent of polynomial hash magnitude.
            let mut mixed = hash;
            mixed = (mixed ^ (mixed >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
            mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94d049bb133111eb);
            mixed ^= mixed >> 31;
            if bottom.len() < K || bottom.last().is_some_and(|&last| mixed < last) {
                bottom.insert(mixed);
                if bottom.len() > K {
                    bottom.pop_last();
                }
            }
        }
    }
    bottom
}

#[derive(Default)]
pub struct Index {
    keys: BTreeMap<u64, VecDeque<usize>>,
    history: VecDeque<BTreeSet<u64>>,
}
impl Index {
    pub fn insert(&mut self, id: usize, keys: BTreeSet<u64>) {
        if self.history.len() == WINDOW {
            for key in self.history.pop_front().unwrap() {
                let hits = self.keys.get_mut(&key).unwrap();
                hits.pop_front();
                if hits.is_empty() {
                    self.keys.remove(&key);
                }
            }
        }
        for &key in &keys {
            self.keys.entry(key).or_default().push_back(id);
        }
        self.history.push_back(keys);
    }
    pub fn rank(&self, keys: &BTreeSet<u64>) -> Vec<usize> {
        let mut votes = BTreeMap::<usize, usize>::new();
        for key in keys {
            if let Some(hits) = self.keys.get(key) {
                for &id in hits.iter().rev().take(16) {
                    *votes.entry(id).or_default() += 1;
                }
            }
        }
        let mut ranked: Vec<_> = votes.into_iter().collect();
        ranked.sort_unstable_by_key(|&(id, hits)| (std::cmp::Reverse(hits), std::cmp::Reverse(id)));
        ranked.into_iter().map(|(id, _)| id).collect()
    }
}
