"""
Task Manager - handles background tasks using ThreadPoolExecutor
No need for Celery or Redis, uses in-memory task tracking
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Dict, Any
from datetime import datetime
from sqlalchemy import func
from models import db, Task, Page, Material, PageImageVersion, Settings
from services.ai_service import AIService
from utils import get_filtered_pages
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskManager:
    """Simple task manager using ThreadPoolExecutor"""
    
    def __init__(self, max_workers: int = 4):
        """Initialize task manager"""
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks = {}  # task_id -> Future
        self.lock = threading.Lock()
    
    def submit_task(self, task_id: str, func: Callable, *args, **kwargs):
        """Submit a background task"""
        future = self.executor.submit(func, task_id, *args, **kwargs)
        
        with self.lock:
            self.active_tasks[task_id] = future
        
        # Add callback to clean up when done and log exceptions
        future.add_done_callback(lambda f: self._task_done_callback(task_id, f))
    
    def _task_done_callback(self, task_id: str, future):
        """Handle task completion and log any exceptions"""
        try:
            # Check if task raised an exception
            exception = future.exception()
            if exception:
                logger.error(f"Task {task_id} failed with exception: {exception}", exc_info=exception)
        except Exception as e:
            logger.error(f"Error in task callback for {task_id}: {e}", exc_info=True)
        finally:
            self._cleanup_task(task_id)
    
    def _cleanup_task(self, task_id: str):
        """Clean up completed task"""
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
    
    def is_task_active(self, task_id: str) -> bool:
        """Check if task is still running"""
        with self.lock:
            return task_id in self.active_tasks
    
    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=True)


# Global task manager instance
task_manager = TaskManager(max_workers=4)


def save_image_with_version(image, project_id: str, page_id: str, file_service,
                            page_obj=None, image_format: str = 'PNG') -> tuple[str, int]:
    """
    保存图片并创建历史版本记录的公共函数

    Args:
        image: PIL Image 对象
        project_id: 项目ID
        page_id: 页面ID
        file_service: FileService 实例
        page_obj: Page 对象（可选，如果提供则更新页面状态）
        image_format: 图片格式，默认 PNG

    Returns:
        tuple: (image_path, version_number) - 图片路径和版本号

    这个函数会：
    1. 计算下一个版本号（使用 MAX 查询确保安全）
    2. 标记所有旧版本为非当前版本
    3. 保存图片到最终位置
    4. 生成并保存压缩的缓存图片
    5. 创建新版本记录
    6. 如果提供了 page_obj，更新页面状态和图片路径
    """
    # 使用 MAX 查询确保版本号安全（即使有版本被删除也不会重复）
    max_version = db.session.query(func.max(PageImageVersion.version_number)).filter_by(page_id=page_id).scalar() or 0
    next_version = max_version + 1

    # 批量更新：标记所有旧版本为非当前版本（使用单条 SQL 更高效）
    PageImageVersion.query.filter_by(page_id=page_id).update({'is_current': False})

    # 保存原图到最终位置（使用版本号）
    image_path = file_service.save_generated_image(
        image, project_id, page_id,
        version_number=next_version,
        image_format=image_format
    )

    # 生成并保存压缩的缓存图片（用于前端快速显示）
    cached_image_path = file_service.save_cached_image(
        image, project_id, page_id,
        version_number=next_version,
        quality=85
    )

    # 创建新版本记录
    new_version = PageImageVersion(
        page_id=page_id,
        image_path=image_path,
        version_number=next_version,
        is_current=True
    )
    db.session.add(new_version)

    # 如果提供了 page_obj，更新页面状态和图片路径
    if page_obj:
        page_obj.generated_image_path = image_path
        page_obj.cached_image_path = cached_image_path
        page_obj.status = 'COMPLETED'
        page_obj.updated_at = datetime.utcnow()

    # 提交事务
    db.session.commit()

    logger.debug(f"Page {page_id} image saved as version {next_version}: {image_path}, cached: {cached_image_path}")

    return image_path, next_version


def generate_descriptions_task(task_id: str, project_id: str, ai_service, 
                               project_context, outline: List[Dict], 
                               max_workers: int = 5, app=None,
                               language: str = None):
    """
    Background task for generating page descriptions
    Based on demo.py gen_desc() with parallel processing
    
    Note: app instance MUST be passed from the request context
    
    Args:
        task_id: Task ID
        project_id: Project ID
        ai_service: AI service instance
        project_context: ProjectContext object containing all project information
        outline: Complete outline structure
        max_workers: Maximum number of parallel workers
        app: Flask app instance
        language: Output language (zh, en, ja, auto)
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")
    
    # 在整个任务中保持应用上下文
    with app.app_context():
        try:
            # 重要：在后台线程开始时就获取task和设置状态
            task = Task.query.get(task_id)
            if not task:
                logger.error(f"Task {task_id} not found")
                return
            
            task.status = 'PROCESSING'
            db.session.commit()
            logger.info(f"Task {task_id} status updated to PROCESSING")
            
            # Flatten outline to get pages
            pages_data = ai_service.flatten_outline(outline)
            
            # Get all pages for this project
            pages = Page.query.filter_by(project_id=project_id).order_by(Page.order_index).all()
            
            if len(pages) != len(pages_data):
                raise ValueError("Page count mismatch")
            
            # Initialize progress
            task.set_progress({
                "total": len(pages),
                "completed": 0,
                "failed": 0
            })
            db.session.commit()
            
            # Generate descriptions in parallel
            completed = 0
            failed = 0
            
            def generate_single_desc(page_id, page_outline, page_index):
                """
                Generate description for a single page
                注意：只传递 page_id（字符串），不传递 ORM 对象，避免跨线程会话问题
                """
                # 关键修复：在子线程中也需要应用上下文
                with app.app_context():
                    try:
                        # Get singleton AI service instance
                        from services.ai_service_manager import get_ai_service
                        ai_service = get_ai_service()
                        
                        desc_text = ai_service.generate_page_description(
                            project_context, outline, page_outline, page_index,
                            language=language
                        )
                        
                        # Parse description into structured format
                        # This is a simplified version - you may want more sophisticated parsing
                        desc_content = {
                            "text": desc_text,
                            "generated_at": datetime.utcnow().isoformat()
                        }
                        
                        return (page_id, desc_content, None)
                    except Exception as e:
                        import traceback
                        error_detail = traceback.format_exc()
                        logger.error(f"Failed to generate description for page {page_id}: {error_detail}")
                        return (page_id, None, str(e))
            
            # Use ThreadPoolExecutor for parallel generation
            # 关键：提前提取 page.id，不要传递 ORM 对象到子线程
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(generate_single_desc, page.id, page_data, i)
                    for i, (page, page_data) in enumerate(zip(pages, pages_data), 1)
                ]
                
                # Process results as they complete
                for future in as_completed(futures):
                    page_id, desc_content, error = future.result()
                    
                    db.session.expire_all()
                    
                    # Update page in database
                    page = Page.query.get(page_id)
                    if page:
                        if error:
                            page.status = 'FAILED'
                            failed += 1
                        else:
                            page.set_description_content(desc_content)
                            page.status = 'DESCRIPTION_GENERATED'
                            completed += 1
                        
                        db.session.commit()
                    
                    # Update task progress
                    task = Task.query.get(task_id)
                    if task:
                        task.update_progress(completed=completed, failed=failed)
                        db.session.commit()
                        logger.info(f"Description Progress: {completed}/{len(pages)} pages completed")
            
            # Mark task as completed
            task = Task.query.get(task_id)
            if task:
                task.status = 'COMPLETED'
                task.completed_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"Task {task_id} COMPLETED - {completed} pages generated, {failed} failed")
            
            # Update project status
            from models import Project
            project = Project.query.get(project_id)
            if project and failed == 0:
                project.status = 'DESCRIPTIONS_GENERATED'
                db.session.commit()
                logger.info(f"Project {project_id} status updated to DESCRIPTIONS_GENERATED")
        
        except Exception as e:
            # Mark task as failed
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()


def generate_images_task(task_id: str, project_id: str, ai_service, file_service,
                        outline: List[Dict], use_template: bool = True, 
                        max_workers: int = 8, aspect_ratio: str = "16:9",
                        resolution: str = "2K", app=None,
                        extra_requirements: str = None,
                        language: str = None,
                        page_ids: list = None):
    """
    Background task for generating page images
    Based on demo.py gen_images_parallel()
    
    Note: app instance MUST be passed from the request context
    
    Args:
        language: Output language (zh, en, ja, auto)
        page_ids: Optional list of page IDs to generate (if not provided, generates all pages)
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")
    
    with app.app_context():
        try:
            # Update task status to PROCESSING
            task = Task.query.get(task_id)
            if not task:
                return
            
            task.status = 'PROCESSING'
            db.session.commit()
            
            # Get pages for this project (filtered by page_ids if provided)
            pages = get_filtered_pages(project_id, page_ids)
            pages_data = ai_service.flatten_outline(outline)
            
            # 注意：不在任务开始时获取模板路径，而是在每个子线程中动态获取
            # 这样可以确保即使用户在上传新模板后立即生成，也能使用最新模板
            
            # Initialize progress
            task.set_progress({
                "total": len(pages),
                "completed": 0,
                "failed": 0
            })
            db.session.commit()
            
            # Generate images in parallel
            completed = 0
            failed = 0
            
            def generate_single_image(page_id, page_data, page_index):
                """
                Generate image for a single page
                注意：只传递 page_id（字符串），不传递 ORM 对象，避免跨线程会话问题
                """
                # 关键修复：在子线程中也需要应用上下文
                with app.app_context():
                    try:
                        logger.debug(f"Starting image generation for page {page_id}, index {page_index}")
                        # Get page from database in this thread
                        page_obj = Page.query.get(page_id)
                        if not page_obj:
                            raise ValueError(f"Page {page_id} not found")
                        
                        # Update page status
                        page_obj.status = 'GENERATING'
                        db.session.commit()
                        logger.debug(f"Page {page_id} status updated to GENERATING")
                        
                        # Get description content
                        desc_content = page_obj.get_description_content()
                        if not desc_content:
                            raise ValueError("No description content for page")
                        
                        # 获取描述文本（可能是 text 字段或 text_content 数组）
                        desc_text = desc_content.get('text', '')
                        if not desc_text and desc_content.get('text_content'):
                            # 如果 text 字段不存在，尝试从 text_content 数组获取
                            text_content = desc_content.get('text_content', [])
                            if isinstance(text_content, list):
                                desc_text = '\n'.join(text_content)
                            else:
                                desc_text = str(text_content)
                        
                        logger.debug(f"Got description text for page {page_id}: {desc_text[:100]}...")
                        
                        # 从当前页面的描述内容中提取图片 URL
                        page_additional_ref_images = []
                        has_material_images = False
                        
                        # 从描述文本中提取图片
                        if desc_text:
                            image_urls = ai_service.extract_image_urls_from_markdown(desc_text)
                            if image_urls:
                                logger.info(f"Found {len(image_urls)} image(s) in page {page_id} description")
                                page_additional_ref_images = image_urls
                                has_material_images = True
                        
                        # 在子线程中动态获取模板路径，确保使用最新模板
                        page_ref_image_path = None
                        if use_template:
                            page_ref_image_path = file_service.get_template_path(project_id)
                            # 注意：如果有风格描述，即使没有模板图片也允许生成
                            # 这个检查已经在 controller 层完成，这里不再检查
                        
                        # Generate image prompt
                        prompt = ai_service.generate_image_prompt(
                            outline, page_data, desc_text, page_index,
                            has_material_images=has_material_images,
                            extra_requirements=extra_requirements,
                            language=language,
                            has_template=use_template
                        )
                        logger.debug(f"Generated image prompt for page {page_id}")
                        
                        # Generate image
                        logger.info(f"🎨 Calling AI service to generate image for page {page_index}/{len(pages)}...")
                        image = ai_service.generate_image(
                            prompt, page_ref_image_path, aspect_ratio, resolution,
                            additional_ref_images=page_additional_ref_images if page_additional_ref_images else None
                        )
                        logger.info(f"✅ Image generated successfully for page {page_index}")
                        
                        if not image:
                            raise ValueError("Failed to generate image")
                        
                        # Use configured image format
                        image_format = app.config.get('IMAGE_FORMAT', 'PNG')
                        
                        # 优化：直接在子线程中计算版本号并保存到最终位置
                        # 每个页面独立，使用数据库事务保证版本号原子性，避免临时文件
                        image_path, next_version = save_image_with_version(
                            image, project_id, page_id, file_service, page_obj=page_obj,
                            image_format=image_format
                        )
                        
                        return (page_id, image_path, None)
                        
                    except Exception as e:
                        import traceback
                        error_detail = traceback.format_exc()
                        logger.error(f"Failed to generate image for page {page_id}: {error_detail}")
                        return (page_id, None, str(e))
            
            # Use ThreadPoolExecutor for parallel generation
            # 关键：提前提取 page.id，不要传递 ORM 对象到子线程
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(generate_single_image, page.id, page_data, i)
                    for i, (page, page_data) in enumerate(zip(pages, pages_data), 1)
                ]
                
                # Process results as they complete
                for future in as_completed(futures):
                    page_id, image_path, error = future.result()
                    
                    db.session.expire_all()
                    
                    # Update page in database (主要是为了更新失败状态)
                    page = Page.query.get(page_id)
                    if page:
                        if error:
                            page.status = 'FAILED'
                            failed += 1
                            db.session.commit()
                        else:
                            # 图片已在子线程中保存并创建版本记录，这里只需要更新计数
                            completed += 1
                            # 刷新页面对象以获取最新状态
                            db.session.refresh(page)
                    
                    # Update task progress
                    task = Task.query.get(task_id)
                    if task:
                        task.update_progress(completed=completed, failed=failed)
                        db.session.commit()
                        logger.info(f"Image Progress: {completed}/{len(pages)} pages completed")
            
            # Mark task as completed
            task = Task.query.get(task_id)
            if task:
                task.status = 'COMPLETED'
                task.completed_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"Task {task_id} COMPLETED - {completed} images generated, {failed} failed")
            
            # Update project status
            from models import Project
            project = Project.query.get(project_id)
            if project and failed == 0:
                project.status = 'COMPLETED'
                db.session.commit()
                logger.info(f"Project {project_id} status updated to COMPLETED")
        
        except Exception as e:
            # Mark task as failed
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()


def generate_single_page_image_task(task_id: str, project_id: str, page_id: str, 
                                    ai_service, file_service, outline: List[Dict],
                                    use_template: bool = True, aspect_ratio: str = "16:9",
                                    resolution: str = "2K", app=None,
                                    extra_requirements: str = None,
                                    language: str = None):
    """
    Background task for generating a single page image
    
    Note: app instance MUST be passed from the request context
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")
    
    with app.app_context():
        try:
            # Update task status to PROCESSING
            task = Task.query.get(task_id)
            if not task:
                return
            
            task.status = 'PROCESSING'
            db.session.commit()
            
            # Get page from database
            page = Page.query.get(page_id)
            if not page or page.project_id != project_id:
                raise ValueError(f"Page {page_id} not found")
            
            # Update page status
            page.status = 'GENERATING'
            db.session.commit()
            
            # Get description content
            desc_content = page.get_description_content()
            if not desc_content:
                raise ValueError("No description content for page")
            
            # 获取描述文本（可能是 text 字段或 text_content 数组）
            desc_text = desc_content.get('text', '')
            if not desc_text and desc_content.get('text_content'):
                text_content = desc_content.get('text_content', [])
                if isinstance(text_content, list):
                    desc_text = '\n'.join(text_content)
                else:
                    desc_text = str(text_content)
            
            # 从描述文本中提取图片 URL
            additional_ref_images = []
            has_material_images = False
            
            if desc_text:
                image_urls = ai_service.extract_image_urls_from_markdown(desc_text)
                if image_urls:
                    logger.info(f"Found {len(image_urls)} image(s) in page {page_id} description")
                    additional_ref_images = image_urls
                    has_material_images = True
            
            # Get template path if use_template
            ref_image_path = None
            if use_template:
                ref_image_path = file_service.get_template_path(project_id)
                # 注意：如果有风格描述，即使没有模板图片也允许生成
                # 这个检查已经在 controller 层完成，这里不再检查
            
            # Generate image prompt
            page_data = page.get_outline_content() or {}
            if page.part:
                page_data['part'] = page.part
            
            prompt = ai_service.generate_image_prompt(
                outline, page_data, desc_text, page.order_index + 1,
                has_material_images=has_material_images,
                extra_requirements=extra_requirements,
                language=language,
                has_template=use_template
            )
            
            # Generate image
            logger.info(f"🎨 Generating image for page {page_id}...")
            image = ai_service.generate_image(
                prompt, ref_image_path, aspect_ratio, resolution,
                additional_ref_images=additional_ref_images if additional_ref_images else None
            )
            
            if not image:
                raise ValueError("Failed to generate image")
            
            # Use configured image format
            image_format = app.config.get('IMAGE_FORMAT', 'PNG')
            
            # 保存图片并创建历史版本记录
            image_path, next_version = save_image_with_version(
                image, project_id, page_id, file_service, page_obj=page,
                image_format=image_format
            )
            
            # Mark task as completed
            task.status = 'COMPLETED'
            task.completed_at = datetime.utcnow()
            task.set_progress({
                "total": 1,
                "completed": 1,
                "failed": 0
            })
            db.session.commit()
            
            logger.info(f"✅ Task {task_id} COMPLETED - Page {page_id} image generated")
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"Task {task_id} FAILED: {error_detail}")
            
            # Mark task as failed
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()
            
            # Update page status
            page = Page.query.get(page_id)
            if page:
                page.status = 'FAILED'
                db.session.commit()


def edit_page_image_task(task_id: str, project_id: str, page_id: str,
                         edit_instruction: str, ai_service, file_service,
                         aspect_ratio: str = "16:9", resolution: str = "2K",
                         original_description: str = None,
                         additional_ref_images: List[str] = None,
                         temp_dir: str = None, app=None):
    """
    Background task for editing a page image
    
    Note: app instance MUST be passed from the request context
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")
    
    with app.app_context():
        try:
            # Update task status to PROCESSING
            task = Task.query.get(task_id)
            if not task:
                return
            
            task.status = 'PROCESSING'
            db.session.commit()
            
            # Get page from database
            page = Page.query.get(page_id)
            if not page or page.project_id != project_id:
                raise ValueError(f"Page {page_id} not found")
            
            if not page.generated_image_path:
                raise ValueError("Page must have generated image first")
            
            # Update page status
            page.status = 'GENERATING'
            db.session.commit()
            
            # Get current image path
            current_image_path = file_service.get_absolute_path(page.generated_image_path)
            
            # Edit image
            logger.info(f"🎨 Editing image for page {page_id}...")
            try:
                image = ai_service.edit_image(
                    edit_instruction,
                    current_image_path,
                    aspect_ratio,
                    resolution,
                    original_description=original_description,
                    additional_ref_images=additional_ref_images if additional_ref_images else None
                )
            finally:
                # Clean up temp directory if created
                if temp_dir:
                    import shutil
                    from pathlib import Path
                    temp_path = Path(temp_dir)
                    if temp_path.exists():
                        shutil.rmtree(temp_dir)
            
            if not image:
                raise ValueError("Failed to edit image")
            
            # Use configured image format
            image_format = app.config.get('IMAGE_FORMAT', 'PNG')
            
            # 保存编辑后的图片并创建历史版本记录
            image_path, next_version = save_image_with_version(
                image, project_id, page_id, file_service, page_obj=page,
                image_format=image_format
            )
            
            # Mark task as completed
            task.status = 'COMPLETED'
            task.completed_at = datetime.utcnow()
            task.set_progress({
                "total": 1,
                "completed": 1,
                "failed": 0
            })
            db.session.commit()
            
            logger.info(f"✅ Task {task_id} COMPLETED - Page {page_id} image edited")
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"Task {task_id} FAILED: {error_detail}")
            
            # Clean up temp directory on error
            if temp_dir:
                import shutil
                from pathlib import Path
                temp_path = Path(temp_dir)
                if temp_path.exists():
                    shutil.rmtree(temp_dir)
            
            # Mark task as failed
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()
            
            # Update page status
            page = Page.query.get(page_id)
            if page:
                page.status = 'FAILED'
                db.session.commit()


def generate_material_image_task(task_id: str, project_id: str, prompt: str,
                                 ai_service, file_service,
                                 ref_image_path: str = None,
                                 additional_ref_images: List[str] = None,
                                 aspect_ratio: str = "16:9",
                                 resolution: str = "2K",
                                 temp_dir: str = None, app=None):
    """
    Background task for generating a material image
    复用核心的generate_image逻辑，但保存到Material表而不是Page表
    
    Note: app instance MUST be passed from the request context
    project_id can be None for global materials (but Task model requires a project_id,
    so we use a special value 'global' for task tracking)
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")
    
    with app.app_context():
        try:
            # Update task status to PROCESSING
            task = Task.query.get(task_id)
            if not task:
                return
            
            task.status = 'PROCESSING'
            db.session.commit()
            
            # Generate image (复用核心逻辑)
            logger.info(f"🎨 Generating material image with prompt: {prompt[:100]}...")
            image = ai_service.generate_image(
                prompt=prompt,
                ref_image_path=ref_image_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                additional_ref_images=additional_ref_images or None,
            )
            
            if not image:
                raise ValueError("Failed to generate image")
            
            # 处理project_id：如果为'global'或None，转换为None
            actual_project_id = None if (project_id == 'global' or project_id is None) else project_id
            
            # Save generated material image
            relative_path = file_service.save_material_image(image, actual_project_id)
            relative = Path(relative_path)
            filename = relative.name
            
            # Construct frontend-accessible URL
            image_url = file_service.get_file_url(actual_project_id, 'materials', filename)
            
            # Save material info to database
            material = Material(
                project_id=actual_project_id,
                filename=filename,
                relative_path=relative_path,
                url=image_url
            )
            db.session.add(material)
            
            # Mark task as completed
            task.status = 'COMPLETED'
            task.completed_at = datetime.utcnow()
            task.set_progress({
                "total": 1,
                "completed": 1,
                "failed": 0,
                "material_id": material.id,
                "image_url": image_url
            })
            db.session.commit()
            
            logger.info(f"✅ Task {task_id} COMPLETED - Material {material.id} generated")
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"Task {task_id} FAILED: {error_detail}")
            
            # Mark task as failed
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()
        
        finally:
            # Clean up temp directory
            if temp_dir:
                import shutil
                temp_path = Path(temp_dir)
                if temp_path.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)


def analyze_layout_task(
    task_id: str,
    project_id: str,
    page_ids: List[str] = None,
    extractor_method: str = 'hybrid',
    max_depth: int = 1,
    app=None
):
    """
    后台任务：对幻灯片进行版面分析（OCR）而不进行重绘
    结果将保存到 Page 模型的 layout_analysis 字段中
    任务完成后状态设为 WAITING_CONFIRMATION
    """
    logger.info(f"🚀 Task {task_id} started: analyze_layout (project={project_id})")

    if app is None:
        raise ValueError("Flask app instance must be provided")

    with app.app_context():
        import os
        from models import Project, Page, Task, db, Settings
        from services.image_editability import ServiceConfig, ImageEditabilityService
        from services.ai_service_manager import get_ai_service
        from services.file_service import FileService
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            # 更新任务状态
            task_obj = Task.query.get(task_id)
            if not task_obj:
                logger.error(f"Task {task_id} not found")
                return

            task_obj.status = 'PROCESSING'
            db.session.commit()

            # 获取项目和页面
            project = Project.query.get(project_id)
            pages = get_filtered_pages(project_id, page_ids)

            if not pages:
                raise ValueError("No pages found")

            # 初始化文件服务
            file_service = FileService(app.config.get('UPLOAD_FOLDER'))

            # 获取全局设置
            settings = Settings.get_settings()

            # 初始化服务
            ai_service = get_ai_service()
            from services.image_editability.factories import ServiceConfig
            config = ServiceConfig.from_defaults(
                mineru_token=settings.mineru_token,
                mineru_api_base=settings.mineru_api_base,
                upload_folder=app.config.get('UPLOAD_FOLDER'),
                ai_service=ai_service,
                extractor_method=extractor_method,
                max_depth=max_depth,
                use_local_ocr_inpaint=settings.use_local_ocr_inpaint,
                local_ocr_url=settings.local_ocr_url,
                local_inpaint_url=settings.local_inpaint_url
            )
            editability_service = ImageEditabilityService(config)

            total = len(pages)
            completed_count = 0

            task_obj.set_progress({
                "total": total,
                "completed": 0,
                "percent": 0,
                "current_step": "正在初始化..."
            })
            db.session.commit()

            def process_single_page(page_id):
                with app.app_context():
                    try:
                        page = Page.query.get(page_id)
                        if not page or not page.generated_image_path:
                            logger.warning(f"Page {page_id}: no generated_image_path")
                            return page_id, None, "No image path"

                        img_path = file_service.get_absolute_path(page.generated_image_path)
                        if not os.path.exists(img_path):
                            logger.warning(f"Page {page_id}: image file not found at {img_path}")
                            return page_id, None, "Image file not found"

                        logger.info(f"Page {page_id}: starting OCR analysis on {img_path}")

                        # 执行分析，传入空列表以跳过 Inpaint
                        editable_img = editability_service.make_image_editable(
                            image_path=img_path,
                            selected_element_ids=[]  # 空列表表示不进行任何重绘
                        )

                        if editable_img is None:
                            logger.error(f"Page {page_id}: make_image_editable returned None")
                            return page_id, None, "Analysis returned None"

                        # 保存结果
                        layout_dict = editable_img.to_dict()
                        page.set_layout_analysis(layout_dict)
                        # 默认全部保留（蓝色框），不擦除任何元素
                        # 用户需要主动点击选择要擦除的元素
                        page.set_confirmed_element_ids([])
                        db.session.commit()
                        element_count = len(layout_dict.get('elements', []))
                        logger.info(f"Page {page_id}: saved layout_analysis with {element_count} elements")
                        return page_id, True, None
                    except Exception as e:
                        logger.error(f"Page {page_id}: analysis failed - {e}", exc_info=True)
                        return page_id, None, str(e)

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(process_single_page, p.id): p.id for p in pages}
                errors = []
                for future in as_completed(futures):
                    page_id = futures[future]
                    try:
                        result_page_id, success, error_msg = future.result()
                        if not success:
                            errors.append(f"Page {result_page_id}: {error_msg}")
                    except Exception as e:
                        errors.append(f"Page {page_id}: {str(e)}")

                    completed_count += 1
                    task_obj = Task.query.get(task_id)
                    if task_obj:
                        task_obj.set_progress({
                            "total": total,
                            "completed": completed_count,
                            "percent": int(100 * completed_count / total),
                            "current_step": f"正在分析第 {completed_count}/{total} 页..."
                        })
                        db.session.commit()

                if errors:
                    logger.warning(f"Task {task_id}: some pages failed - {errors}")

            task_obj = Task.query.get(task_id)
            if task_obj:
                task_obj.status = 'WAITING_CONFIRMATION'
                task_obj.set_progress({
                    "total": total,
                    "completed": total,
                    "percent": 100,
                    "current_step": "分析完成，等待确认"
                })
                db.session.commit()
            logger.info(f"✓ Task {task_id} COMPLETED (Waiting for confirmation)")

        except Exception as e:
            logger.error(f"Layout analysis failed: {e}", exc_info=True)
            task_obj = Task.query.get(task_id)
            if task_obj:
                task_obj.status = 'FAILED'
                task_obj.error_message = str(e)
                db.session.commit()


def export_editable_pptx_with_recursive_analysis_task(
    task_id: str,
    project_id: str,
    filename: str,
    file_service,
    page_ids: list = None,
    max_depth: int = 2,
    max_workers: int = 4,
    export_extractor_method: str = 'hybrid',
    export_inpaint_method: str = 'hybrid',
    save_analysis: bool = False,
    use_confirmed_elements: bool = False,
    skip_ocr: bool = False,
    text_style_mode: str = 'local_cv',
    image_resolution: str = '1080p',
    image_format: str = 'PNG',
    app=None
):
    """
    使用递归图片可编辑化分析导出可编辑PPTX的后台任务

    Args:
        task_id: 任务ID
        project_id: 项目ID
        filename: 输出文件名
        file_service: 文件服务实例
        page_ids: 可选的页面ID列表（如果提供，只导出这些页面）
        max_depth: 最大递归深度
        max_workers: 并发处理数
        export_extractor_method: 组件提取方法 ('mineru' 或 'hybrid')
        export_inpaint_method: 背景修复方法 ('generative', 'baidu', 'hybrid')
        save_analysis: 是否保存分析结果到JSON文件
        use_confirmed_elements: 使用人工确认的元素列表
        skip_ocr: 跳过OCR（使用已有layout_analysis）
        text_style_mode: 样式提取模式 ('ai', 'local_cv', 'none')
        image_resolution: 背景图分辨率 ('720p', '1080p', '2K')
        image_format: 背景图格式 ('PNG', 'JPG', 'WEBP')
        app: Flask应用实例
    """
    logger.info(f"🚀 Task {task_id} started: export_editable_pptx_with_recursive_analysis (project={project_id}, depth={max_depth}, workers={max_workers}, extractor={export_extractor_method}, inpaint={export_inpaint_method}, save_analysis={save_analysis}, use_confirmed={use_confirmed_elements}, skip_ocr={skip_ocr}, text_style={text_style_mode})")

    if app is None:
        raise ValueError("Flask app instance must be provided")

    with app.app_context():
        import os
        import json
        from datetime import datetime
        from pathlib import Path
        from PIL import Image
        from models import Project, Page
        from services.export_service import ExportService
        from services.image_editability import ServiceConfig, ImageEditabilityService, TextAttributeExtractorFactory, EditableImage
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(f"开始递归分析导出任务 {task_id} for project {project_id}")

        try:
            # Get project
            project = Project.query.get(project_id)
            if not project:
                raise ValueError(f'Project {project_id} not found')

            # Get pages (filtered by page_ids if provided)
            pages = get_filtered_pages(project_id, page_ids)
            if not pages:
                raise ValueError('No pages found for project')

            image_paths = []
            for page in pages:
                if page.generated_image_path:
                    img_path = file_service.get_absolute_path(page.generated_image_path)
                    if os.path.exists(img_path):
                        image_paths.append(img_path)

            if not image_paths:
                raise ValueError('No generated images found for project')

            logger.info(f"找到 {len(image_paths)} 张图片")
            total_pages = len(image_paths)

            # 初始化任务进度（包含消息日志）
            task = Task.query.get(task_id)
            task.status = 'PROCESSING'
            task.set_progress({
                "total": 100,  # 使用百分比
                "completed": 0,
                "failed": 0,
                "current_step": "准备中...",
                "percent": 0,
                "messages": ["🚀 开始导出可编辑PPTX..."]  # 消息日志
            })
            db.session.commit()

            # 进度回调函数
            progress_messages = ["🚀 开始导出可编辑PPTX..."]
            max_messages = 10

            def progress_callback(step: str, message: str, percent: int):
                """更新任务进度到数据库"""
                nonlocal progress_messages
                try:
                    new_message = f"[{step}] {message}"
                    progress_messages.append(new_message)
                    if len(progress_messages) > max_messages:
                        progress_messages = progress_messages[-max_messages:]

                    task = Task.query.get(task_id)
                    if task:
                        task.set_progress({
                            "total": 100,
                            "completed": percent,
                            "failed": 0,
                            "current_step": message,
                            "percent": percent,
                            "messages": progress_messages.copy()
                        })
                        db.session.commit()
                except Exception as e:
                    logger.warning(f"更新进度失败: {e}")

            # Step 1: 准备工作
            logger.info("Step 1: 准备工作...")
            progress_callback("准备", f"找到 {len(image_paths)} 张幻灯片图片", 2)

            # 准备输出路径
            exports_dir = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'exports')
            os.makedirs(exports_dir, exist_ok=True)

            if not filename.endswith('.pptx'):
                filename += '.pptx'

            output_path = os.path.join(exports_dir, filename)
            if os.path.exists(output_path):
                base_name = filename.rsplit('.', 1)[0]
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"{base_name}_{timestamp}.pptx"
                output_path = os.path.join(exports_dir, filename)

            # 获取参考尺寸
            first_img = Image.open(image_paths[0])
            slide_width, slide_height = first_img.size
            first_img.close()

            # 获取全局设置
            settings = Settings.get_settings()

            # 初始化AI服务
            ai_service = AIService()

            # Step 2: 执行分析或使用已有分析
            if skip_ocr and use_confirmed_elements:
                # 使用已有的 layout_analysis 和 confirmed_element_ids
                logger.info("Step 2: 使用已有分析结果...")
                progress_callback("分析", "使用已有分析结果...", 5)

                editable_images = []
                for idx, page in enumerate(pages):
                    layout_data = page.get_layout_analysis()
                    if layout_data:
                        # 从保存的数据重建 EditableImage
                        editable_img = EditableImage.from_dict(layout_data)
                        editable_images.append(editable_img)
                    else:
                        # 如果没有分析数据，跳过这个页面
                        editable_images.append(None)
                    progress_callback("分析", f"已加载第 {idx+1}/{total_pages} 页分析结果", 5 + int(5 * (idx+1) / total_pages))

                # 根据 confirmed_element_ids 执行 inpaint（只处理用户确认的元素）
                logger.info("Step 2.5: 根据确认元素执行 Inpaint...")
                progress_callback("重绘", "根据确认元素执行背景重绘...", 12)

                # 初始化服务配置
                from services.image_editability.factories import ServiceConfig
                config = ServiceConfig.from_defaults(
                    mineru_token=settings.mineru_token,
                    mineru_api_base=settings.mineru_api_base,
                    upload_folder=app.config.get('UPLOAD_FOLDER'),
                    ai_service=ai_service,
                    extractor_method=export_extractor_method,
                    inpaint_method=export_inpaint_method,
                    max_depth=max_depth,
                    use_local_ocr_inpaint=settings.use_local_ocr_inpaint,
                    local_ocr_url=settings.local_ocr_url,
                    local_inpaint_url=settings.local_inpaint_url
                )
                editability_service = ImageEditabilityService(config)

                # 对每个页面执行 inpaint（使用新方法，不重新 OCR）
                completed_count = 0
                for idx, (page, editable_img) in enumerate(zip(pages, editable_images)):
                    if editable_img is None:
                        completed_count += 1
                        continue

                    confirmed_ids = page.get_confirmed_element_ids()
                    # 使用新方法处理：会过滤元素列表，只保留确认的元素
                    # 如果没有确认的元素，元素列表会被清空，不会生成文本框
                    img_path = image_paths[idx]
                    logger.info(f"Page {page.id}: processing with {len(confirmed_ids)} confirmed elements")
                    editable_img = editability_service.inpaint_with_existing_analysis(
                        image_path=img_path,
                        editable_image=editable_img,
                        selected_element_ids=confirmed_ids
                    )
                    editable_images[idx] = editable_img

                    completed_count += 1
                    percent = 12 + int(28 * completed_count / total_pages)
                    progress_callback("重绘", f"已处理第 {completed_count}/{total_pages} 页", percent)

            else:
                # 正常流程：执行完整分析
                logger.info(f"Step 2: 执行图片分析 (extractor={export_extractor_method}, inpaint={export_inpaint_method})...")
                progress_callback("分析", "初始化分析服务...", 5)

                # 初始化服务配置
                from services.image_editability.factories import ServiceConfig
                config = ServiceConfig.from_defaults(
                    mineru_token=settings.mineru_token,
                    mineru_api_base=settings.mineru_api_base,
                    upload_folder=app.config.get('UPLOAD_FOLDER'),
                    ai_service=ai_service,
                    extractor_method=export_extractor_method,
                    inpaint_method=export_inpaint_method,
                    max_depth=max_depth,
                    use_local_ocr_inpaint=settings.use_local_ocr_inpaint,
                    local_ocr_url=settings.local_ocr_url,
                    local_inpaint_url=settings.local_inpaint_url
                )
                editability_service = ImageEditabilityService(config)

                editable_images = [None] * total_pages
                completed_count = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(editability_service.make_image_editable, img_path): idx
                        for idx, img_path in enumerate(image_paths)
                    }

                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            result = future.result()
                            editable_images[idx] = result
                            completed_count += 1
                            # 分析占 5% - 40% 的进度
                            percent = 5 + int(35 * completed_count / total_pages)
                            progress_callback("分析", f"已分析第 {completed_count}/{total_pages} 页", percent)
                        except Exception as e:
                            logger.error(f"处理图片 {image_paths[idx]} 失败: {e}")
                            raise
            
            # Step 2.5: 保存分析结果
            if save_analysis:
                logger.info("Step 2.5: 保存分析结果...")
                progress_callback("保存", "正在保存分析结果...", 42)
                analysis_dir = Path(app.config['UPLOAD_FOLDER']) / project_id / 'analysis'
                analysis_dir.mkdir(parents=True, exist_ok=True)
                
                for i, (page, editable_img) in enumerate(zip(pages, editable_images)):
                    if not editable_img: continue
                    try:
                        analysis_file = analysis_dir / f"{page.id}_analysis.json"
                        with open(analysis_file, 'w', encoding='utf-8') as f:
                            json.dump(editable_img.to_dict(), f, ensure_ascii=False, indent=2)
                        logger.info(f"Saved analysis for page {page.id} to {analysis_file}")
                    except Exception as e:
                        logger.error(f"Failed to save analysis for page {page.id}: {e}")

            # Step 3: 创建文字属性提取器
            # 使用任务参数中的模式配置（优先于全局配置）

            # 使用 Registry 工厂方法创建
            registry = TextAttributeExtractorFactory.create_text_attribute_registry(
                ai_service=ai_service,
                mode=text_style_mode  # 使用任务参数
            )
            
            # 由于 ExportService 目前接受 TextAttributeExtractor 接口而不是 Registry，
            # 我们暂时传递默认提取器。
            # TODO: 升级 ExportService 以支持 Registry
            text_attribute_extractor = registry.get_extractor(None)
            
            # Step 4: 生成PPTX
            logger.info("Step 4: 生成PPTX...")
            progress_callback("生成", "开始构建PPTX文件...", 45)
            
            # 调用ExportService，传入已分析的editable_images
            _, export_warnings = ExportService.create_editable_pptx_with_recursive_analysis(
                image_paths=None, # 已提供editable_images，无需重新分析
                editable_images=editable_images,
                output_file=output_path,
                slide_width_pixels=slide_width,
                slide_height_pixels=slide_height,
                max_depth=max_depth,
                max_workers=max_workers,
                text_attribute_extractor=text_attribute_extractor,
                progress_callback=progress_callback,
                export_extractor_method=export_extractor_method,
                export_inpaint_method=export_inpaint_method
            )
            
            logger.info(f"✓ 可编辑PPTX已创建: {output_path}")
            
            # Step 5: 标记任务完成
            download_path = f"/files/{project_id}/exports/{filename}"
            progress_messages.append("✅ 导出完成！")
            
            warning_messages = []
            if export_warnings and export_warnings.has_warnings():
                warning_messages = export_warnings.to_summary()
                progress_messages.extend(warning_messages)
            
            task = Task.query.get(task_id)
            if task:
                task.status = 'COMPLETED'
                task.completed_at = datetime.utcnow()
                task.set_progress({
                    "total": 100,
                    "completed": 100,
                    "failed": 0,
                    "current_step": "✓ 导出完成",
                    "percent": 100,
                    "messages": progress_messages,
                    "download_url": download_path,
                    "filename": filename,
                    "method": "recursive_analysis",
                    "max_depth": max_depth,
                    "warnings": warning_messages,
                    "warning_details": export_warnings.to_dict() if export_warnings else {}
                })
                db.session.commit()
                logger.info(f"✓ 任务 {task_id} 完成")
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"✗ 任务 {task_id} 失败: {error_detail}")
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()


def reconstruct_pdf_pages_task(
    task_id: str,
    project_id: str,
    page_ids: List[str],
    style_prompt: str,
    ai_service,
    file_service,
    aspect_ratio: str = "16:9",
    resolution: str = "2K",
    export_options: Dict = None,
    app=None
):
    """
    Background task for reconstructing PDF pages using AI generation and optionally exporting
    """
    if app is None:
        raise ValueError("Flask app instance must be provided")

    with app.app_context():
        import os
        try:
            task = Task.query.get(task_id)
            if not task:
                return
            
            task.status = 'PROCESSING'
            reconstruct_weight = 50 if export_options else 100
            
            task.set_progress({
                "total": 100,
                "completed": 0,
                "failed": 0,
                "current_step": "正在重构页面...",
                "percent": 0
            })
            db.session.commit()
            
            completed = 0
            failed = 0
            total_pages = len(page_ids)
            
            max_workers = 4
            
            def process_page(page_id):
                with app.app_context():
                    try:
                        page = Page.query.get(page_id)
                        if not page:
                            return False, f"Page {page_id} not found"
                        
                        original_version = PageImageVersion.query.filter_by(
                            page_id=page_id, 
                            version_number=1
                        ).first()
                        
                        ref_image_path = None
                        if original_version and original_version.image_path:
                            abs_path = file_service.get_absolute_path(original_version.image_path)
                            if os.path.exists(abs_path):
                                ref_image_path = abs_path
                        
                        if not ref_image_path and page.generated_image_path:
                            abs_path = file_service.get_absolute_path(page.generated_image_path)
                            if os.path.exists(abs_path):
                                ref_image_path = abs_path
                        
                        if not ref_image_path:
                            return False, "Original reference image not found"
                        
                        prompt = f"Redesign this presentation slide. Keep the content and layout structure but apply the following style:\n\n{style_prompt}\n\nMake it professional and visually appealing."
                        
                        image = ai_service.generate_image(
                            prompt=prompt,
                            ref_image_path=ref_image_path,
                            aspect_ratio=aspect_ratio,
                            resolution=resolution
                        )
                        
                        if not image:
                            return False, "Image generation failed"
                        
                        image_format = app.config.get('IMAGE_FORMAT', 'PNG')
                        save_image_with_version(
                            image, project_id, page_id, file_service, page_obj=page,
                            image_format=image_format
                        )
                        
                        return True, None
                        
                    except Exception as e:
                        logger.error(f"Failed to reconstruct page {page_id}: {e}")
                        return False, str(e)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_page, pid): pid for pid in page_ids}
                
                for future in as_completed(futures):
                    pid = futures[future]
                    success, error = future.result()
                    
                    if success:
                        completed += 1
                    else:
                        failed += 1
                    
                    percent = int((completed / total_pages) * reconstruct_weight)
                    task.set_progress({
                        "total": 100,
                        "completed": percent,
                        "failed": failed,
                        "current_step": f"重构页面 {completed}/{total_pages}",
                        "percent": percent
                    })
                    db.session.commit()
            
            if export_options and failed < total_pages:
                from services.export_service import ExportService
                from services.image_editability import ServiceConfig, ImageEditabilityService, TextAttributeExtractorFactory
                
                filename = export_options.get('filename', f'reconstructed_{project_id}.pptx')
                exports_dir = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'exports')
                os.makedirs(exports_dir, exist_ok=True)
                output_path = os.path.join(exports_dir, filename)
                
                current_image_paths = []
                pages = get_filtered_pages(project_id, page_ids)
                for page in pages:
                    if page.generated_image_path:
                        img_path = file_service.get_absolute_path(page.generated_image_path)
                        if os.path.exists(img_path):
                            current_image_paths.append(img_path)
                
                def export_progress_callback(step: str, message: str, p: int):
                    actual_percent = reconstruct_weight + int(p * (100 - reconstruct_weight) / 100)
                    task.set_progress({
                        "total": 100,
                        "completed": actual_percent,
                        "failed": failed,
                        "current_step": f"导出: {message}",
                        "percent": actual_percent
                    })
                    db.session.commit()
                
                config = ServiceConfig.from_defaults(
                    upload_folder=app.config.get('UPLOAD_FOLDER'),
                    extractor_method=export_options.get('export_extractor_method', 'hybrid'),
                    inpaint_method=export_options.get('export_inpaint_method', 'hybrid'),
                    max_depth=export_options.get('max_depth', 2),
                    use_local_ocr_inpaint=app.config.get('USE_LOCAL_OCR_INPAINT', False),
                    local_ocr_url=app.config.get('LOCAL_OCR_URL'),
                    local_inpaint_url=app.config.get('LOCAL_INPAINT_URL')
                )
                editability_service = ImageEditabilityService(config)
                
                editable_images = [None] * len(current_image_paths)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(editability_service.make_image_editable, img_path): idx
                        for idx, img_path in enumerate(current_image_paths)
                    }
                    
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            editable_images[idx] = future.result()
                        except Exception as e:
                            logger.error(f"Analysis failed for {current_image_paths[idx]}: {e}")
                
                text_style_mode = app.config.get('TEXT_STYLE_EXTRACTION_MODE', 'local_cv')
                registry = TextAttributeExtractorFactory.create_text_attribute_registry(
                    ai_service=ai_service,
                    mode=text_style_mode
                )
                text_attribute_extractor = registry.get_extractor(None)
                
                _, export_warnings = ExportService.create_editable_pptx_with_recursive_analysis(
                    image_paths=None,
                    editable_images=editable_images,
                    output_file=output_path,
                    text_attribute_extractor=text_attribute_extractor,
                    progress_callback=export_progress_callback
                )
                
                download_path = f"/files/{project_id}/exports/{filename}"
                task.set_progress({
                    "total": 100,
                    "completed": 100,
                    "failed": failed,
                    "current_step": "✓ 完成",
                    "percent": 100,
                    "download_url": download_path,
                    "filename": filename
                })
                db.session.commit()
            
            task.status = 'COMPLETED'
            task.completed_at = datetime.utcnow()
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            task = Task.query.get(task_id)
            if task:
                task.status = 'FAILED'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()
