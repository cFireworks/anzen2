use serde::{Deserialize, Serialize};
use reqwest::blocking::Client;
use image::{RgbaImage, Rgba};
use imageproc::drawing::{draw_text_mut, draw_hollow_rect_mut};
use ab_glyph::PxScale;

#[derive(Debug, Clone)]
#[derive(Serialize, Deserialize)]
#[derive(PartialEq)]
pub enum BabyStatus {
    Sleeping,   // 深度睡眠
    Awake,      // 清醒
    Crying,     // 哭闹
    Unknown,    // 未知状态
}

#[derive(Serialize, Deserialize)]
#[derive(Debug)]
pub struct DetectionResult {
    pub baby_detected: bool,  // 是否检测到婴儿
    pub confidence: f32,
    pub state: Option<BabyStatus>,  // 婴儿状态
    pub bounding_box: Option<Vec<i32>>,  // [x1, y1, x2, y2]
}

pub fn send_detection_request(jpeg_data: &Vec<u8>) -> Result<DetectionResult, reqwest::Error> {
    let client = Client::new();
    let image_part = reqwest::blocking::multipart::Part::bytes(jpeg_data.clone())
        .file_name("image.jpg") // 文件名
        .mime_str("image/jpeg")?; // MIME 类型为 binary
    let form = reqwest::blocking::multipart::Form::new().part("file", image_part);
    let response_result = client
        .post("http://127.0.0.1:8000/detect/image")
        .multipart(form)
        .send();
        // .unwrap();
    // log::debug!("response {}",response.json());
    // response.json::<DetectionResult>()

        // 记录请求的响应或错误
    match response_result {
        Ok(response) => {            
            // 尝试解析返回的 JSON 数据
            match response.json::<DetectionResult>() {
                Ok(detection_result) => {
                    log::debug!("Received detection result: {:?}", detection_result);
                    Ok(detection_result)
                }
                Err(e) => {
                    log::error!("Failed to parse JSON response: {}", e);
                    Err(e)
                }
            }
        }
        Err(e) => {
            log::error!("Request failed: {}", e);
            Err(e)
        }
    }
}

fn process_detection_result(result: DetectionResult) -> (bool, BabyStatus, Option<Vec<i32>>) {
    if result.baby_detected {
        let baby_status = result.state.unwrap_or(BabyStatus::Unknown);  // 默认状态为 Sleeping
        (true, baby_status, result.bounding_box)
    } else {
        (false, BabyStatus::Unknown, None)  // 没有检测到婴儿
    }
}

fn draw_label(image: &mut RgbaImage, text: &str, x: i32, y: i32) {
    // 加载字体
    let font_data = Vec::from(include_bytes!("../../static/fonts/Arial.ttf") as &[u8]);
    let font = ab_glyph::FontVec::try_from_vec(font_data).unwrap();
    
    // 设置文字大小
    let px_scale = PxScale::from(20.0);

    // 绘制文字
    draw_text_mut(image, Rgba([255, 0, 0, 255]), x, y, px_scale, &font, text);
}

fn annotate_image(jpeg_data: &Vec<u8>, bounding_box: Option<Vec<i32>>, baby_status: &BabyStatus) -> Vec<u8> {
    // 将 JPEG 数据转换为 RGBA 图像
    let img = image::load_from_memory(jpeg_data).unwrap();
    let mut annotated_image: image::ImageBuffer<Rgba<u8>, Vec<u8>> = img.to_rgba8(); // 转换为 RGBA 格式

    if let Some(bounding_box) = bounding_box {
        // 获取图像的宽度和高度
        let (width, height) = annotated_image.dimensions();

        let (x1, y1, x2, y2) = (
            bounding_box[0],
            bounding_box[1],
            bounding_box[2],
            bounding_box[3],
        );
        // 确保 bounding box 在图像的有效范围内
        let x1 = x1.min(width as i32);
        let y1 = y1.min(height as i32);
        let x2 = x2.min(width as i32);
        let y2 = y2.min(height as i32);

        let (box_width, box_height) = (x2-x1, y2-y1);


        // 绘制边界框
        draw_hollow_rect_mut(&mut annotated_image, 
            imageproc::rect::Rect::at(x1 as i32, y1 as i32).of_size(box_width as u32, box_height as u32), 
            Rgba([255, 0, 0, 255])); // 红色框

        // 添加状态标签
        let label = match baby_status {
            BabyStatus::Sleeping => "Sleeping",
            BabyStatus::Awake => "Awake",
            BabyStatus::Crying => "Crying",
            BabyStatus::Unknown => "Unknown",
        };

         // 使用rusttype库来绘制文字
        draw_label(&mut annotated_image, label, x1, y1);

        log::debug!("Adding label: {}", label);

        // 返回 RGBA 图像的字节数据
        return annotated_image.into_raw();  // 返回 RGBA 格式的字节流
    }

    // 如果没有 bounding box，则直接返回原图（RGBA 格式）
    annotated_image.into_raw()
}

pub fn analyze_baby_posture(jpeg_data: &Vec<u8>) -> (bool, BabyStatus, Option<Vec<u8>>) {
    // 发送 HTTP 请求
    match send_detection_request(jpeg_data) {
        Ok(result) => {
            // 处理检测结果
            let (baby_detected, baby_status, bounding_box) = process_detection_result(result);
            
            if !baby_detected {
                log::debug!("There's NO Baby Face.");
                return (false, BabyStatus::Unknown, None)
            }
            
            log::debug!("ok, Baby Face Detected!");
            // 注释图像并返回结果
            let annotated_image = annotate_image(jpeg_data, bounding_box, &baby_status);

            // 返回婴儿检测标志、婴儿状态和注释后的图像
            (baby_detected, baby_status, Some(annotated_image))
        }
        Err(_) => {
            // 请求失败时返回 false 和原始图像
            log::error!("Failed to Detect Baby Face!");
            (false, BabyStatus::Unknown, None)
        }
    }
}
