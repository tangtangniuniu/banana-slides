import os
import json
from contextlib import asynccontextmanager
from typing import List, Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from paddlex import create_pipeline
from simple_lama_inpainting import SimpleLama
from PIL import Image
import torch

# 全局变量，用于存储加载的模型
ocr_pipeline = None
lama_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    生命周期管理器：在服务启动时加载模型，在关闭时清理。
    """
    global ocr_pipeline, lama_model
    print("正在初始化模型，请稍候...")
    
    # 初始化 OCR Pipeline
    try:
        print("正在加载 OCR Pipeline (paddlex)...")
        # 显式指定 device="cpu" 以避免可能的 CUDA 问题
        try:
             ocr_pipeline = create_pipeline(pipeline="OCR", device="cpu")
        except TypeError:
             print("PaddleX create_pipeline does not support device argument directly, falling back to default.")
             ocr_pipeline = create_pipeline(pipeline="OCR")
        
        print("OCR Pipeline 加载成功。")
    except Exception as e:
        print(f"OCR Pipeline 加载失败: {e}")

    # 初始化 Lama Inpainting
    try:
        print("正在加载 SimpleLama 模型...")
        # 强制使用 CPU，因为当前环境的 PyTorch CUDA 核心与显卡架构不匹配
        lama_model = SimpleLama(device=torch.device('cpu'))
        print("SimpleLama 模型加载成功 (CPU模式)。")
    except Exception as e:
        print(f"SimpleLama 模型加载失败: {e}")

    print("所有模型初始化完成。")
    yield
    print("服务正在关闭...")

app = FastAPI(lifespan=lifespan, title="OCR & Inpainting API Service")

# --- 数据模型定义 ---

class OCRRequest(BaseModel):
    img_path: str       # 本地图片路径
    output_dir: str     # 本地输出目录

class OCRResponse(BaseModel):
    json_content: Dict[str, Any] # OCR 识别结果的 JSON 内容
    output_files: List[str]      # 输出的文件列表

class InpaintRequest(BaseModel):
    img_path: str       # 原始图片路径
    mask_path: str      # Mask 图片路径
    output_path: str    # 输出图片路径

class InpaintResponse(BaseModel):
    output_path: str

# --- 接口实现 ---

@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(req: OCRRequest):
    """
    OCR 接口：输入图片路径，输出 JSON 结果和保存的文件。
    """
    if ocr_pipeline is None:
        raise HTTPException(status_code=503, detail="OCR 模型未初始化")
    
    if not os.path.exists(req.img_path):
        raise HTTPException(status_code=404, detail=f"找不到输入图片: {req.img_path}")

    # 确保输出目录存在
    os.makedirs(req.output_dir, exist_ok=True)

    try:
        # 执行预测
        # PaddleX 的 predict 接口通常返回一个生成器或列表
        output = ocr_pipeline.predict([req.img_path],
                                      use_doc_orientation_classify=False,
                                      use_doc_unwarping=False,
                                      use_textline_orientation=False)   # 关闭文本行方向检测)

        results_json = {}
        saved_files = []
        
        # 处理结果
        for res in output:
            # 根据示例代码保存图片和 JSON
            # save_to_json 和 save_to_img 通常使用输入文件名作为前缀
            res.save_to_img(req.output_dir)
            res.save_to_json(req.output_dir)
            
            # 尝试定位生成的 JSON 文件以读取内容
            # PaddleX 命名规则通常是: 文件名_res.json 或类似结构
            # 我们通过查找输出目录下最新的 json 文件或尝试匹配文件名来获取
            base_name = os.path.splitext(os.path.basename(req.img_path))[0]
            
            # 常见的命名模式猜测
            possible_json_names = [
                f"{base_name}_res.json",
                f"{base_name}.json",
                f"res_{base_name}.json"
            ]
            
            target_json_path = None
            for name in possible_json_names:
                p = os.path.join(req.output_dir, name)
                if os.path.exists(p):
                    target_json_path = p
                    break
            
            # 如果没找到，尝试读取目录里最新的 JSON 文件 (作为兜底)
            if not target_json_path:
                json_files = [f for f in os.listdir(req.output_dir) if f.endswith('.json')]
                if json_files:
                     # 按修改时间排序，取最新的
                     json_files.sort(key=lambda x: os.path.getmtime(os.path.join(req.output_dir, x)), reverse=True)
                     target_json_path = os.path.join(req.output_dir, json_files[0])

            if target_json_path and os.path.exists(target_json_path):
                saved_files.append(target_json_path)
                try:
                    with open(target_json_path, 'r', encoding='utf-8') as f:
                        results_json = json.load(f)
                except Exception as e:
                    print(f"读取 JSON 失败: {e}")
            
            # 记录可能的图片输出路径 (用于返回给调用者)
            # 这里简单记录一个基本的预期路径
            expected_img_output = os.path.join(req.output_dir, f"{base_name}_res_img.png") # 示例猜测
            if os.path.exists(expected_img_output):
                saved_files.append(expected_img_output)

        return OCRResponse(json_content=results_json, output_files=saved_files)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OCR 处理出错: {str(e)}")


@app.post("/inpaint", response_model=InpaintResponse)
async def inpaint_endpoint(req: InpaintRequest):
    """
    Lama Inpainting 接口：输入原图和 Mask，输出修复后的图片。
    """
    if lama_model is None:
        raise HTTPException(status_code=503, detail="Lama 模型未初始化")

    if not os.path.exists(req.img_path):
        raise HTTPException(status_code=404, detail=f"找不到输入图片: {req.img_path}")
    if not os.path.exists(req.mask_path):
        raise HTTPException(status_code=404, detail=f"找不到 Mask 图片: {req.mask_path}")

    try:
        # 打开图片
        image = Image.open(req.img_path)
        mask = Image.open(req.mask_path).convert('L') # Mask 需要转为灰度图

        # 执行推理
        result = lama_model(image, mask)

        # 确保输出目录存在
        os.makedirs(os.path.dirname(os.path.abspath(req.output_path)), exist_ok=True)

        # 保存结果
        result.save(req.output_path)
        
        return InpaintResponse(output_path=req.output_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Inpainting 处理出错: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # 启动服务，监听 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
