use crate::detection::posture_analysis::BabyStatus;
use crate::detection::posture_analysis::analyze_baby_posture;
use crate::detection::baby_detection::detect_baby;
use std::collections::HashMap;

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
        let device_sender_id = msg.0;
        let image_data = msg.1;
        // Step 1: Perform quick baby target detection
        let baby_detected = detect_baby(&image_data);
        
        if !baby_detected {
            // No baby detected, directly forward the image to the monitor clients
            forward_to_monitor_clients(device_sender_id, image_data.clone(), &self.connected_monitor_clients);
            return;
        }

        // Step 2: If baby detected, perform posture analysis (sleeping or awake)
        let (baby_status, annotated_image) = analyze_baby_posture(&image_data);

        // Step 3: If baby is awake, send to remote baby sleep alert API
        if baby_status == BabyStatus::Awake {
            log::info!("Baby Status: Awake (id: {})", device_sender_id);
        }

        // Step 4: Forward annotated image to monitor clients
        forward_to_monitor_clients(device_sender_id, annotated_image, &self.connected_monitor_clients);
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