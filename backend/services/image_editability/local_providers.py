import os
import requests
import cv2
import numpy as np
import logging
import threading
import time
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image
from pathlib import Path

from .extractors import ElementExtractor, ExtractionResult, ExtractionContext
from .inpaint_providers import InpaintProvider

logger = logging.getLogger(__name__)

# 全局锁，确保本地 OCR 和 Inpaint 请求串行执行
_local_api_lock = threading.Lock()

class LocalOCRElementExtractor(ElementExtractor):
    """
    基于本地 OCR REST 接口的元素提取器
    """
    
    def __init__(self, api_url: str, output_dir: Path):
        self.api_url = api_url
        self.output_dir = output_dir
        
    def supports_type(self, element_type: Optional[str]) -> bool:
        return element_type in ['text', 'title', 'paragraph', None]
        
    def extract(
        self,
        image_path: str,
        element_type: Optional[str] = None,
        **kwargs
    ) -> ExtractionResult:
        depth = kwargs.get('depth', 0)
        
        payload = {
            "img_path": os.path.abspath(image_path),
            "output_dir": os.path.abspath(self.output_dir)
        }
        
        logger.info(f"{'  ' * depth}Calling Local OCR: {self.api_url}")
        
        # 增加重试机制
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # 明确禁用代理，防止系统代理拦截本地请求
                # 使用全局锁限制并发
                with _local_api_lock:
                    resp = requests.post(
                        self.api_url, 
                        json=payload, 
                        timeout=120,
                        proxies={"http": None, "https": None}
                    )
                resp.raise_for_status()
                ocr_data = resp.json().get("json_content", {})
                
                elements = self._process_ocr_data(ocr_data, image_path)
                
                context = ExtractionContext(
                    metadata={
                        'source': 'local_ocr',
                        'ocr_raw_data': ocr_data
                    }
                )
                return ExtractionResult(elements=elements, context=context)
                
            except Exception as e:
                logger.warning(f"{'  ' * depth}Local OCR attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error(f"{'  ' * depth}Local OCR all retries failed.")
                    # 失败时返回空结果
                    return ExtractionResult(elements=[])

    def _process_ocr_data(self, ocr_data: Dict[str, Any], image_path: str) -> List[Dict[str, Any]]:
        elements = []
        rec_texts = ocr_data.get("rec_texts", [])
        rec_polys = ocr_data.get("rec_polys", [])
        
        # 获取图像颜色信息等
        img = cv2.imread(image_path)
        
        for text, poly in zip(rec_texts, rec_polys):
            if not text.strip():
                continue
                
            # Convert poly to bbox [x0, y0, x1, y1]
            pts = np.array(poly)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            
            bbox = [float(x0), float(y0), float(x1), float(y1)]
            
            # 提取文字样式属性
            style_dict = self._analyze_text_style(img, poly)
            
            # 符合 TextStyleResult 结构
            elements.append({
                'bbox': bbox,
                'type': 'text',
                'content': text,
                'image_path': None,
                'metadata': {
                    'poly': poly,
                    'style': style_dict, # 这将被转换或直接使用
                    'source': 'local_ocr'
                }
            })
        return elements

    def _analyze_text_style(self, img: np.ndarray, poly: List[List[int]]) -> Dict[str, Any]:
        """
        初步分析文字样式，符合 TextStyleResult 格式
        """
        if img is None:
            return {'font_color_rgb': [0, 0, 0], 'confidence': 0.5}
            
        try:
            # 1. 颜色提取
            mask = np.zeros(img.shape[:2], dtype=np.uint8)
            pts = np.array(poly, np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [pts], 255)
            
            mean_val = cv2.mean(img, mask=mask)
            # BGR to RGB
            rgb = [int(mean_val[2]), int(mean_val[1]), int(mean_val[0])]
            
            return {
                'font_color_rgb': rgb,
                'is_bold': False,
                'is_italic': False,
                'confidence': 0.8
            }
        except Exception as e:
            logger.error(f"分析文字样式失败: {e}")
            return {'font_color_rgb': [0, 0, 0], 'confidence': 0.0}

class LocalInpaintProvider(InpaintProvider):
    """
    基于本地 Inpaint REST 接口的 Inpaint 提供者
    """
    
    def __init__(self, api_url: str, output_dir: Path):
        self.api_url = api_url
        self.output_dir = output_dir
        
    def inpaint_regions(
        self,
        image: Image.Image,
        bboxes: List[tuple],
        types: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Image.Image]:
        
        image_id = kwargs.get('image_id', 'temp_inpaint')
        temp_img_path = self.output_dir / f"{image_id}_orig.png"
        mask_path = self.output_dir / f"{image_id}_mask.png"
        output_path = self.output_dir / f"{image_id}_inpainted.png"
        
        try:
            # 1. 保存原图
            image.save(temp_img_path)
            
            # 2. 生成 Mask
            # 尝试从 kwargs 获取 poly，如果没有则用 bbox
            polys = kwargs.get('polys', [])
            self._generate_mask(image.size, bboxes, polys, mask_path)
            
            # 3. 调用 Inpaint API
            payload = {
                "img_path": os.path.abspath(str(temp_img_path)),
                "mask_path": os.path.abspath(str(mask_path)),
                "output_path": os.path.abspath(str(output_path))
            }
            
            logger.info(f"Calling Local Inpaint: {self.api_url}")
            
            # 增加重试机制
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    # 明确禁用代理，防止系统代理拦截本地请求
                    # 使用全局锁限制并发
                    with _local_api_lock:
                        resp = requests.post(
                            self.api_url, 
                            json=payload, 
                            timeout=120,
                            proxies={"http": None, "https": None}
                        )
                    resp.raise_for_status()
                    # success
                    break
                except Exception as e:
                    logger.warning(f"Local Inpaint attempt {attempt+1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    else:
                        raise e # re-raise after all retries fail
            
            if os.path.exists(output_path):
                return Image.open(output_path).convert("RGB")
            else:
                logger.error("Local Inpaint output file not found")
                return None
                
        except Exception as e:
            logger.error(f"Local Inpaint failed: {e}")
            return None
        finally:
            # 清理临时文件 (可选)
            # if os.path.exists(temp_img_path): os.remove(temp_img_path)
            # if os.path.exists(mask_path): os.remove(mask_path)
            pass

    def _generate_mask(self, size: Tuple[int, int], bboxes: List[tuple], polys: List[List[List[int]]], mask_path: Path, padding: int = 5):
        """
        生成 Inpaint 掩码图

        Args:
            size: 图片尺寸 (width, height)
            bboxes: 边界框列表 [(x0, y0, x1, y1), ...]
            polys: 多边形列表 [[[x1,y1], [x2,y2], ...], ...]
            mask_path: 输出掩码图路径
            padding: 扩展边界的像素数，用于确保文字完全被覆盖
        """
        width, height = size
        mask = np.zeros((height, width), dtype=np.uint8)

        if polys:
            for poly in polys:
                pts = np.array(poly, np.int32).reshape((-1, 1, 2))
                # 扩展多边形：使用形态学膨胀
                temp_mask = np.zeros((height, width), dtype=np.uint8)
                cv2.fillPoly(temp_mask, [pts], 255)
                # 膨胀操作扩展边界
                if padding > 0:
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (padding * 2 + 1, padding * 2 + 1))
                    temp_mask = cv2.dilate(temp_mask, kernel)
                mask = cv2.bitwise_or(mask, temp_mask)
        else:
            # 如果没有 poly，回退到 bbox（添加 padding）
            for bbox in bboxes:
                x0, y0, x1, y1 = map(int, bbox)
                # 扩展边界，但不超出图片范围
                x0 = max(0, x0 - padding)
                y0 = max(0, y0 - padding)
                x1 = min(width, x1 + padding)
                y1 = min(height, y1 + padding)
                cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)

        cv2.imwrite(str(mask_path), mask)