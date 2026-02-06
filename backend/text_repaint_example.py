import os
import shutil
import uuid
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Tuple, Union
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont
import json

from loguru import logger

# --- 配置 ---
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
FONT_PATH = "fonts/wqy-zenhei.ttc"  # 确保这里有一个中文字体，否则中文会显示为方框

# 确保目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("fonts", exist_ok=True)

app = FastAPI()

# 将 static 目录挂载到根路径，这样 /index.html、/app.js 等可以直接访问
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# 设置代理
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:10086'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:10086'

# 初始化 PaddleOCR (首次运行会自动下载模型，约需几分钟)
logger.info("正在加载 OCR 模型，请稍候...")
try:
    # 尝试使用离线模式，先检查本地是否有模型
    ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch",
                          det_model_dir=None, rec_model_dir=None, cls_model_dir=None,
                          use_doc_orientation_classify=False, use_doc_unwarping=False)
    logger.success("OCR 模型加载完成。")
except Exception as e:
    logger.error(f"OCR 模型加载失败: {e}")
    logger.error("请确保网络连接正常或预先下载模型文件")
    logger.error("提示: 可以先在有网络的环境下运行一次以下载模型，或手动下载模型文件")
    raise e


# --- 数据模型 ---
class TextBlock(BaseModel):
    id: int
    text: str
    new_text: str
    box: List[List[int]]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    color: str  # hex color (兼容旧版)
    bg_color: str = "#FFFFFF"  # 背景色
    text_color: str = "#000000"  # 文字颜色
    surrounding_colors: List[List[int]] = [[255,255,255]]*4  # 周边颜色数组（保留但不使用）
    font_size: int = 20  # 字体大小
    font_family: str = "default"  # 字体名称
    text_align: str = "left"  # 文字对齐方式: left, center, right
    score: float = 0.0  # OCR置信度
    angle: int = 0  # 文字角度


class ReplaceRequest(BaseModel):
    filename: str
    modifications: List[TextBlock]


# --- 辅助函数 ---
def expand_box_if_needed(box, text):
    """如果文字以数字开头且包含非数字，则扩大box下方+2像素"""
    try:
        import re
        # 检查是否以数字开头
        if text and len(text) > 0 and text[0].isdigit():
            # 检查是否包含非数字字符
            if re.search(r'\D', text):
                # 扩大下方2像素
                box[2][1] += 2  # 右下角Y
                box[3][1] += 2  # 左下角Y
                logger.debug(f"Expanded box for text '{text}' (starts with digit, contains non-digit)")
        return box
    except Exception as e:
        logger.exception(f"Error in expand_box_if_needed: {e}")
        return box


def get_surrounding_colors(img_cv, box, offset=3):
    """获取文字框周边的颜色数组（外围offset像素的矩形顶点）"""
    try:
        h, w = img_cv.shape[:2]

        # 获取box的边界
        x_coords = [p[0] for p in box]
        y_coords = [p[1] for p in box]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        # 外扩offset像素
        outer_x_min = max(0, x_min - offset)
        outer_x_max = min(w - 1, x_max + offset)
        outer_y_min = max(0, y_min - offset)
        outer_y_max = min(h - 1, y_max + offset)

        # 获取外围矩形的四个角的颜色
        corners = [
            (outer_x_min, outer_y_min),  # 左上
            (outer_x_max, outer_y_min),  # 右上
            (outer_x_max, outer_y_max),  # 右下
            (outer_x_min, outer_y_max),  # 左下
        ]

        corner_colors = []
        for x, y in corners:
            b, g, r = img_cv[y, x]
            corner_colors.append([int(r), int(g), int(b)])

        return corner_colors
    except Exception as e:
        logger.exception(f"Error in get_surrounding_colors: {e}")
        return [[0, 0, 0]] * 4


def get_background_color(img_cv, box, offset=3):
    """计算背景色：文字框周边颜色的平均值"""
    try:
        h, w = img_cv.shape[:2]

        # 获取box的边界
        x_coords = [p[0] for p in box]
        y_coords = [p[1] for p in box]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        # 外扩offset像素
        outer_x_min = max(0, x_min - offset)
        outer_x_max = min(w - 1, x_max + offset)
        outer_y_min = max(0, y_min - offset)
        outer_y_max = min(h - 1, y_max + offset)

        # 收集周边像素
        surrounding_pixels = []

        # 上边
        for x in range(outer_x_min, outer_x_max + 1):
            if outer_y_min >= 0 and outer_y_min < h and x >= 0 and x < w:
                surrounding_pixels.append(img_cv[outer_y_min, x])

        # 下边
        for x in range(outer_x_min, outer_x_max + 1):
            if outer_y_max >= 0 and outer_y_max < h and x >= 0 and x < w:
                surrounding_pixels.append(img_cv[outer_y_max, x])

        # 左边
        for y in range(outer_y_min, outer_y_max + 1):
            if y >= 0 and y < h and outer_x_min >= 0 and outer_x_min < w:
                surrounding_pixels.append(img_cv[y, outer_x_min])

        # 右边
        for y in range(outer_y_min, outer_y_max + 1):
            if y >= 0 and y < h and outer_x_max >= 0 and outer_x_max < w:
                surrounding_pixels.append(img_cv[y, outer_x_max])

        if len(surrounding_pixels) > 0:
            avg_color = np.mean(surrounding_pixels, axis=0)
            b, g, r = avg_color
            return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))

        return "#FFFFFF"
    except Exception as e:
        logger.exception(f"Error in get_background_color: {e}")
        return "#FFFFFF"


def get_text_color(img_cv, box, bg_color_hex):
    """计算文字颜色：文字区域每个点颜色减去背景色，非零点的颜色平均值"""
    try:
        # 将hex颜色转换为RGB
        bg_hex = bg_color_hex.lstrip('#')
        bg_r, bg_g, bg_b = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)

        # 获取box的边界
        x_coords = [p[0] for p in box]
        y_coords = [p[1] for p in box]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        h, w = img_cv.shape[:2]
        x_min, x_max = max(0, x_min), min(w - 1, x_max)
        y_min, y_max = max(0, y_min), min(h - 1, y_max)

        # 提取文字区域
        text_region = img_cv[y_min:y_max, x_min:x_max]

        # 减去背景色
        diff = np.abs(text_region.astype(np.int16) - np.array([bg_b, bg_g, bg_r]))

        # 计算差异强度（使用灰度值）
        diff_intensity = np.sum(diff, axis=2)

        # 阈值：找出与背景差异较大的像素（可能是文字）
        threshold = 30
        text_mask = diff_intensity > threshold

        if np.sum(text_mask) > 0:
            # 获取文字像素的颜色
            text_pixels = text_region[text_mask]
            avg_color = np.mean(text_pixels, axis=0)
            b, g, r = avg_color
            return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))

        # 如果没有找到明显的文字，返回黑色
        return "#000000"
    except Exception as e:
        logger.exception(f"Error in get_text_color: {e}")
        return "#000000"


def get_box_color(img_cv, box):
    """获取文字中心点的颜色（保留用于兼容性）"""
    try:
        # box 应该是 [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        if not isinstance(box, (list, tuple)) or len(box) < 4:
             return "#000000"

        # Check if corners are lists/tuples and have coordinates
        p1 = box[0]
        p3 = box[2]
        if not isinstance(p1, (list, tuple)) or len(p1) < 2:
            return "#000000"
        if not isinstance(p3, (list, tuple)) or len(p3) < 2:
            return "#000000"

        center_x = int((p1[0] + p3[0]) / 2)
        center_y = int((p1[1] + p3[1]) / 2)

        # 防止越界
        h, w = img_cv.shape[:2]
        center_x = max(0, min(center_x, w - 1))
        center_y = max(0, min(center_y, h - 1))

        b, g, r = img_cv[center_y, center_x]
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)
    except Exception as e:
        logger.exception(f"Error in get_box_color: {e}, box: {box}")
        return "#000000" # Default black on error


def get_font_size(box):
    """根据盒子高度估算字号"""
    # 简单的用高度作为字号，实际可能需要乘以一个系数 (如 0.8)
    try:
        return int(abs(box[2][1] - box[1][1]))
    except:
        return 20 # Default


def fill_region_with_gradient(img, box, surrounding_colors):
    """使用周边颜色数组进行渐变填充"""
    try:
        # 获取box的边界
        x_coords = [p[0] for p in box]
        y_coords = [p[1] for p in box]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        h, w = img.shape[:2]
        x_min, x_max = max(0, x_min), min(w, x_max)
        y_min, y_max = max(0, y_min), min(h, y_max)

        width = x_max - x_min
        height = y_max - y_min

        if width <= 0 or height <= 0:
            return img

        # surrounding_colors: [[r1,g1,b1], [r2,g2,b2], [r3,g3,b3], [r4,g4,b4]]
        # 四个角: 左上、右上、右下、左下
        if len(surrounding_colors) < 4:
            # 使用简单的平均颜色填充
            avg_color = np.mean(surrounding_colors, axis=0) if len(surrounding_colors) > 0 else [255, 255, 255]
            r, g, b = int(avg_color[0]), int(avg_color[1]), int(avg_color[2])
            cv2.rectangle(img, (x_min, y_min), (x_max, y_max), (b, g, r), -1)
            return img

        # 双线性插值进行渐变填充
        top_left = np.array(surrounding_colors[0])  # 左上
        top_right = np.array(surrounding_colors[1])  # 右上
        bottom_right = np.array(surrounding_colors[2])  # 右下
        bottom_left = np.array(surrounding_colors[3])  # 左下

        for y in range(height):
            for x in range(width):
                # 计算归一化坐标 (0-1)
                nx = x / max(width - 1, 1)
                ny = y / max(height - 1, 1)

                # 双线性插值
                top_color = top_left * (1 - nx) + top_right * nx
                bottom_color = bottom_left * (1 - nx) + bottom_right * nx
                color = top_color * (1 - ny) + bottom_color * ny

                # 设置像素颜色 (BGR格式)
                img_y = y_min + y
                img_x = x_min + x
                if 0 <= img_y < h and 0 <= img_x < w:
                    img[img_y, img_x] = [int(color[2]), int(color[1]), int(color[0])]  # RGB to BGR

        return img
    except Exception as e:
        logger.exception(f"Error in fill_region_with_gradient: {e}")
        return img


# --- API 接口 ---


@app.get("/api/fonts")
async def get_available_fonts():
    """获取可用字体列表"""
    try:
        fonts_dir = "fonts"
        available_fonts = []

        if os.path.exists(fonts_dir):
            for file in os.listdir(fonts_dir):
                if file.endswith(('.ttf', '.ttc', '.otf')):
                    # 去掉扩展名作为字体名称
                    font_name = os.path.splitext(file)[0]
                    available_fonts.append({
                        "name": font_name,
                        "file": file,
                        "display_name": font_name.replace('-', ' ').replace('_', ' ')
                    })

        # 添加默认字体
        if not any(f['name'] == 'default' for f in available_fonts):
            available_fonts.insert(0, {
                "name": "default",
                "file": os.path.basename(FONT_PATH),
                "display_name": "默认字体"
            })

        return JSONResponse({"fonts": available_fonts})
    except Exception as e:
        logger.exception(f"Error getting fonts: {e}")
        return JSONResponse({"fonts": [{"name": "default", "file": "", "display_name": "默认字体"}]})


@app.post("/api/ocr")
async def upload_and_ocr(file: UploadFile = File(...)):
    """上传图片并提取文字信息"""
    file_ext = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 读取图片用于颜色分析
    img_cv = cv2.imread(file_path)
    if img_cv is None:
        raise HTTPException(status_code=400, detail="无效的图片文件")

    # 运行 OCR
    try:
        result = ocr_engine.ocr(file_path, det=True, rec=True, cls=True)
    except Exception as e:
        logger.exception(f"OCR execution failed: {e}")
        raise HTTPException(status_code=500, detail="OCR processing failed")

    text_blocks = []

    # 使用新的 PaddleOCR 结果格式
    if result and isinstance(result, list) and len(result) > 0:
        ocr_result = result[0]

        # 检查是否有 json 属性
        if hasattr(ocr_result, 'json'):
            ocr_data = ocr_result.json.get('res')

            # 获取识别的文本和位置
            rec_texts = ocr_data.get('rec_texts', [])
            rec_polys = ocr_data.get('rec_polys', [])
            rec_scores = ocr_data.get('rec_scores', [])
            textline_orientation_angles = ocr_data.get('textline_orientation_angles', [])

            logger.info(f"OCR detected {len(rec_texts)} text blocks")

            # 遍历所有识别的文本
            for idx, (text, poly) in enumerate(zip(rec_texts, rec_polys)):
                try:
                    # poly 是四边形的四个点坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    if not isinstance(poly, list) or len(poly) != 4:
                        logger.warning(f"Skipping invalid poly format: {poly}")
                        continue

                    # 确保坐标是整数
                    box = [[int(p[0]), int(p[1])] for p in poly]

                    # 如果文字以数字开头且包含非数字，扩大box下方
                    box = expand_box_if_needed(box, text)

                    # 计算背景色（周边颜色平均）
                    bg_color = get_background_color(img_cv, box, offset=3)

                    # 计算文字颜色（文字区域与背景的差异）
                    text_color = get_text_color(img_cv, box, bg_color)

                    # 获取周边颜色数组（四个角点）
                    surrounding_colors = get_surrounding_colors(img_cv, box, offset=3)

                    # 获取置信度和角度
                    score = rec_scores[idx] if idx < len(rec_scores) else 0.0
                    angle = textline_orientation_angles[idx] if idx < len(textline_orientation_angles) else 0

                    # 计算字体大小
                    font_size = get_font_size(box)

                    text_blocks.append({
                        "id": idx,
                        "text": text,
                        "new_text": text,  # 默认新旧一致
                        "box": box,
                        "bg_color": bg_color,  # 背景色
                        "text_color": text_color,  # 文字颜色
                        "surrounding_colors": surrounding_colors,  # 周边颜色数组
                        "color": text_color,  # 兼容旧版，使用文字颜色
                        "font_size": font_size,  # 字体大小
                        "font_family": "default",  # 默认字体
                        "score": score,
                        "angle": angle
                    })

                    logger.debug(f"Text block {idx}: '{text}' at {box}")
                    logger.debug(f"  BG Color: {bg_color}, Text Color: {text_color}, Font Size: {font_size}")
                    logger.debug(f"  Surrounding: {surrounding_colors}")
                    logger.debug(f"  Score: {score:.3f}, Angle: {angle}")

                except Exception as e:
                    logger.exception(f"Error processing text block {idx}: {e}")
                    continue
        else:
            logger.warning("Warning: OCR result does not have 'json' attribute")
    else:
        logger.warning("Warning: OCR result is empty or invalid")

    return JSONResponse({
        "filename": unique_filename,
        "width": img_cv.shape[1],
        "height": img_cv.shape[0],
        "blocks": text_blocks
    })


@app.post("/api/replace")
async def replace_text(req: ReplaceRequest):
    """核心功能：擦除旧文字，写入新文字"""
    input_path = os.path.join(UPLOAD_DIR, req.filename)
    output_filename = f"edited_{req.filename}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    if not os.path.exists(input_path):
        raise HTTPException(status_code=404, detail="原图不存在")

    # 1. 读取图片
    img = cv2.imread(input_path)
    blocks_to_draw = []

    # 2. 处理需要修改的文字块
    for block in req.modifications:
        # 只有文字发生变化才处理
        if block.text != block.new_text:
            blocks_to_draw.append(block)

            # 使用背景色直接填充（不使用渐变）
            points = np.array(block.box, dtype=np.int32)
            # 获取背景色
            bg_hex = block.bg_color.lstrip('#')
            r, g, b = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
            logger.info(f"Filling text region with bg_color: {block.bg_color} -> RGB({r},{g},{b})")
            cv2.fillPoly(img, [points], (b, g, r))

    # 3. 绘制新文字 (使用 Pillow，因为 OpenCV 不支持中文)
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)

    try:
        # 尝试加载中文字体，如果不存在则使用默认
        base_font = ImageFont.truetype(FONT_PATH, 20)
        font_available = True
    except IOError:
        logger.warning(f"警告: 未找到字体文件 {FONT_PATH}，中文可能无法显示。")
        font_available = False
        base_font = ImageFont.load_default()

    for block in blocks_to_draw:
        box = block.box

        # 使用用户设置的字体大小，如果没有则根据box计算
        if block.font_size and block.font_size > 0:
            font_size = block.font_size
        else:
            font_size = get_font_size(box)

        # 选择字体
        font_path = FONT_PATH
        if block.font_family and block.font_family != "default":
            # 检查字体文件是否存在
            custom_font_path = os.path.join("fonts", f"{block.font_family}.ttc")
            if os.path.exists(custom_font_path):
                font_path = custom_font_path
            else:
                custom_font_path = os.path.join("fonts", f"{block.font_family}.ttf")
                if os.path.exists(custom_font_path):
                    font_path = custom_font_path

        # 加载字体
        if font_available:
            try:
                font = ImageFont.truetype(font_path, int(font_size * 0.8))  # 0.8 为微调系数
            except:
                font = ImageFont.truetype(FONT_PATH, int(font_size * 0.8))
        else:
            font = base_font

        # 使用用户设置的文字颜色
        text_color_hex = block.text_color
        try:
            hex_color = text_color_hex.lstrip('#')
            rgb_color = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            logger.info(f"Drawing text '{block.new_text}' with color {text_color_hex} -> RGB{rgb_color}, size {font_size}")
        except:
            rgb_color = (0, 0, 0)
            logger.warning(f"Failed to parse color {text_color_hex}, using black")

        # 计算文字位置（支持对齐和垂直居中）
        # 获取box的边界
        x_min = min(p[0] for p in box)
        x_max = max(p[0] for p in box)
        y_min = min(p[1] for p in box)
        y_max = max(p[1] for p in box)
        box_width = x_max - x_min
        box_height = y_max - y_min

        # 获取文字的边界框
        try:
            # PIL 10.0.0+ 使用 getbbox
            text_bbox = draw.textbbox((0, 0), block.new_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except AttributeError:
            # 旧版本 PIL 使用 textsize
            text_width, text_height = draw.textsize(block.new_text, font=font)

        # 根据对齐方式计算x坐标
        text_align = getattr(block, 'text_align', 'left')
        if text_align == 'center':
            x = x_min + (box_width - text_width) / 2
        elif text_align == 'right':
            x = x_max - text_width
        else:  # left
            x = x_min

        # 垂直居中
        y = y_min + (box_height - text_height) / 2

        logger.debug(f"Text position: align={text_align}, x={x:.1f}, y={y:.1f}, text_size=({text_width}x{text_height}), box_size=({box_width}x{box_height})")

        draw.text((x, y), block.new_text, font=font, fill=rgb_color)

    # 4. 保存并返回
    img_pil.save(output_path)

    # 返回图片的 URL (这里直接返回文件流，方便前端下载)
    return FileResponse(output_path, filename=output_filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)