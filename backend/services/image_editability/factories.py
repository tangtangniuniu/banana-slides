"""
工厂类 - 负责创建和配置具体的提取器和Inpaint提供者
"""
import logging
from typing import List, Optional, Any
from pathlib import Path

from .extractors import ElementExtractor, MinerUElementExtractor, BaiduOCRElementExtractor, BaiduAccurateOCRElementExtractor, ExtractorRegistry
from .hybrid_extractor import HybridElementExtractor, create_hybrid_extractor
from .inpaint_providers import (
    InpaintProvider, 
    DefaultInpaintProvider, 
    GenerativeEditInpaintProvider, 
    BaiduInpaintProvider,
    HybridInpaintProvider,
    InpaintProviderRegistry
)
from .text_attribute_extractors import (
    TextAttributeExtractor,
    CaptionModelTextAttributeExtractor,
    CVTextAttributeExtractor,
    TextAttributeExtractorRegistry,
    TextStyleResult
)

logger = logging.getLogger(__name__)


class ExtractorFactory:
    """元素提取器工厂"""
    
    @staticmethod
    def create_default_extractors(
        parser_service: Any,
        upload_folder: Path,
        baidu_table_ocr_provider: Optional[Any] = None
    ) -> List[ElementExtractor]:
        """
        创建默认的元素提取器列表
        """
        extractors: List[ElementExtractor] = []
        
        # 1. 百度OCR提取器（用于表格）
        if baidu_table_ocr_provider is None:
            try:
                from services.ai_providers.ocr import create_baidu_table_ocr_provider
                baidu_provider = create_baidu_table_ocr_provider()
                if baidu_provider:
                    extractors.append(BaiduOCRElementExtractor(baidu_provider))
                    logger.info("✅ 百度表格OCR提取器已启用")
            except Exception as e:
                logger.warning(f"无法初始化百度表格OCR: {e}")
        else:
            extractors.append(BaiduOCRElementExtractor(baidu_table_ocr_provider))
            logger.info("✅ 百度表格OCR提取器已启用")
        
        # 2. MinerU提取器（默认通用提取器）
        mineru_extractor = MinerUElementExtractor(parser_service, upload_folder)
        extractors.append(mineru_extractor)
        logger.info("✅ MinerU提取器已启用")
        
        return extractors
    
    @staticmethod
    def create_extractor_registry(
        parser_service: Any,
        upload_folder: Path,
        baidu_table_ocr_provider: Optional[Any] = None
    ) -> ExtractorRegistry:
        """
        创建元素类型到提取器的注册表
        """
        # 创建MinerU提取器
        mineru_extractor = MinerUElementExtractor(parser_service, upload_folder)
        logger.info("✅ MinerU提取器已创建")
        
        # 尝试创建百度OCR提取器
        baidu_ocr_extractor = None
        if baidu_table_ocr_provider is None:
            try:
                from services.ai_providers.ocr import create_baidu_table_ocr_provider
                baidu_provider = create_baidu_table_ocr_provider()
                if baidu_provider:
                    baidu_ocr_extractor = BaiduOCRElementExtractor(baidu_provider)
                    logger.info("✅ 百度表格OCR提取器已创建")
            except Exception as e:
                logger.warning(f"无法初始化百度表格OCR: {e}")
        else:
            baidu_ocr_extractor = BaiduOCRElementExtractor(baidu_table_ocr_provider)
            logger.info("✅ 百度表格OCR提取器已创建")
        
        # 尝试创建百度高精度OCR提取器
        baidu_accurate_ocr_extractor = None
        try:
            from services.ai_providers.ocr import create_baidu_accurate_ocr_provider
            baidu_accurate_provider = create_baidu_accurate_ocr_provider()
            if baidu_accurate_provider:
                baidu_accurate_ocr_extractor = BaiduAccurateOCRElementExtractor(baidu_accurate_provider)
                logger.info("✅ 百度高精度OCR提取器已创建")
        except Exception as e:
            logger.warning(f"无法初始化百度高精度OCR: {e}")
        
        # 使用注册表的工厂方法创建默认配置
        return ExtractorRegistry.create_default(
            mineru_extractor=mineru_extractor,
            baidu_ocr_extractor=baidu_ocr_extractor,
            baidu_accurate_ocr_extractor=baidu_accurate_ocr_extractor
        )
    
    @staticmethod
    def create_baidu_accurate_ocr_extractor(
        baidu_accurate_ocr_provider: Optional[Any] = None
    ) -> Optional[BaiduAccurateOCRElementExtractor]:
        """
        创建百度高精度OCR提取器
        """
        if baidu_accurate_ocr_provider is None:
            try:
                from services.ai_providers.ocr import create_baidu_accurate_ocr_provider
                baidu_accurate_ocr_provider = create_baidu_accurate_ocr_provider()
            except Exception as e:
                logger.warning(f"无法初始化百度高精度OCR Provider: {e}")
                return None
        
        if baidu_accurate_ocr_provider is None:
            return None
        
        return BaiduAccurateOCRElementExtractor(baidu_accurate_ocr_provider)
    
    @staticmethod
    def create_local_extractor(api_url: str, upload_folder: Path) -> Optional[ElementExtractor]:
        """创建本地OCR提取器"""
        try:
            from .local_providers import LocalOCRElementExtractor
            output_dir = upload_folder / 'editable_images'
            output_dir.mkdir(parents=True, exist_ok=True)
            return LocalOCRElementExtractor(api_url, output_dir)
        except Exception as e:
            logger.error(f"创建LocalOCRElementExtractor失败: {e}")
            return None

    @staticmethod
    def create_hybrid_extractor(
        parser_service: Any,
        upload_folder: Path,
        baidu_accurate_ocr_provider: Optional[Any] = None,
        contain_threshold: float = 0.8,
        intersection_threshold: float = 0.3
    ) -> Optional[HybridElementExtractor]:
        """
        创建混合元素提取器
        """
        # 创建MinerU提取器
        mineru_extractor = MinerUElementExtractor(parser_service, upload_folder)
        logger.info("✅ MinerU提取器已创建（用于混合提取）")
        
        # 创建百度高精度OCR提取器
        baidu_ocr_extractor = ExtractorFactory.create_baidu_accurate_ocr_extractor(
            baidu_accurate_ocr_provider
        )
        
        if baidu_ocr_extractor is None:
            logger.warning("无法创建百度高精度OCR提取器，混合提取器创建失败")
            return None
        
        logger.info("✅ 百度高精度OCR提取器已创建（用于混合提取）")
        
        return HybridElementExtractor(
            mineru_extractor=mineru_extractor,
            baidu_ocr_extractor=baidu_ocr_extractor,
            contain_threshold=contain_threshold,
            intersection_threshold=intersection_threshold
        )
    
    @staticmethod
    def create_hybrid_extractor_registry(
        parser_service: Any,
        upload_folder: Path,
        baidu_table_ocr_provider: Optional[Any] = None,
        baidu_accurate_ocr_provider: Optional[Any] = None,
        contain_threshold: float = 0.8,
        intersection_threshold: float = 0.3
    ) -> ExtractorRegistry:
        """
        创建使用混合提取器的注册表
        """
        # 创建MinerU提取器作为回退
        mineru_extractor = MinerUElementExtractor(parser_service, upload_folder)
        logger.info("✅ MinerU提取器已创建")
        
        # 尝试创建混合提取器
        hybrid_extractor = ExtractorFactory.create_hybrid_extractor(
            parser_service=parser_service,
            upload_folder=upload_folder,
            baidu_accurate_ocr_provider=baidu_accurate_ocr_provider,
            contain_threshold=contain_threshold,
            intersection_threshold=intersection_threshold
        )
        
        # 尝试创建百度表格OCR提取器
        baidu_table_ocr_extractor = None
        if baidu_table_ocr_provider is None:
            try:
                from services.ai_providers.ocr import create_baidu_table_ocr_provider
                baidu_provider = create_baidu_table_ocr_provider()
                if baidu_provider:
                    from .extractors import BaiduOCRElementExtractor
                    baidu_table_ocr_extractor = BaiduOCRElementExtractor(baidu_provider)
                    logger.info("✅ 百度表格OCR提取器已创建")
            except Exception as e:
                logger.warning(f"无法初始化百度表格OCR: {e}")
        else:
            from .extractors import BaiduOCRElementExtractor
            baidu_table_ocr_extractor = BaiduOCRElementExtractor(baidu_table_ocr_provider)
            logger.info("✅ 百度表格OCR提取器已创建")
        
        # 创建注册表
        registry = ExtractorRegistry()
        
        # 设置默认提取器
        if hybrid_extractor:
            registry.register_default(hybrid_extractor)
            logger.info("✅ 使用混合提取器作为默认提取器")
        else:
            registry.register_default(mineru_extractor)
            logger.info("⚠️ 混合提取器不可用，回退到MinerU提取器")
        
        # 表格类型使用百度表格OCR（如果可用）
        if baidu_table_ocr_extractor:
            registry.register_types(list(ExtractorRegistry.TABLE_TYPES), baidu_table_ocr_extractor)
        
        return registry


class InpaintProviderFactory:
    """Inpaint提供者工厂"""
    
    @staticmethod
    def create_default_provider(inpainting_service: Optional[Any] = None) -> Optional[InpaintProvider]:
        """
        创建默认的Inpaint提供者（使用Volcengine Inpainting服务）
        """
        if inpainting_service is None:
            from services.inpainting_service import get_inpainting_service
            inpainting_service = get_inpainting_service()
        
        logger.info("创建DefaultInpaintProvider")
        return DefaultInpaintProvider(inpainting_service)
    
    @staticmethod
    def create_generative_edit_provider(
        ai_service: Optional[Any] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "2K"
    ) -> InpaintProvider:
        """
        创建基于生成式大模型的Inpaint提供者
        """
        if ai_service is None:
            from services.ai_service_manager import get_ai_service
            ai_service = get_ai_service()
        
        logger.info("创建GenerativeEditInpaintProvider")
        return GenerativeEditInpaintProvider(ai_service, aspect_ratio, resolution)
    
    @staticmethod
    def create_inpaint_registry(
        mask_provider: Optional[InpaintProvider] = None,
        generative_provider: Optional[InpaintProvider] = None,
        default_provider_type: str = "generative"
    ) -> InpaintProviderRegistry:
        """
        创建重绘方法注册表
        """
        # 自动创建提供者
        if mask_provider is None:
            mask_provider = InpaintProviderFactory.create_default_provider()
        
        if generative_provider is None:
            generative_provider = InpaintProviderFactory.create_generative_edit_provider()
        
        # 创建注册表
        registry = InpaintProviderRegistry()
        
        # 设置默认提供者
        if default_provider_type == "generative" and generative_provider:
            registry.register_default(generative_provider)
        elif mask_provider:
            registry.register_default(mask_provider)
        elif generative_provider:
            registry.register_default(generative_provider)
        
        # 注册类型映射（可通过registry.register()动态扩展）
        if mask_provider:
            # 文本和表格使用mask-based精确移除
            registry.register_types(['text', 'title', 'paragraph'], mask_provider)
            registry.register_types(['table', 'table_cell'], mask_provider)
        
        if generative_provider:
            # 图片和图表使用生成式重绘
            registry.register_types(['image', 'figure', 'chart', 'diagram'], generative_provider)
        
        logger.info(f"创建InpaintProviderRegistry: 默认={default_provider_type}, "
                   f"mask={mask_provider is not None}, generative={generative_provider is not None}")
        
        return registry
    
    @staticmethod
    def create_baidu_inpaint_provider() -> Optional[BaiduInpaintProvider]:
        """
        创建百度图像修复提供者
        """
        try:
            from services.ai_providers.image.baidu_inpainting_provider import create_baidu_inpainting_provider
            baidu_provider = create_baidu_inpainting_provider()
            if baidu_provider:
                logger.info("✅ 创建BaiduInpaintProvider")
                return BaiduInpaintProvider(baidu_provider)
            else:
                logger.warning("⚠️ 无法创建百度图像修复Provider（API Key未配置）")
                return None
        except Exception as e:
            logger.warning(f"⚠️ 创建BaiduInpaintProvider失败: {e}")
            return None
    
    @staticmethod
    def create_hybrid_inpaint_provider(
        baidu_provider: Optional[BaiduInpaintProvider] = None,
        generative_provider: Optional[GenerativeEditInpaintProvider] = None,
        ai_service: Optional[Any] = None,
        enhance_quality: bool = True
    ) -> Optional[HybridInpaintProvider]:
        """
        创建混合Inpaint提供者（百度修复 + 生成式画质提升）
        """
        # 创建百度修复提供者
        if baidu_provider is None:
            baidu_provider = InpaintProviderFactory.create_baidu_inpaint_provider()
        
        if baidu_provider is None:
            logger.warning("⚠️ 无法创建百度图像修复Provider，混合Provider创建失败")
            return None
        
        # 创建生成式提供者（用于画质提升）
        if generative_provider is None:
            generative_provider = InpaintProviderFactory.create_generative_edit_provider(
                ai_service=ai_service
            )
        
        logger.info("✅ 创建HybridInpaintProvider（百度修复 + 生成式画质提升）")
        return HybridInpaintProvider(
            baidu_provider=baidu_provider,
            generative_provider=generative_provider,
            enhance_quality=enhance_quality
        )

    @staticmethod
    def create_local_inpaint_provider(api_url: str, upload_folder: Path) -> Optional[InpaintProvider]:
        """创建本地Inpaint提供者"""
        try:
            from .local_providers import LocalInpaintProvider
            output_dir = upload_folder / 'editable_images'
            output_dir.mkdir(parents=True, exist_ok=True)
            return LocalInpaintProvider(api_url, output_dir)
        except Exception as e:
            logger.error(f"创建LocalInpaintProvider失败: {e}")
            return None


class ServiceConfig:
    """服务配置类 - 纯配置，不持有具体服务引用"""
    
    def __init__(
        self,
        upload_folder: Path,
        extractor_registry: ExtractorRegistry,
        inpaint_registry: InpaintProviderRegistry,
        max_depth: int = 1,
        min_image_size: int = 200,
        min_image_area: int = 40000
    ):
        """
        初始化服务配置
        """
        self.upload_folder = upload_folder
        self.extractor_registry = extractor_registry
        self.inpaint_registry = inpaint_registry
        self.max_depth = max_depth
        self.min_image_size = min_image_size
        self.min_image_area = min_image_area
    
    @classmethod
    def from_defaults(
        cls,
        mineru_token: Optional[str] = None,
        mineru_api_base: Optional[str] = None,
        upload_folder: Optional[str] = None,
        ai_service: Optional[Any] = None,
        use_hybrid_extractor: bool = True,
        use_hybrid_inpaint: bool = True,
        extractor_method: Optional[str] = None,
        inpaint_method: Optional[str] = None,
        **kwargs
    ) -> 'ServiceConfig':
        """
        从默认参数创建配置
        """
        # 自动从 Flask config 获取配置
        from flask import current_app, has_app_context
        
        if has_app_context() and current_app:
            if mineru_token is None:
                mineru_token = current_app.config.get('MINERU_TOKEN')
            if mineru_api_base is None:
                mineru_api_base = current_app.config.get('MINERU_API_BASE', 'https://mineru.net')
            if upload_folder is None:
                upload_folder = current_app.config.get('UPLOAD_FOLDER', './uploads')
        else:
            if mineru_api_base is None:
                mineru_api_base = 'https://mineru.net'
            if upload_folder is None:
                upload_folder = './uploads'
        
        # 解析upload_folder路径
        upload_path = Path(upload_folder)
        if not upload_path.is_absolute():
            from config import PROJECT_ROOT
            upload_path = Path(PROJECT_ROOT) / upload_folder.lstrip('./')
        
        logger.info(f"Upload folder resolved to: {upload_path}")
        
        # 创建提取器注册表
        extractor_registry = ExtractorRegistry()
        
        # 判断使用的提取方法
        effective_extractor_method = extractor_method
        if effective_extractor_method is None:
            effective_extractor_method = 'hybrid' if use_hybrid_extractor else 'mineru'
            
        if effective_extractor_method == 'local':
            local_ocr_url = kwargs.get('local_ocr_url')
            if not local_ocr_url and has_app_context() and current_app:
                local_ocr_url = current_app.config.get('LOCAL_OCR_URL')
            if not local_ocr_url:
                local_ocr_url = 'http://127.0.0.1:8000/ocr'
                
            local_extractor = ExtractorFactory.create_local_extractor(local_ocr_url, upload_path)
            if local_extractor:
                extractor_registry.register_default(local_extractor)
                logger.info(f"✅ 使用本地 OCR 提取器: {local_ocr_url}")
            else:
                # 回退
                effective_extractor_method = 'hybrid'
        
        if effective_extractor_method != 'local':
            from services.file_parser_service import FileParserService
            parser_service = FileParserService(
                mineru_token=mineru_token,
                mineru_api_base=mineru_api_base
            )
            
            if effective_extractor_method == 'hybrid':
                hybrid_extractor = ExtractorFactory.create_hybrid_extractor(
                    parser_service=parser_service,
                    upload_folder=upload_path,
                    contain_threshold=kwargs.get('contain_threshold', 0.8),
                    intersection_threshold=kwargs.get('intersection_threshold', 0.3)
                )
                if hybrid_extractor:
                    extractor_registry.register_default(hybrid_extractor)
                else:
                    mineru_extractor = MinerUElementExtractor(parser_service, upload_path)
                    extractor_registry.register_default(mineru_extractor)
            else: # mineru
                mineru_extractor = MinerUElementExtractor(parser_service, upload_path)
                extractor_registry.register_default(mineru_extractor)
        
        # 创建Inpaint提供者注册表
        inpaint_registry = InpaintProviderRegistry()
        
        # 判断使用的Inpaint方法
        effective_inpaint_method = inpaint_method
        if effective_inpaint_method is None:
            effective_inpaint_method = 'hybrid' if use_hybrid_inpaint else 'generative'
            
        if effective_inpaint_method == 'local':
            local_inpaint_url = kwargs.get('local_inpaint_url')
            if not local_inpaint_url and has_app_context() and current_app:
                local_inpaint_url = current_app.config.get('LOCAL_INPAINT_URL')
            if not local_inpaint_url:
                local_inpaint_url = 'http://127.0.0.1:8000/inpaint'
                
            local_inpaint = InpaintProviderFactory.create_local_inpaint_provider(local_inpaint_url, upload_path)
            if local_inpaint:
                inpaint_registry.register_default(local_inpaint)
                logger.info(f"✅ 使用本地 Inpaint 提供者: {local_inpaint_url}")
            else:
                effective_inpaint_method = 'hybrid'
                
        if effective_inpaint_method != 'local':
            if effective_inpaint_method == 'hybrid':
                hybrid_inpaint = InpaintProviderFactory.create_hybrid_inpaint_provider(
                    ai_service=ai_service,
                    enhance_quality=kwargs.get('enhance_quality', True)
                )
                if hybrid_inpaint:
                    inpaint_registry.register_default(hybrid_inpaint)
                else:
                    generative_provider = InpaintProviderFactory.create_generative_edit_provider(ai_service)
                    inpaint_registry.register_default(generative_provider)
            elif effective_inpaint_method == 'baidu':
                baidu_inpaint = InpaintProviderFactory.create_baidu_inpaint_provider()
                if baidu_inpaint:
                    inpaint_registry.register_default(baidu_inpaint)
                else:
                    generative_provider = InpaintProviderFactory.create_generative_edit_provider(ai_service)
                    inpaint_registry.register_default(generative_provider)
            else: # generative
                generative_provider = InpaintProviderFactory.create_generative_edit_provider(ai_service)
                inpaint_registry.register_default(generative_provider)
        
        return cls(
            upload_folder=upload_path,
            extractor_registry=extractor_registry,
            inpaint_registry=inpaint_registry,
            max_depth=kwargs.get('max_depth', 1),
            min_image_size=kwargs.get('min_image_size', 200),
            min_image_area=kwargs.get('min_image_area', 40000)
        )


class TextAttributeExtractorFactory:
    """文字属性提取器工厂"""
    
    @staticmethod
    def create_caption_model_extractor(
        ai_service: Optional[Any] = None,
        prompt_template: Optional[str] = None
    ) -> TextAttributeExtractor:
        """
        创建基于Caption Model的文字属性提取器
        """
        if ai_service is None:
            from services.ai_service_manager import get_ai_service
            ai_service = get_ai_service()
        
        logger.info("创建CaptionModelTextAttributeExtractor")
        return CaptionModelTextAttributeExtractor(ai_service, prompt_template)
    
    @staticmethod
    def create_cv_extractor() -> TextAttributeExtractor:
        """
        创建基于CV的文字属性提取器
        """
        logger.info("创建CVTextAttributeExtractor")
        return CVTextAttributeExtractor()

    @staticmethod
    def create_text_attribute_registry(
        caption_extractor: Optional[TextAttributeExtractor] = None,
        ai_service: Optional[Any] = None,
        mode: str = 'ai'  # ai, local_cv, none
    ) -> TextAttributeExtractorRegistry:
        """
        创建文字属性提取器注册表
        """
        registry = TextAttributeExtractorRegistry()
        extractor = None
        
        if mode == 'ai':
            if caption_extractor is None:
                caption_extractor = TextAttributeExtractorFactory.create_caption_model_extractor(ai_service=ai_service)
            extractor = caption_extractor
        elif mode == 'local_cv':
            try:
                extractor = TextAttributeExtractorFactory.create_cv_extractor()
            except Exception as e:
                logger.warning(f"无法创建Local CV提取器: {e}")
                extractor = None
        
        if extractor:
            registry.register_default(extractor)
            registry.register_types(['text', 'title', 'paragraph', 'heading', 'table_cell'], extractor)
        
        return registry