<div align="center">

# 🍌 蕉幻 (Banana Slides)

一个基于nano banana pro的智能PPT生成工具，支持一句话生成完整PPT演示文稿，自然语言直接修改ppt页面，实现“Vibe PPT”

<p>
  <a href="https://github.com/your-username/banana-slides/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React-18-blue?logo=react&logoColor=61DAFB" alt="React">
  <img src="https://img.shields.io/badge/Flask-3.0-lightgrey?logo=flask&logoColor=black" alt="Flask">
  <img src="https://img.shields.io/badge/TypeScript--blue?logo=typescript&logoColor=white" alt="TypeScript">
  <a href="https://gemini.google.com/">
    <img src="https://img.shields.io/badge/Powered_by-Gemini_AI-4A89F3?logo=google-gemini" alt="Powered by Gemini">
  </a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome">
</p>

<img src="https://github.com/user-attachments/assets/7ddb6079-1633-456c-a933-e27a7f6e8c5c">

</div>




<img width="2086" height="1866" alt="image" src="https://github.com/user-attachments/assets/45283476-afb7-4aff-8154-15a0c0bc9174" />

## ✨ 项目简介

蕉幻（Banana Slides）是一个 AI 原生的 PPT 生成应用，它利用大语言模型和文生图模型来自动化 PPT 制作流程。用户只需要提供一个简单的想法或大纲，系统就能自动生成包含精美设计的完整 PPT

### 核心亮点

- 🚀 **一句话生成PPT**：从一个简单的想法快速生成完整的演示文稿
- 🎨 **风格模板支持**：支持上传参考图片，生成的PPT将保持统一的设计风格
- ⚡ **并行化处理**：多线程并行生成PPT页面，大幅提升生成速度
- 🔄 **灵活的生成路径**：支持从构想、大纲或详细描述三种方式生成PPT
- 📝 **智能内容生成**：基于LLM自动生成大纲和页面内容描述
- 🖼️ **高质量图片生成**：利用Gemini AI生成4K分辨率、16:9比例的专业设计
- 📊 **完整的PPT导出**：自动组合生成的图片页面并导出为标准PPTX文件
- 🎯 **拖拽式编辑**：直观的大纲和描述编辑界面，支持拖拽排序
- ✏️ **灵活修改**：支持对单页PPT进行自然语言编辑和重新生成

## 🎯 主要功能

### 1. 多种创建方式
- **从构想生成**：输入一句话描述，AI自动生成完整大纲和内容
- **从大纲生成**：粘贴已有大纲，AI辅助扩展为详细描述
- **从描述生成**：直接提供每页描述，快速生成图片

### 2. 智能大纲生成
- 根据用户输入的主题自动生成PPT大纲
- 支持简单格式和分章节格式两种组织方式
- 可视化卡片编辑，支持拖拽排序
- 实时编辑和调整内容

### 3. 页面描述生成
- 为每一页PPT生成详细的文字描述
- 包含标题、要点、排版建议等完整信息
- 并行化处理，快速生成多页内容
- 支持单页和批量生成

### 4. 图片生成与设计
- 基于页面描述自动生成图片提示词
- 使用Gemini AI的图像生成能力创建精美页面
- 支持参考图片以保持风格一致性
- 并行生成所有页面，提高效率
- 支持单页自然语言编辑和重新生成

### 5. 模板管理
- 上传自定义风格模板
- 模板自动应用到所有页面
- 保持PPT风格一致性

### 6. 多格式导出
- **PPTX导出**：标准PowerPoint格式，可进一步编辑
- **PDF导出**：便于分享和打印
- 16:9比例，高质量输出

## 🛠️ 技术架构

### 前端技术栈
- **框架**：React 18 + TypeScript
- **构建工具**：Vite 5
- **状态管理**：Zustand
- **路由**：React Router v6
- **UI组件**：Tailwind CSS
- **拖拽功能**：@dnd-kit
- **图标**：Lucide React
- **HTTP客户端**：Axios

### 后端技术栈
- **语言**：Python 3.10+
- **框架**：Flask 3.0
- **包管理**：uv
- **数据库**：SQLite + Flask-SQLAlchemy
- **AI能力**：Google Gemini API
- **PPT处理**：python-pptx
- **图片处理**：Pillow
- **并发处理**：ThreadPoolExecutor
- **跨域支持**：Flask-CORS

### 项目架构

```
banana-slides/
├── frontend/              # React前端
│   ├── src/
│   │   ├── pages/        # 页面组件
│   │   ├── components/   # UI组件
│   │   ├── store/        # Zustand状态管理
│   │   ├── api/          # API接口
│   │   └── types/        # TypeScript类型
│   └── package.json
│
├── backend/              # Flask后端
│   ├── app.py           # 应用入口
│   ├── models/          # 数据模型
│   ├── services/        # 业务逻辑
│   ├── controllers/     # API控制器
│   ├── utils/           # 工具函数
│   └── requirements.txt
│
└── docs/                # 文档
    ├── PRD.md
    ├── API设计文档.md
    └── 快速启动指南.md
```

## 📦 安装说明

### 环境要求
- Python 3.10 或更高版本
- Node.js 16+ 和 npm
- 有效的 Google Gemini API 密钥

### 后端安装

1. **进入后端目录**
```bash
cd backend
```

2. **安装依赖**

使用 pip：
```bash
pip install -r requirements.txt
```

或使用 uv（推荐）：
```bash
uv pip install -r requirements.txt
```

3. **配置环境变量**

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置你的 API 密钥：
```env
GOOGLE_API_KEY=your-api-key-here
GOOGLE_API_BASE=https://generativelanguage.googleapis.com
PORT=5000
```

### 前端安装

1. **进入前端目录**
```bash
cd frontend
```

2. **安装依赖**
```bash
npm install
```

3. **配置API地址**

前端会自动连接到 `http://localhost:5000` 的后端服务。如需修改，请编辑 `src/api/client.ts`。

## 🚀 快速开始

### 启动后端服务

```bash
cd backend
python app.py
```

后端服务将在 `http://localhost:5000` 启动。

访问 `http://localhost:5000/health` 验证服务是否正常运行。

### 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端开发服务器将在 `http://localhost:5173` 启动。

打开浏览器访问即可使用应用。

### 快速测试

**方式一：使用Web界面**

1. 打开浏览器访问 `http://localhost:5173`
2. 选择 "一句话生成PPT"
3. 输入你的想法，例如："生成一份关于人工智能发展历程的PPT"
4. 上传风格模板（可选）
5. 查看生成的大纲，可拖拽调整顺序
6. 点击生成页面描述
7. 点击生成PPT图片
8. 导出为PPTX或PDF

**方式二：使用API测试**

```bash
cd backend
python test_api.py
```

或使用 curl 命令：

```bash
# 创建项目
curl -X POST http://localhost:5000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"creation_type":"idea","idea_prompt":"生成一份关于环保的PPT"}'

# 记录返回的 project_id，然后继续后续步骤
```

完整的API测试流程请参考 [快速启动指南](快速启动指南.md)。

## 📁 项目结构

```
banana-slides/
├── frontend/                    # React前端应用
│   ├── src/
│   │   ├── pages/              # 页面组件
│   │   │   ├── Home.tsx        # 首页（创建项目）
│   │   │   ├── OutlineEditor.tsx    # 大纲编辑页
│   │   │   ├── DescriptionEditor.tsx # 描述编辑页
│   │   │   └── Preview.tsx     # 预览和导出页
│   │   ├── components/         # UI组件
│   │   │   ├── outline/        # 大纲相关组件
│   │   │   ├── description/    # 描述相关组件
│   │   │   └── common/         # 通用组件
│   │   ├── store/              # Zustand状态管理
│   │   │   └── useProjectStore.ts
│   │   ├── api/                # API接口
│   │   │   ├── client.ts       # Axios客户端配置
│   │   │   └── endpoints.ts    # API端点
│   │   ├── types/              # TypeScript类型定义
│   │   └── utils/              # 工具函数
│   ├── public/                 # 静态资源
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                    # Flask后端应用
│   ├── app.py                  # Flask应用入口
│   ├── config.py               # 配置文件
│   ├── requirements.txt        # Python依赖
│   ├── models/                 # 数据库模型
│   │   ├── project.py          # Project模型
│   │   ├── page.py             # Page模型
│   │   └── task.py             # Task模型
│   ├── services/               # 服务层
│   │   ├── ai_service.py       # AI服务（基于demo.py）
│   │   ├── file_service.py     # 文件管理
│   │   ├── export_service.py   # PPTX/PDF导出
│   │   └── task_manager.py     # 异步任务管理
│   ├── controllers/            # API控制器
│   │   ├── project_controller.py
│   │   ├── page_controller.py
│   │   ├── template_controller.py
│   │   ├── export_controller.py
│   │   └── file_controller.py
│   ├── utils/                  # 工具函数
│   │   ├── response.py         # 统一响应格式
│   │   └── validators.py       # 数据验证
│   └── instance/               # SQLite数据库（自动生成）
│
├── uploads/                    # 文件上传目录
│   └── {project_id}/
│       ├── template/           # 模板图片
│       └── pages/              # 生成的PPT页面图片
│
├── docs/                       # 文档
│   ├── PRD.md                  # 产品需求文档
│   ├── API设计文档.md          # API详细文档
│   ├── 快速启动指南.md         # 快速上手指南
│   ├── 后端测试报告.md         # 测试报告
│   └── 项目交付总结.md         # 交付总结
│
├── demo.py                     # 原始demo（已集成到后端）
├── gemini_genai.py             # Gemini API封装（已集成）
├── pyproject.toml              # Python项目配置
├── uv.lock                     # uv依赖锁定
├── LICENSE                     # MIT许可证
└── README.md                   # 本文件
```


## 🤝 贡献指南

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT

## 📞 联系方式

如有问题或建议，欢迎通过Issue反馈。



