import React, { useState, useRef } from 'react';
import { Upload, X, FileText } from 'lucide-react';
import { Modal, Button, useToast } from '@/components/shared';
import { createProject, uploadReferenceFile, triggerFileParse, getReferenceFile, generateOutline } from '@/api/endpoints';
import { useNavigate } from 'react-router-dom';

interface PdfToPPTModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PdfToPPTModal: React.FC<PdfToPPTModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const { show } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressMessage, setProgressMessage] = useState('');
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

  const pollFileStatus = async (fileId: string): Promise<boolean> => {
    const maxRetries = 60; // 5 minutes max (5s * 60)
    let retries = 0;

    return new Promise((resolve, reject) => {
      const checkStatus = async () => {
        try {
          const response = await getReferenceFile(fileId);
          const status = response.data?.file?.parse_status;

          if (status === 'completed') {
            resolve(true);
          } else if (status === 'failed') {
            reject(new Error('PDF 解析失败'));
          } else {
            retries++;
            if (retries >= maxRetries) {
              reject(new Error('PDF 解析超时'));
            } else {
              setTimeout(checkStatus, 5000);
            }
          }
        } catch (error) {
          reject(error);
        }
      };
      checkStatus();
    });
  };

  const handleSubmit = async () => {
    if (!file) return;

    setIsProcessing(true);
    try {
      // 1. 创建新项目
      setProgressMessage('正在创建项目...');
      const projectResponse = await createProject({
        creation_type: 'idea',
        idea_prompt: '基于参考文件内容生成演示文稿大纲，请提取文件中的核心观点和结构。',
      });
      
      const projectId = projectResponse.data?.project_id;
      if (!projectId) throw new Error('创建项目失败');

      // 2. 上传 PDF 文件
      setProgressMessage('正在上传 PDF...');
      const uploadResponse = await uploadReferenceFile(file, projectId);
      const fileId = uploadResponse.data?.file?.id;
      if (!fileId) throw new Error('上传文件失败');

      // 3. 触发解析 (上传接口可能自动触发，但手动确保一下)
      // uploadReferenceFile logic in backend/controllers/reference_file_controller.py 
      // automatically triggers parsing via thread if status is pending.
      // But we need to wait for it.
      
      // 4. 等待解析完成
      setProgressMessage('正在解析 PDF 内容 (可能需要几分钟)...');
      await pollFileStatus(fileId);

      // 5. 生成大纲
      setProgressMessage('正在生成 PPT 大纲...');
      await generateOutline(projectId);
      
      show({ message: '大纲生成成功，正在跳转...', type: 'success' });
      
      // 6. 跳转到大纲页
      navigate(`/project/${projectId}/outline`);
      onClose();
      
    } catch (error: any) {
      console.error('PDF 转 PPT 失败:', error);
      show({ message: error.message || '处理失败', type: 'error' });
    } finally {
      setIsProcessing(false);
      setProgressMessage('');
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="PDF 转 PPT"
      size="md"
    >
      <div className="space-y-6">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
          <p className="font-semibold mb-1">💡 功能说明</p>
          <p>
            上传 PDF 文档，AI 将自动阅读并提取其中的核心内容，为您生成结构化的 PPT 大纲。
          </p>
        </div>

        {/* 文件上传区 */}
        {!file ? (
          <div 
            className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-banana-400 transition-colors cursor-pointer"
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
              <div className="w-12 h-12 bg-banana-50 rounded-full flex items-center justify-center text-banana-600">
                <Upload size={24} />
              </div>
              <div>
                <p className="font-medium text-gray-700">点击上传 PDF</p>
                <p className="text-sm text-gray-500 mt-1">支持 .pdf 格式</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center text-red-600 flex-shrink-0">
                <FileText size={20} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
                <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            </div>
            <button
              onClick={removeFile}
              className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
              disabled={isProcessing}
            >
              <X size={18} />
            </button>
          </div>
        )}

        {isProcessing && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-gray-500">
              <span>{progressMessage}</span>
              <span className="animate-pulse">...</span>
            </div>
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-banana-500 rounded-full animate-progress-indeterminate"></div>
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
          >
            {isProcessing ? '处理中...' : '开始生成'}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
