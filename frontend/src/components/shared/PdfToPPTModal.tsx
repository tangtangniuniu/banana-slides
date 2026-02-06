import React, { useState, useRef } from 'react';
import { Upload, X, FileText, Settings, Sparkles, Layers } from 'lucide-react';
import { Modal, Button, useToast, Textarea } from '@/components/shared';
import { createProject, convertPdfToPPT } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import { useExportTasksStore } from '@/store/useExportTasksStore';
import type { ExportExtractorMethod, ExportInpaintMethod } from '@/types';

interface PdfToPPTModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PdfToPPTModal: React.FC<PdfToPPTModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const { show } = useToast();
  const { addTask, pollTask } = useExportTasksStore();
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  
  // 转换设置
  const [mode, setMode] = useState<'original' | 'reconstructed'>('original');
  const [resolution, setResolution] = useState<'1K' | '2K'>('2K');
  const [templateStyle, setTemplateStyle] = useState('');
  const [extractorMethod, setExtractorMethod] = useState<ExportExtractorMethod>('hybrid');
  const [inpaintMethod, setInpaintMethod] = useState<ExportInpaintMethod>('local'); // 默认本地
  const [showAdvanced, setShowAdvanced] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      if (selectedFile.type !== 'application/pdf') {
        show({ message: '请选择 PDF 文件', type: 'error' });
        return;
      }
      setFile(selectedFile);
    }
    // Reset input
    if (fileInputRef.current) {
        fileInputRef.current.value = '';
    }
  };

  const removeFile = () => {
    setFile(null);
  };

  const handleSubmit = async () => {
    if (!file) return;

    if (mode === 'reconstructed' && !templateStyle.trim()) {
      show({ message: '重构模式下请输入风格描述', type: 'warning' });
      return;
    }

    setIsProcessing(true);
    try {
      // 1. 创建新项目
      const projectResponse = await createProject({
        creation_type: 'idea',
        idea_prompt: `PDF Import: ${file.name}`,
        template_style: templateStyle || undefined
      });
      
      const projectId = projectResponse.data?.project_id;
      if (!projectId) throw new Error('创建项目失败');

      // 2. 调用转换接口 (异步任务)
      const convertResponse = await convertPdfToPPT(
        projectId, 
        file, 
        mode, 
        resolution, 
        templateStyle,
        extractorMethod,
        inpaintMethod
      );
      
      const taskId = convertResponse.data?.task_id;
      const pageIds = convertResponse.data?.page_ids;

      if (taskId) {
        const exportTaskId = `pdf-convert-${Date.now()}`;
        addTask({
          id: exportTaskId,
          taskId,
          projectId,
          type: 'editable-pptx', // Treat as editable PPTX export
          status: 'PROCESSING',
          pageIds: pageIds
        });
        pollTask(exportTaskId, projectId, taskId);
      }
      
      show({ message: '已提交 PDF 转换任务，正在跳转...', type: 'success' });
      
      // 3. 跳转到预览页（显示任务进度）
      navigate(`/project/${projectId}/preview`);
      onClose();
      
    } catch (error: any) {
      console.error('PDF 转换失败:', error);
      show({ message: error.message || '转换失败', type: 'error' });
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="PDF 转可编辑 PPT"
      size="lg"
    >
      <div className="space-y-6">
        <div className="bg-banana-50 border border-banana-200 rounded-lg p-4 text-sm text-banana-800">
          <p className="font-semibold mb-1 flex items-center gap-2">
            <Sparkles size={16} /> 功能说明
          </p>
          <p>
            将 PDF 每一页转换为高清图片，并利用 AI 识别其中的元素，重建为完全可编辑的 PPT 幻灯片。
          </p>
        </div>

        {/* 模式选择 */}
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => setMode('original')}
            className={`p-4 rounded-xl border-2 transition-all text-left ${
              mode === 'original' 
                ? 'border-banana-500 bg-banana-50 ring-2 ring-banana-200' 
                : 'border-gray-100 bg-gray-50 hover:border-gray-200'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <Layers size={18} className={mode === 'original' ? 'text-banana-600' : 'text-gray-400'} />
              <span className="font-semibold">原始转换</span>
            </div>
            <p className="text-xs text-gray-500">保持原始页面布局和设计，仅实现可编辑化</p>
          </button>
          
          <button
            onClick={() => setMode('reconstructed')}
            className={`p-4 rounded-xl border-2 transition-all text-left ${
              mode === 'reconstructed' 
                ? 'border-banana-500 bg-banana-50 ring-2 ring-banana-200' 
                : 'border-gray-100 bg-gray-50 hover:border-gray-200'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <Sparkles size={18} className={mode === 'reconstructed' ? 'text-banana-600' : 'text-gray-400'} />
              <span className="font-semibold">重构转换</span>
            </div>
            <p className="text-xs text-gray-500">根据风格模板重绘每一页，实现整体风格统一</p>
          </button>
        </div>

        {/* 文件上传区 */}
        {!file ? (
          <div 
            className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center hover:border-banana-400 transition-colors cursor-pointer bg-gray-50/50"
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={handleFileSelect}
            />
            <div className="flex flex-col items-center gap-3">
              <div className="w-14 h-14 bg-banana-100 rounded-full flex items-center justify-center text-banana-600">
                <Upload size={28} />
              </div>
              <div>
                <p className="font-semibold text-gray-700 text-lg">点击或拖拽上传 PDF</p>
                <p className="text-sm text-gray-500 mt-1">AI 将自动分页并处理</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between p-4 bg-white rounded-xl border-2 border-banana-200 shadow-sm">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-12 h-12 bg-red-50 rounded-lg flex items-center justify-center text-red-500 flex-shrink-0">
                <FileText size={24} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-gray-900 truncate">{file.name}</p>
                <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            </div>
            <button
              onClick={removeFile}
              className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-colors"
              disabled={isProcessing}
            >
              <X size={20} />
            </button>
          </div>
        )}

        {/* 重构模式下的风格输入 */}
        {mode === 'reconstructed' && (
          <div className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-300">
            <label className="block text-sm font-semibold text-gray-700">
              设置风格模板 <span className="text-red-500">*</span>
            </label>
            <Textarea
              placeholder="请输入您希望重构后的 PPT 风格描述（如：简约现代，配色以深蓝为主，配合明亮的橙色点缀...）"
              value={templateStyle}
              onChange={(e) => setTemplateStyle(e.target.value)}
              rows={3}
              className="border-2 focus:border-banana-400"
            />
          </div>
        )}

        {/* 高级设置开关 */}
        <div className="pt-2">
          <button 
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-banana-600 transition-colors"
          >
            <Settings size={16} />
            {showAdvanced ? '隐藏高级设置' : '高级设置'}
          </button>
        </div>

        {showAdvanced && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 bg-gray-50 rounded-xl border border-gray-200 animate-in fade-in zoom-in-95 duration-200">
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                PDF 图片分辨率
              </label>
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value as '1K' | '2K')}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-banana-500 focus:border-banana-500"
              >
                <option value="1K">1K (标准)</option>
                <option value="2K">2K (高清)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                背景修复模式
              </label>
              <select
                value={inpaintMethod}
                onChange={(e) => setInpaintMethod(e.target.value as ExportInpaintMethod)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-banana-500 focus:border-banana-500"
              >
                <option value="local">本地 LAMA (推荐)</option>
                <option value="hybrid">混合修复 (百度+AI)</option>
                <option value="baidu">极速修复 (百度)</option>
                <option value="generative">画质重绘 (AI模型)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                版面分析模式
              </label>
              <select
                value={extractorMethod}
                onChange={(e) => setExtractorMethod(e.target.value as ExportExtractorMethod)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-banana-500 focus:border-banana-500"
              >
                <option value="hybrid">混合模式 (百度OCR+分析)</option>
                <option value="mineru">快速模式 (MinerU)</option>
                <option value="local">本地 OCR 模式</option>
              </select>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
          <Button variant="ghost" onClick={onClose} disabled={isProcessing}>取消</Button>
          <Button 
            variant="primary" 
            onClick={handleSubmit}
            disabled={!file || isProcessing}
            loading={isProcessing}
            className="px-8 shadow-yellow"
          >
            {isProcessing ? '处理中...' : '开始转换'}
          </Button>
        </div>
      </div>
    </Modal>
  );
};