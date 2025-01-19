pub mod config;
pub mod client_message;
pub mod stream_server;
pub mod stream_session;
pub mod time;
pub mod images;
pub mod detection {
    pub mod baby_detection;
    pub mod posture_analysis;
}

pub fn add(left: usize, right: usize) -> usize {
    left + right
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn it_works() {
        let result = add(2, 2);
        assert_eq!(result, 4);
    }
}
