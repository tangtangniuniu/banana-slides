import React from 'react';
import { Modal, Button } from '@/components/shared';
import type { ExportExtractorMethod, ExportInpaintMethod } from '@/types';
import { getSettings } from '@/api/endpoints';

interface ExportSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (extractor: ExportExtractorMethod | 'local', inpaint: ExportInpaintMethod | 'local', manualConfirmation: boolean) => void;
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
  // 扩展类型以支持 'local'
  const [extractor, setExtractor] = React.useState<ExportExtractorMethod | 'local'>(initialExtractor);
  const [inpaint, setInpaint] = React.useState<ExportInpaintMethod | 'local'>(initialInpaint);
  const [globalLocalEnabled, setGlobalLocalEnabled] = React.useState(false);
  const [manualConfirmation, setManualConfirmation] = React.useState(false);

  // Reset state when modal opens
  React.useEffect(() => {
    if (isOpen) {
      // Check global settings
      getSettings().then(res => {
        if (res.data?.use_local_ocr_inpaint) {
          setGlobalLocalEnabled(true);
          // 默认选中 Local
          setExtractor('local');
          setInpaint('local');
        } else {
          setGlobalLocalEnabled(false);
          setExtractor(initialExtractor);
          setInpaint(initialInpaint);
        }
      }).catch(err => {
        console.error("Failed to fetch settings:", err);
        setExtractor(initialExtractor);
        setInpaint(initialInpaint);
      });
      // 重置人工确认选项
      setManualConfirmation(false);
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

        {globalLocalEnabled && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
            <p className="font-semibold mb-1">🚀 默认使用本地服务</p>
            <p>
              全局设置已启用本地 OCR & Inpaint。已自动为您选择本地模式，您也可以手动切换为其他模式。
            </p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              版面分析模式 (Extractor)
            </label>
            <select
              value={extractor}
              onChange={(e) => setExtractor(e.target.value as ExportExtractorMethod | 'local')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-banana-500 focus:border-banana-500 sm:text-sm"
            >
              {globalLocalEnabled && <option value="local">本地模式 (Local) - 使用配置的本地OCR接口</option>}
              <option value="hybrid">混合模式 (推荐) - MinerU + 百度OCR表格精修</option>
              <option value="mineru">快速模式 - 仅使用 MinerU</option>
              {!globalLocalEnabled && <option value="local">本地模式 (Local) - 需要先在设置中启用</option>}
            </select>
            <p className="mt-1 text-xs text-gray-500">
              混合模式在处理复杂表格时效果更好，本地模式速度最快。
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              背景修复模式 (Inpaint)
            </label>
            <select
              value={inpaint}
              onChange={(e) => setInpaint(e.target.value as ExportInpaintMethod | 'local')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-banana-500 focus:border-banana-500 sm:text-sm"
            >
              {globalLocalEnabled && <option value="local">本地模式 (Local) - 使用配置的本地Inpaint接口</option>}
              <option value="hybrid">混合模式 (推荐) - 百度去字 + AI画质增强</option>
              <option value="baidu">极速模式 - 仅使用百度去字</option>
              <option value="generative">画质优先 - 仅使用AI重绘 (较慢)</option>
              {!globalLocalEnabled && <option value="local">本地模式 (Local) - 需要先在设置中启用</option>}
            </select>
            <p className="mt-1 text-xs text-gray-500">
              决定如何移除原图中的文字以生成干净背景。
            </p>
          </div>

          {/* 人工确认选项 */}
          <div className="pt-2 border-t border-gray-100">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={manualConfirmation}
                onChange={(e) => setManualConfirmation(e.target.checked)}
                className="mt-1 h-4 w-4 text-banana-600 focus:ring-banana-500 border-gray-300 rounded"
              />
              <div>
                <span className="text-sm font-medium text-gray-700">人工确认文字区域</span>
                <p className="text-xs text-gray-500 mt-0.5">
                  先执行 OCR 分析，然后手动选择哪些文字区域需要擦除重构，哪些保留原样。
                  适合需要精细控制导出效果的场景。
                </p>
              </div>
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            onClick={() => onConfirm(extractor, inpaint, manualConfirmation)}
          >
            {manualConfirmation ? '开始分析' : '开始导出'}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
