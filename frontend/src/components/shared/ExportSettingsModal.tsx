import React from 'react';
import { Modal, Button } from '@/components/shared';
import type { ExportExtractorMethod, ExportInpaintMethod } from '@/types';

interface ExportSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (extractor: ExportExtractorMethod, inpaint: ExportInpaintMethod) => void;
  initialExtractor: ExportExtractorMethod;
  initialInpaint: ExportInpaintMethod;
}

export const ExportSettingsModal: React.FC<ExportSettingsModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  initialExtractor,
  initialInpaint,
}) => {
  const [extractor, setExtractor] = React.useState<ExportExtractorMethod>(initialExtractor);
  const [inpaint, setInpaint] = React.useState<ExportInpaintMethod>(initialInpaint);

  // Reset state when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setExtractor(initialExtractor);
      setInpaint(initialInpaint);
    }
  }, [isOpen, initialExtractor, initialInpaint]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="导出可编辑 PPTX 设置"
      size="md"
    >
      <div className="space-y-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
          <p className="font-semibold mb-1">💡 关于可编辑导出</p>
          <p>
            生成可编辑 PPT 需要对图片进行深度分析和重建。
            此过程耗时较长（约 30-60 秒/页），请耐心等待。
          </p>
        </div>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              版面分析模式 (Extractor)
            </label>
            <select
              value={extractor}
              onChange={(e) => setExtractor(e.target.value as ExportExtractorMethod)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-banana-500 focus:border-banana-500 sm:text-sm"
            >
              <option value="hybrid">混合模式 (推荐) - MinerU + 百度OCR表格精修</option>
              <option value="mineru">快速模式 - 仅使用 MinerU</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              混合模式在处理复杂表格时效果更好，但速度稍慢。
            </p>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              背景修复模式 (Inpaint)
            </label>
            <select
              value={inpaint}
              onChange={(e) => setInpaint(e.target.value as ExportInpaintMethod)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-banana-500 focus:border-banana-500 sm:text-sm"
            >
              <option value="hybrid">混合模式 (推荐) - 百度去字 + AI画质增强</option>
              <option value="baidu">极速模式 - 仅使用百度去字</option>
              <option value="generative">画质优先 - 仅使用AI重绘 (较慢)</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              决定如何移除原图中的文字以生成干净背景。混合模式兼顾去字彻底性和画质。
            </p>
          </div>
        </div>
        
        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button 
            variant="primary" 
            onClick={() => onConfirm(extractor, inpaint)}
          >
            开始导出
          </Button>
        </div>
      </div>
    </Modal>
  );
};
