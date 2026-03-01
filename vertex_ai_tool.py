"""
独立的 Vertex AI 调用工具类
支持文本大模型和图像大模型的调用
"""
import os
import logging
from typing import Optional, List
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class VertexAITool:
    """Vertex AI 调用工具类，整合文本和图像大模型"""

    def __init__(
        self,
        project_id: str = None,
        location: str = None,
        credentials_path: str = None,
        text_model: str = "gemini-3.1-pro-preview",
        image_model: str = "gemini-3.1-flash-image-preview",
        timeout: float = 300.0,
        max_retries: int = 2
    ):
        """
        初始化 Vertex AI 工具类

        Args:
            project_id: GCP 项目 ID
            location: GCP 区域
            credentials_path: 服务账号凭据文件路径
            text_model: 文本模型名称
            image_model: 图像模型名称
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
        """
        self.project_id = project_id
        self.location = location or 'us-central1'
        self.credentials_path = credentials_path
        self.text_model = text_model
        self.image_model = image_model
        self.timeout = timeout
        self.max_retries = max_retries

        if credentials_path:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

        timeout_ms = int(self.timeout * 1000)
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
            http_options=types.HttpOptions(timeout=timeout_ms)
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def generate_text(self, prompt: str, thinking_budget: int = 0) -> str:
        """
        使用 Vertex AI 文本模型生成文本

        Args:
            prompt: 输入提示词
            thinking_budget: 推理预算（0 表示禁用推理模式）

        Returns:
            生成的文本
        """
        config_params = {}
        if thinking_budget > 0:
            config_params['thinking_config'] = types.ThinkingConfig(thinking_budget=thinking_budget)

        response = self.client.models.generate_content(
            model=self.text_model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_params) if config_params else None,
        )
        return response.text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def generate_with_image(self, prompt: str, image_path: str, thinking_budget: int = 0) -> str:
        """
        使用 Vertex AI 文本模型生成文本（支持图像输入）

        Args:
            prompt: 输入提示词
            image_path: 图像文件路径
            thinking_budget: 推理预算（0 表示禁用推理模式）

        Returns:
            生成的文本
        """
        img = Image.open(image_path)
        contents = [img, prompt]

        config_params = {}
        if thinking_budget > 0:
            config_params['thinking_config'] = types.ThinkingConfig(thinking_budget=thinking_budget)

        response = self.client.models.generate_content(
            model=self.text_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_params) if config_params else None,
        )
        return response.text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True
    )
    def generate_image(
        self,
        prompt: str,
        ref_images: Optional[List[Image.Image]] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "2K",
        enable_thinking: bool = True,
        thinking_budget: int = 1024
    ) -> Optional[Image.Image]:
        """
        使用 Vertex AI 图像模型生成图像

        Args:
            prompt: 图像生成提示词
            ref_images: 参考图像列表
            aspect_ratio: 图像比例
            resolution: 图像分辨率
            enable_thinking: 是否启用推理模式
            thinking_budget: 推理预算

        Returns:
            生成的 PIL Image 对象，失败返回 None
        """
        try:
            contents = []

            if ref_images:
                for ref_img in ref_images:
                    contents.append(ref_img)

            contents.append(prompt)

            config_params = {
                'response_modalities': ['TEXT', 'IMAGE'],
                'image_config': types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=resolution
                )
            }

            if enable_thinking:
                config_params['thinking_config'] = types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                    include_thoughts=True
                )

            response = self.client.models.generate_content(
                model=self.image_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_params)
            )

            last_image = None
            for i, part in enumerate(response.parts):
                if part.text is None:
                    try:
                        image = part.as_image()
                        if image:
                            if isinstance(image, Image.Image):
                                last_image = image
                            elif hasattr(image, 'image_bytes') and image.image_bytes:
                                last_image = Image.open(BytesIO(image.image_bytes))
                            elif hasattr(image, '_pil_image') and image._pil_image:
                                last_image = image._pil_image
                    except Exception as e:
                        logger.warning(f"提取图像失败: {e}")

            if last_image:
                return last_image

            raise ValueError("响应中未找到图像")

        except Exception as e:
            logger.error(f"图像生成失败: {e}", exc_info=True)
            raise Exception(f"图像生成失败: {e}") from e


if __name__ == "__main__":
    """简单的测试代码，测试 Vertex AI 文本和图像大模型调用"""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    load_dotenv()

    vertex_tool = VertexAITool(
        project_id=os.getenv('VERTEX_PROJECT_ID'),
        location=os.getenv('VERTEX_LOCATION'),
        credentials_path=os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
        text_model=os.getenv('TEXT_MODEL', 'gemini-3-flash-preview'),
        image_model=os.getenv('IMAGE_MODEL', 'gemini-3-pro-image-preview')
    )

    print("=" * 60)
    print("Vertex AI 工具类测试")
    print("=" * 60)

    test_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'test_img.png')

    while True:
        print("\n请选择测试类型:")
        print("1. 文本模型测试")
        print("2. 图像模型测试")
        print("3. 退出")
        choice = input("请输入选项 (1-3): ").strip()

        if choice == "1":
            print("\n--- 文本模型测试 ---")
            prompt = input("请输入提示词 (默认: '你好，请简单介绍一下你自己。'): ").strip()
            if not prompt:
                prompt = "你好，请简单介绍一下你自己。"

            try:
                print(f"\n正在调用 Vertex AI 文本模型...")
                result = vertex_tool.generate_text(prompt)
                print("\n生成结果:")
                print("-" * 60)
                print(result)
                print("-" * 60)
            except Exception as e:
                print(f"\n错误: {e}")

        elif choice == "2":
            print("\n--- 图像模型测试 ---")
            prompt = input("请输入图像生成提示词 (默认: '一只可爱的猫咪在花园里玩耍'): ").strip()
            if not prompt:
                prompt = "一只可爱的猫咪在花园里玩耍"

            save_path = input("请输入保存路径 (默认: 'generated_image.png'): ").strip()
            if not save_path:
                save_path = "generated_image.png"

            try:
                print(f"\n正在调用 Vertex AI 图像模型...")
                print(f"提示词: {prompt}")
                result = vertex_tool.generate_image(prompt)

                if result:
                    result.save(save_path)
                    print(f"\n图像已保存到: {save_path}")
                    print(f"图像尺寸: {result.size}")
                else:
                    print("\n图像生成失败")
            except Exception as e:
                print(f"\n错误: {e}")

        elif choice == "3":
            print("\n退出测试")
            break

        else:
            print("\n无效选项，请重新选择")
