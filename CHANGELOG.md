# 修改日志

本项目的所有重要修改都将记录在此文件中。

## [未发布] - 2026-01-20

### 新增
- **可编辑 PPT 导出增强**:
  - 新增 `docs/make_editable_ppt.md` 技术文档，详细说明生成原理及 MinerU/百度 OCR 的作用。
  - 后端 `export_editable_pptx` 接口支持 `extractor_method` (mineru/hybrid) 和 `inpaint_method` (baidu/generative/hybrid) 参数。
  - 前端新增导出设置弹窗，允许用户在导出时选择版面分析模式和背景修复模式。
- **页面导入**:
  - 后端新增 `POST /api/projects/{project_id}/pages/import-image` 接口，支持将单张图片导入为项目页面。
- **图片转可编辑 PPT (批量)**:
  - 后端新增 `POST /api/projects/{project_id}/convert-images` 接口，支持批量上传图片并直接转换为可编辑 PPTX。
  - 支持自动触发 MinerU/百度 OCR 分析，并保存分析结果（JSON + 分解图片）以供后续查看。
  - 任务完成后提供 PPTX 下载链接。

### 变更
- **项目维护**:
  - 初始化 `CHANGELOG.md` 文件以跟踪版本变更。
  - 将 Git 远程仓库从上游更新为 `https://github.com/tangtangniuniu/banana-slides`。
  - 同步上游 `main` 分支的最新更改，并解决了与本地修改产生的冲突，主要涉及：
    - `backend/controllers/settings_controller.py`
    - `frontend/src/pages/Settings.tsx`
  - 将本地的所有修改成功推送到新的远程仓库。
