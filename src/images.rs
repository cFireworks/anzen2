pub mod jpeg;
pub mod app;

#[derive(Debug)]
pub enum ImageType {
    RGBA,
    JPEG
}

pub fn detect_image_type(image_data: &Vec<u8>) -> Option<ImageType> {
    if jpeg::is_jpeg(image_data) {
        Some(ImageType::JPEG)
    } else {
        Some(ImageType::RGBA)
    }
}

pub fn get_sender_id(image_data: &Vec<u8>) -> Option<u64> {
    // TODO: add more image types
    let image_type = detect_image_type(image_data);
    match image_type {
        Some(ImageType::JPEG) => {
            jpeg::extract_app_section(image_data)
                .map(|app_section_data| app::extract_sender_id(&app_section_data))
                .unwrap_or_else(|err| {
                    log::error!("invalid app section in image: {}", err);
                    None
                })
        },
        Some(ImageType::RGBA) => {
            app::extract_sender_id(image_data)
        },
        _ => {
            log::error!("unsupported image type");
            None
        }
    }
}