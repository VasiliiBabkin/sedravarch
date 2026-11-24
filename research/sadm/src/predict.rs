//! Reversible byte subtraction with a fixed lag.
pub fn residual(data: &[u8], lag: usize) -> Vec<u8> {
    data.iter()
        .enumerate()
        .map(|(i, &value)| value.wrapping_sub(if i >= lag { data[i - lag] } else { 0 }))
        .collect()
}
pub fn restore(data: &mut [u8], lag: usize) {
    for i in lag..data.len() {
        data[i] = data[i].wrapping_add(data[i - lag]);
    }
}
