import React, { useState, useRef } from 'react';
import { Upload, X } from 'lucide-react';
import { Modal, Button, useToast } from '@/components/shared';
import { createProject, convertImagesToPPT } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';
import type { ExportExtractorMethod, ExportInpaintMethod } from '@/types';

interface ImageToPPTModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ImageToPPTModal: React.FC<ImageToPPTModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const { show } = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // 转换设置
  const [extractorMethod, setExtractorMethod] = useState<ExportExtractorMethod>('hybrid');
  const [inpaintMethod, setInpaintMethod] = useState<ExportInpaintMethod>('hybrid');

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files).filter(file => file.type.startsWith('image/'));
      setFiles(prev => [...prev, ...newFiles]);
    }
    // Reset input
    if (fileInputRef.current) {
        fileInputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    try {
      // 1. 创建新项目
      const projectResponse = await createProject({
        creation_type: 'idea', // 创建一个空的 idea 项目作为容器
        idea_prompt: 'Image Import Project', // 占位符
      });
      
      const projectId = projectResponse.data?.project_id;
      if (!projectId) throw new Error('创建项目失败');

      // 2. 调用转换接口
      await convertImagesToPPT(projectId, files, extractorMethod, inpaintMethod);
      
      show({ message: '已开始转换，正在跳转...', type: 'success' });
      
      // 3. 跳转到预览页
      navigate(`/project/${projectId}/preview`);
      onClose();
      
    } catch (error: any) {
      console.error('转换失败:', error);
      show({ message: error.message || '转换失败', type: 'error' });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="图片转可编辑 PPT"
      size="lg"
    >
      <div className="space-y-6">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
          <p className="font-semibold mb-1">💡 功能说明</p>
          <p>
            上传 PPT 截图或任意图片，AI 将自动识别其中的文字、图片和表格，并重建为可编辑的 PPT 幻灯片。
          </p>
        </div>

        {/* 文件上传区 */}
        <div 
          className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-banana-400 transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 bg-banana-50 rounded-full flex items-center justify-center text-banana-600">
              <Upload size={24} />
            </div>
            <div>
              <p className="font-medium text-gray-700">点击上传图片</p>
              <p className="text-sm text-gray-500 mt-1">支持 JPG, PNG, WEBP (多选)</p>
            </div>
          </div>
        </div>

        {/* 文件列表 */}
        {files.length > 0 && (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3 max-h-60 overflow-y-auto p-1">
            {files.map((file, idx) => (
              <div key={idx} className="relative group aspect-video bg-gray-100 rounded-lg overflow-hidden border border-gray-200">
                <img 
                  src={URL.createObjectURL(file)} 
                  alt={file.name}
                  className="w-full h-full object-cover" 
                />
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(idx); }}
                  className="absolute top-1 right-1 p-1 bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={12} />
                </button>
                <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-[10px] px-2 py-1 truncate">
                  {file.name}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 高级设置 */}
        <div className="space-y-4 pt-4 border-t border-gray-100">
          <h4 className="text-sm font-medium text-gray-900">转换设置</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                版面分析模式
              </label>
              <select
                value={extractorMethod}
                onChange={(e) => setExtractorMethod(e.target.value as ExportExtractorMethod)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-banana-500 focus:border-banana-500"
              >
                <option value="hybrid">混合模式 (推荐)</option>
                <option value="mineru">快速模式 (MinerU)</option>
                <option value="local">本地 OCR 模式</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                背景修复模式
              </label>
              <select
                value={inpaintMethod}
                onChange={(e) => setInpaintMethod(e.target.value as ExportInpaintMethod)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-banana-500 focus:border-banana-500"
              >
                <option value="hybrid">混合模式 (推荐)</option>
                <option value="baidu">极速模式 (仅去字)</option>
                <option value="generative">画质优先 (AI重绘)</option>
                <option value="local">本地 LAMA 修复</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button 
            variant="primary" 
            onClick={handleSubmit}
            disabled={files.length === 0 || isUploading}
            loading={isUploading}
          >
            {isUploading ? '正在处理...' : `开始转换 (${files.length}张)`}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
