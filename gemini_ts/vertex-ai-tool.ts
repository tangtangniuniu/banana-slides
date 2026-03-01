import { VertexAI, GenerativeModel, Part } from '@google-cloud/vertexai';
import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { ProxyAgent, setGlobalDispatcher } from 'undici';

// Load environment variables
dotenv.config();
// Try loading from parent directory if not found or specific vars are missing
if (!process.env.VERTEX_PROJECT_ID && !process.env.GOOGLE_APPLICATION_CREDENTIALS) {
  const parentEnvPath = path.resolve(process.cwd(), '..', '.env');
  if (fs.existsSync(parentEnvPath)) {
    dotenv.config({ path: parentEnvPath });
  }
}

// Configure proxy if available
const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxyUrl) {
  const dispatcher = new ProxyAgent(proxyUrl);
  setGlobalDispatcher(dispatcher);
  console.log(`Using proxy: ${proxyUrl}`);
}

/**
 * 独立的 Vertex AI 调用工具类
 * 支持文本大模型和图像大模型的调用
 */
export class VertexAITool {
  private project_id: string;
  private location: string;
  private credentials_path: string | undefined;
  private text_model_name: string;
  private image_model_name: string;
  private timeout: number;
  private max_retries: number;
  private vertex_ai: VertexAI;
  private text_model: GenerativeModel;
  private image_model: GenerativeModel;

  /**
   * 初始化 Vertex AI 工具类
   * 
   * @param config 配置对象
   */
  constructor(config: {
    project_id?: string;
    location?: string;
    credentials_path?: string;
    text_model?: string;
    image_model?: string;
    timeout?: number;
    max_retries?: number;
  } = {}) {
    this.project_id = config.project_id || process.env.VERTEX_PROJECT_ID || '';
    this.location = config.location || process.env.VERTEX_LOCATION || 'us-central1';
    this.credentials_path = config.credentials_path || process.env.GOOGLE_APPLICATION_CREDENTIALS;
    this.text_model_name = config.text_model || process.env.TEXT_MODEL || 'gemini-3-flash-preview';
    this.image_model_name = config.image_model || process.env.IMAGE_MODEL || 'gemini-3-pro-image-preview';
    this.timeout = config.timeout || 300;
    this.max_retries = config.max_retries || 2;

    // 自动纠正不支持的 location
    if (this.location === 'global') {
      console.warn("⚠️ Warning: 'global' location is not supported for Vertex AI GenAI models. Automatically switching to 'us-central1'.");
      this.location = 'us-central1';
    }

    // 打印调试信息
    console.log("--- Vertex AI Configuration ---");
    console.log(`Project ID: ${this.project_id}`);
    console.log(`Location: ${this.location}`);
    console.log(`Credentials: ${this.credentials_path || 'Not set (using default/ADC)'}`);
    console.log(`Text Model: ${this.text_model_name}`);
    console.log(`Image Model: ${this.image_model_name}`);
    console.log("-------------------------------");

    if (!this.project_id) {
      console.warn("⚠️ Warning: Project ID is not set. API calls will likely fail.");
      console.warn("Please set VERTEX_PROJECT_ID in your .env file.");
    }

    if (this.credentials_path) {
      process.env.GOOGLE_APPLICATION_CREDENTIALS = this.credentials_path;
    }

    // 初始化 Vertex AI Client
    this.vertex_ai = new VertexAI({
      project: this.project_id,
      location: this.location,
    });

    // 初始化模型实例
    this.text_model = this.vertex_ai.getGenerativeModel({
      model: this.text_model_name,
    });
    
    this.image_model = this.vertex_ai.getGenerativeModel({
      model: this.image_model_name,
    });
  }

  /**
   * 简单的重试包装器
   */
  private async withRetry<T>(fn: () => Promise<T>, retries: number = 3): Promise<T> {
    let lastError: any;
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error;
        const delay = Math.pow(2, i) * 1000;
        console.warn(`Attempt ${i + 1} failed, retrying in ${delay}ms...`, error);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    throw lastError;
  }

  /**
   * 使用 Vertex AI 文本模型生成文本
   * 
   * @param prompt 输入提示词
   * @param thinking_budget 推理预算（0 表示禁用推理模式）
   * @returns 生成的文本
   */
  async generateText(prompt: string, thinking_budget: number = 0): Promise<string> {
    return this.withRetry(async () => {
      // 当前 SDK 可能还不支持 thinkingConfig，但我们可以尝试作为 generationConfig 传入
      // 或者如果不支持，就忽略它。
      // 注意：Node SDK 对于特定 beta 功能的支持可能滞后。
      // 这里暂时只传 prompt。
      
      const request: any = {
        contents: [{ role: 'user', parts: [{ text: prompt }] }]
      };

      if (thinking_budget > 0) {
        // 尝试添加 thinking_config (如果 SDK 支持的话，否则可能会被忽略或报错)
        // 目前看来 Node SDK 的 generationConfig 类型中还没有 thinkingConfig
        // 我们暂时先跳过 thinking_budget 的设置，以免出错
        console.warn("Thinking budget is not yet fully supported in this Node.js SDK wrapper.");
      }

      const result = await this.text_model.generateContent(request);
      const response = await result.response;
      
      if (!response.candidates || response.candidates.length === 0) {
        throw new Error("No candidates returned");
      }
      
      const textPart = response.candidates[0].content.parts.find(p => p.text);
      return textPart ? textPart.text || '' : '';
    });
  }

  /**
   * 使用 Vertex AI 文本模型生成文本（支持图像输入）
   * 
   * @param prompt 输入提示词
   * @param imagePath 图像文件路径
   * @param thinking_budget 推理预算（0 表示禁用推理模式）
   * @returns 生成的文本
   */
  async generateWithImage(prompt: string, imagePath: string, thinking_budget: number = 0): Promise<string> {
    return this.withRetry(async () => {
      const imageBuffer = fs.readFileSync(imagePath);
      const base64Image = imageBuffer.toString('base64');
      const mimeType = this.getMimeType(imagePath);

      const request: any = {
        contents: [{
          role: 'user',
          parts: [
            { inlineData: { data: base64Image, mimeType: mimeType } },
            { text: prompt }
          ]
        }]
      };

      const result = await this.text_model.generateContent(request);
      const response = await result.response;

      if (!response.candidates || response.candidates.length === 0) {
        throw new Error("No candidates returned");
      }

      const textPart = response.candidates[0].content.parts.find(p => p.text);
      return textPart ? textPart.text || '' : '';
    });
  }

  /**
   * 使用 Vertex AI 图像模型生成图像
   * 
   * @param prompt 图像生成提示词
   * @param refImages 参考图像路径列表 (Buffer 或 Base64)
   * @param aspect_ratio 图像比例
   * @param resolution 图像分辨率
   * @param enable_thinking 是否启用推理模式
   * @param thinking_budget 推理预算
   * @returns 生成的图像 Buffer，失败返回 null
   */
  async generateImage(
    prompt: string,
    refImages?: string[],
    aspect_ratio: string = "16:9",
    resolution: string = "2K",
    enable_thinking: boolean = true,
    thinking_budget: number = 1024
  ): Promise<Buffer | null> {
    return this.withRetry(async () => {
      try {
        const parts: Part[] = [];

        if (refImages) {
          for (const imgPath of refImages) {
            const imageBuffer = fs.readFileSync(imgPath);
            parts.push({
              inlineData: {
                data: imageBuffer.toString('base64'),
                mimeType: this.getMimeType(imgPath)
              }
            });
          }
        }

        parts.push({ text: prompt });

        // 构建请求配置
        // 注意：Node SDK 中 imageConfig 的支持情况可能与 Python 不同
        // 这里尝试构造类似 Python 的配置结构，但可能需要调整
        const generationConfig: any = {
           // 这里我们假设 SDK 会透传这些配置
           // 但实际上 @google-cloud/vertexai 的类型定义可能比较严格
           // 如果 TS 报错，可能需要忽略类型检查
        };

        // 由于 GenerateContentRequest 的 generationConfig 类型限制，我们可能无法直接传入 imageConfig
        // 如果是 Imagen 模型，应该使用 image generation API 而不是 generateContent
        // 但既然 Python 代码用了 generateContent，我们这里也尝试用它。
        
        // 构建请求体
        const request: any = {
          contents: [{ role: 'user', parts: parts }],
          generationConfig: generationConfig
        };

        const result = await this.image_model.generateContent(request);
        const response = await result.response;

        if (!response.candidates || response.candidates.length === 0) {
          throw new Error("No candidates returned");
        }
        
        // 查找图像部分
        for (const candidate of response.candidates) {
            for (const part of candidate.content.parts) {
                // 检查 inlineData 是否存在且是图像
                if (part.inlineData && part.inlineData.mimeType && part.inlineData.mimeType.startsWith('image/')) {
                    return Buffer.from(part.inlineData.data, 'base64');
                }
            }
        }

        throw new Error("响应中未找到图像");
      } catch (error) {
        console.error(`图像生成失败: ${error}`);
        throw error;
      }
    });
  }

  private getMimeType(filePath: string): string {
    const ext = path.extname(filePath).toLowerCase();
    switch (ext) {
      case '.png': return 'image/png';
      case '.jpg':
      case '.jpeg': return 'image/jpeg';
      case '.webp': return 'image/webp';
      case '.gif': return 'image/gif';
      default: return 'image/png';
    }
  }
}

// 测试代码
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const main = async () => {
    const vertexTool = new VertexAITool();
    console.log("=".repeat(60));
    console.log("Vertex AI 工具类测试 (TypeScript)");
    console.log("=".repeat(60));

    const readline = await import('readline');
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    const question = (query: string) => new Promise<string>(resolve => rl.question(query, resolve));

    while (true) {
      console.log("\n请选择测试类型:");
      console.log("1. 文本模型测试");
      console.log("2. 图像模型测试");
      console.log("3. 退出");
      const choice = (await question("请输入选项 (1-3): ")).trim();

      if (choice === "1") {
        console.log("\n--- 文本模型测试 ---");
        let prompt = (await question("请输入提示词 (默认: '你好，请简单介绍一下你自己。'): ")).trim();
        if (!prompt) prompt = "你好，请简单介绍一下你自己。";

        try {
          console.log("\n正在调用 Vertex AI 文本模型...");
          const result = await vertexTool.generateText(prompt);
          console.log("\n生成结果:");
          console.log("-".repeat(60));
          console.log(result);
          console.log("-".repeat(60));
        } catch (e) {
          console.error(`\n错误: ${e}`);
        }
      } else if (choice === "2") {
        console.log("\n--- 图像模型测试 ---");
        let prompt = (await question("请输入图像生成提示词 (默认: '一只可爱的猫咪在花园里玩耍'): ")).trim();
        if (!prompt) prompt = "一只可爱的猫咪在花园里玩耍";

        let savePath = (await question("请输入保存路径 (默认: 'generated_image_ts.png'): ")).trim();
        if (!savePath) savePath = "generated_image_ts.png";

        try {
          console.log("\n正在调用 Vertex AI 图像模型...");
          console.log(`提示词: ${prompt}`);
          const result = await vertexTool.generateImage(prompt);

          if (result) {
            fs.writeFileSync(savePath, result);
            console.log(`\n图像已保存到: ${savePath}`);
          } else {
            console.log("\n图像生成失败");
          }
        } catch (e) {
          console.error(`\n错误: ${e}`);
        }
      } else if (choice === "3") {
        console.log("\n退出测试");
        rl.close();
        break;
      } else {
        console.log("\n无效选项，请重新选择");
      }
    }
  };

  main().catch(console.error);
}
