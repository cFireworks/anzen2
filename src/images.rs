pub mod jpeg;
pub mod app;

use image::{self, RgbaImage};
use std::io::Cursor;


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
            app::extract_sender_id(image_data)
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

pub fn jpeg_to_rgba(jpeg_data: &Vec<u8>) -> Result<Vec<u8>, String> {
    // 使用 image 库从字节数组加载 JPEG 图像
    let img = image::load_from_memory(&jpeg_data)
        .map_err(|e| format!("Failed to load image from bytes: {}", e))?;

    // 将图像转换为 RGBA 格式
    let rgba_img: RgbaImage = img.to_rgba8();
    
    // 获取 RGBA 图像的原始像素数据
    let rgba_bytes = rgba_img.into_raw();

    // 返回 RGBA 数据字节流
    Ok(rgba_bytes)
}