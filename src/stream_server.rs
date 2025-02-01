use crate::detection::posture_analysis::BabyStatus;
use crate::detection::posture_analysis::analyze_baby_posture;
use crate::detection::baby_detection::detect_baby;
use std::collections::HashMap;
use std::time::Instant;

use actix::{Message, Recipient};

#[derive(Message, Clone)]
#[rtype(result = "()")]
pub struct ImageReadyEvent(pub u64, pub Vec<u8>);

#[derive(Message, Clone)]
#[rtype(result = "()")]
pub struct AddMonitorClientEvent(pub u64, pub Recipient<ImageReadyEvent>);

#[derive(Message, Clone)]
#[rtype(result = "()")]
pub struct VideoSessionEndedEvent();

#[derive(Debug, Clone)]
pub struct StreamServer {
    connected_monitor_clients: HashMap<u64, Recipient<ImageReadyEvent>>,
}

impl StreamServer {
    pub fn new() -> Self {
        Self {
            connected_monitor_clients: HashMap::new(),
        }
    }
}

impl actix::Actor for StreamServer {
    type Context = actix::Context<Self>;
}

impl actix::Handler<ImageReadyEvent> for StreamServer {
    type Result = ();
    
    fn handle(&mut self, msg: ImageReadyEvent, _ctx: &mut Self::Context) -> Self::Result {
        // 记录整个方法的开始时间
        let start_total = Instant::now();

        let device_sender_id = msg.0;
        let image_data = msg.1;
        // Step 1: Perform quick baby target detection
        let start = Instant::now();  // 记录Step 1的开始时间
        let baby_detected = detect_baby(&image_data);
        let duration_step_1 = start.elapsed();  // 计算Step 1的耗时
        
        if !baby_detected {
            // No baby detected, directly forward the image to the monitor clients
            let start = Instant::now();  // 记录Step 4的开始时间
            forward_to_monitor_clients(device_sender_id, image_data.clone(), &self.connected_monitor_clients);
            let duration_step_4 = start.elapsed();  // 计算Step 4的耗时
                    // 计算总耗时
            let total_duration = start_total.elapsed();

            // 输出总时间以及各阶段的时间
            log::debug!(
                "Total processing time: {:?}\n\
                Step 1 (Baby Detection) took: {:?}\n\
                Step 4 (Forward Annotated Image) took: {:?}",
                total_duration,
                duration_step_1,
                duration_step_4
            );
            return;
        }

        // Step 2: If baby detected, perform posture analysis (sleeping or awake)
        let start = Instant::now();  // 记录Step 2的开始时间
        let (baby_status, annotated_image) = analyze_baby_posture(&image_data);
        let duration_step_2 = start.elapsed();  // 计算Step 2的耗时

        // Step 3: If baby is awake, send to remote baby sleep alert API
        if baby_status == BabyStatus::Awake {
            log::debug!("Baby Status: Awake (id: {})", device_sender_id);
        }

        // Step 4: Forward annotated image to monitor clients
        let start = Instant::now();  // 记录Step 4的开始时间
        forward_to_monitor_clients(device_sender_id, annotated_image, &self.connected_monitor_clients);
        let duration_step_4 = start.elapsed();  // 计算Step 4的耗时

        // 计算总耗时
        let total_duration = start_total.elapsed();

        // 输出总时间以及各阶段的时间
        log::debug!(
            "Total processing time: {:?}\n\
            Step 1 (Baby Detection) took: {:?}\n\
            Step 2 (Posture Analysis) took: {:?}\n\
            Step 4 (Forward Annotated Image) took: {:?}",
            total_duration,
            duration_step_1,
            duration_step_2,
            duration_step_4
        );
    }
}

impl actix::Handler<AddMonitorClientEvent> for StreamServer {
    type Result = ();

    fn handle(&mut self, msg: AddMonitorClientEvent, _ctx: &mut Self::Context) -> Self::Result {
        let monitor_client_id = msg.0;
        let monitor_client = msg.1;
        let monitor_hash = {
            use std::collections::hash_map::DefaultHasher;
            use std::hash::Hash;
            use std::hash::Hasher;

            let mut hasher = DefaultHasher::new();
            monitor_client.hash(&mut hasher);
            hasher.finish()
        };
        log::info!("adding monitor client (id: {}, hash: {:?})", monitor_client_id, monitor_hash);
        self.connected_monitor_clients.insert(monitor_client_id, monitor_client);
    }
}

impl actix::Handler<VideoSessionEndedEvent> for StreamServer {
    type Result = ();

    fn handle(&mut self, _msg: VideoSessionEndedEvent, _ctx: &mut Self::Context) -> Self::Result {
        log::info!("session ended, removing disconnected monitor clients...");
        self.connected_monitor_clients.retain(|_, mtr_client| mtr_client.connected());
    }
}


// Step 5: Helper function to forward image to monitor clients
fn forward_to_monitor_clients(device_sender_id: u64, image_data: Vec<u8>, connected_monitor_clients: &HashMap<u64, Recipient<ImageReadyEvent>>) {
    for (_monitor_client_id, monitor_client) in connected_monitor_clients {
        if let Err(err) = monitor_client.try_send(ImageReadyEvent(device_sender_id, image_data.clone())) {
            log::error!("failed to send image to monitor client: {:?}", err);
        }
    }
}