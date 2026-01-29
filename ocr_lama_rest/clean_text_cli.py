import os
import sys
import argparse
import requests
import cv2
import numpy as np

# API 服务地址
API_BASE_URL = "http://127.0.0.1:8000"

def call_ocr(input_path, output_dir):
    """
    调用 OCR REST 接口
    """
    url = f"{API_BASE_URL}/ocr"
    payload = {
        "img_path": os.path.abspath(input_path),
        "output_dir": os.path.abspath(output_dir)
    }
    
    print(f"Requesting OCR for: {input_path}")
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"OCR API request failed: {e}")
        if e.response is not None:
             print(f"Server response: {e.response.text}")
        sys.exit(1)

def generate_mask(image_path, ocr_data, mask_output_path):
    """
    根据 OCR 返回的 JSON 数据在本地生成 Mask 图片
    """
    print(f"Generating mask for: {image_path}")
    
    # 读取原图获取尺寸
    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Error: Could not read image {image_path}")
        
    height, width = img.shape[:2]
    
    # 创建黑色背景
    mask = np.zeros((height, width), dtype=np.uint8)
    
    # 获取文本多边形框
    # 注意：PaddleX 通用 OCR pipeline 返回结果通常包含 rec_polys
    polys = ocr_data.get("rec_polys", [])
    
    if not polys:
        print("Warning: No text detected. Mask will be empty.")
    else:
        # 将多边形填充为白色
        for poly in polys:
            pts = np.array(poly, np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [pts], 255)
        
    # 保存 Mask
    cv2.imwrite(mask_output_path, mask)
    print(f"Mask saved to {mask_output_path}")

def call_inpaint(img_path, mask_path, output_path):
    """
    调用 Inpaint REST 接口
    """
    url = f"{API_BASE_URL}/inpaint"
    payload = {
        "img_path": os.path.abspath(img_path),
        "mask_path": os.path.abspath(mask_path),
        "output_path": os.path.abspath(output_path)
    }
    
    print(f"Requesting Inpainting for: {img_path}")
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Inpaint API request failed: {e}")
        if e.response is not None:
             print(f"Server response: {e.response.text}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Clean Text CLI (REST Client)")
    parser.add_argument("input_image", help="Path to the input image")
    parser.add_argument("--output_dir", default="output", help="Directory to save outputs")
    
    args = parser.parse_args()
    
    input_image = args.input_image
    output_dir = args.output_dir
    
    if not os.path.exists(input_image):
        print(f"Error: Input image {input_image} does not exist.")
        sys.exit(1)
        
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    filename = os.path.basename(input_image)
    name, ext = os.path.splitext(filename)
    
    # 定义输出路径
    mask_path = os.path.join(output_dir, f"{name}_mask.jpg")
    final_output_path = os.path.join(output_dir, f"{name}_notext{ext}")
    
    try:
        # 1. OCR
        ocr_resp = call_ocr(input_image, output_dir)
        json_content = ocr_resp.get("json_content", {})
        
        # 2. 生成 Mask
        generate_mask(input_image, json_content, mask_path)
        
        # 3. Inpaint (修复)
        call_inpaint(input_image, mask_path, final_output_path)
        
        print(f"Successfully processed image. Result saved to: {final_output_path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
