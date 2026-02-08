import React, { useState, useCallback, useMemo } from 'react';
import { X, ChevronLeft, ChevronRight, Check, RotateCcw } from 'lucide-react';
import { Button } from '@/components/shared';
import { VerificationCanvas } from './VerificationCanvas';
import type { ElementStatus, VerificationPageData, Page } from '@/types';
import { getImageUrl } from '@/api/client';

interface VerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (confirmedElements: Record<string, string[]>) => void;
  projectId: string;
  pages: Page[];
  pagesData: VerificationPageData[];
}

export const VerificationModal: React.FC<VerificationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  projectId: _projectId,
  pages,
  pagesData,
}) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  // 元素状态：pageId -> elementId -> status
  const [elementStatusMap, setElementStatusMap] = useState<Record<string, Record<string, ElementStatus>>>(() => {
    // 初始化：所有确认的元素为 'erase'，其他为 'keep'
    const initial: Record<string, Record<string, ElementStatus>> = {};
    for (const pageData of pagesData) {
      const pageStatus: Record<string, ElementStatus> = {};
      const confirmedIds = new Set(pageData.confirmedElementIds || []);

      if (pageData.layoutAnalysis?.elements) {
        const getAllElementIds = (elements: any[]): string[] => {
          const ids: string[] = [];
          for (const elem of elements) {
            if (elem.element_id) {
              ids.push(elem.element_id);
            }
            if (elem.children && elem.children.length > 0) {
              ids.push(...getAllElementIds(elem.children));
            }
          }
          return ids;
        };

        const allIds = getAllElementIds(pageData.layoutAnalysis.elements);
        for (const id of allIds) {
          // 如果在 confirmed_element_ids 中，状态为 erase（红色）
          // 否则为 keep（蓝色）
          pageStatus[id] = confirmedIds.has(id) ? 'erase' : 'keep';
        }
      }
      initial[pageData.pageId] = pageStatus;
    }
    return initial;
  });

  const currentPageData = pagesData[currentIndex];

  // 获取当前页的元素状态
  const currentElementStatus = useMemo(() => {
    return elementStatusMap[currentPageData?.pageId] || {};
  }, [elementStatusMap, currentPageData?.pageId]);

  // 切换元素状态
  const handleElementClick = useCallback((elementId: string) => {
    if (!currentPageData) return;

    setElementStatusMap(prev => {
      const pageStatus = { ...prev[currentPageData.pageId] };
      pageStatus[elementId] = pageStatus[elementId] === 'keep' ? 'erase' : 'keep';
      return {
        ...prev,
        [currentPageData.pageId]: pageStatus
      };
    });
  }, [currentPageData]);

  // 全选（全部擦除）
  const handleSelectAll = useCallback(() => {
    if (!currentPageData) return;

    setElementStatusMap(prev => {
      const pageStatus = { ...prev[currentPageData.pageId] };
      for (const id of Object.keys(pageStatus)) {
        pageStatus[id] = 'erase';
      }
      return {
        ...prev,
        [currentPageData.pageId]: pageStatus
      };
    });
  }, [currentPageData]);

  // 全不选（全部保留）
  const handleDeselectAll = useCallback(() => {
    if (!currentPageData) return;

    setElementStatusMap(prev => {
      const pageStatus = { ...prev[currentPageData.pageId] };
      for (const id of Object.keys(pageStatus)) {
        pageStatus[id] = 'keep';
      }
      return {
        ...prev,
        [currentPageData.pageId]: pageStatus
      };
    });
  }, [currentPageData]);

  // 确认导出
  const handleConfirm = useCallback(() => {
    // 收集所有页面中状态为 'erase' 的元素
    const confirmedElements: Record<string, string[]> = {};

    for (const pageData of pagesData) {
      const pageStatus = elementStatusMap[pageData.pageId] || {};
      const eraseIds = Object.entries(pageStatus)
        .filter(([_, status]) => status === 'erase')
        .map(([id]) => id);
      confirmedElements[pageData.pageId] = eraseIds;
    }

    onConfirm(confirmedElements);
  }, [pagesData, elementStatusMap, onConfirm]);

  // 统计当前页的状态
  const currentStats = useMemo(() => {
    const status = currentElementStatus;
    const eraseCount = Object.values(status).filter(s => s === 'erase').length;
    const keepCount = Object.values(status).filter(s => s === 'keep').length;
    return { eraseCount, keepCount, total: eraseCount + keepCount };
  }, [currentElementStatus]);

  // 计算总体进度
  const totalStats = useMemo(() => {
    let totalErase = 0;
    let totalKeep = 0;

    for (const pageData of pagesData) {
      const pageStatus = elementStatusMap[pageData.pageId] || {};
      totalErase += Object.values(pageStatus).filter(s => s === 'erase').length;
      totalKeep += Object.values(pageStatus).filter(s => s === 'keep').length;
    }

    return { totalErase, totalKeep, total: totalErase + totalKeep };
  }, [pagesData, elementStatusMap]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-gray-900 flex flex-col">
      {/* 顶栏 */}
      <header className="h-14 bg-gray-800 flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
          <h1 className="text-white font-semibold">确认文字区域</h1>
          <span className="text-gray-400 text-sm">
            第 {currentIndex + 1} / {pagesData.length} 页
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-sm text-gray-400">
            <span className="text-red-400">删除 {totalStats.totalErase}</span>
            {' / '}
            <span className="text-blue-400">保留 {totalStats.totalKeep}</span>
            {' / '}
            共 {totalStats.total} 个元素
          </div>
          <Button
            variant="primary"
            size="sm"
            icon={<Check size={16} />}
            onClick={handleConfirm}
          >
            确认导出
          </Button>
        </div>
      </header>

      {/* 主内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：页面缩略图 */}
        <aside className="w-48 bg-gray-800 border-r border-gray-700 overflow-y-auto flex-shrink-0">
          <div className="p-2 space-y-2">
            {pagesData.map((pageData, index) => {
              const page = pages.find(p => p.page_id === pageData.pageId || p.id === pageData.pageId);
              const pageStatus = elementStatusMap[pageData.pageId] || {};
              const eraseCount = Object.values(pageStatus).filter(s => s === 'erase').length;
              const isActive = index === currentIndex;

              return (
                <button
                  key={pageData.pageId}
                  onClick={() => setCurrentIndex(index)}
                  className={`w-full aspect-video rounded-lg overflow-hidden border-2 transition-all ${
                    isActive
                      ? 'border-banana-500 shadow-lg'
                      : 'border-transparent hover:border-gray-600'
                  }`}
                >
                  <div className="relative w-full h-full bg-gray-700">
                    {page?.generated_image_path && (
                      <img
                        src={getImageUrl(page.generated_image_path, page.updated_at)}
                        alt={`Page ${index + 1}`}
                        className="w-full h-full object-cover"
                      />
                    )}
                    {/* 删除计数 */}
                    <div className="absolute bottom-1 right-1 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded">
                      {eraseCount}
                    </div>
                    {/* 页码 */}
                    <div className="absolute top-1 left-1 bg-black/50 text-white text-xs px-1.5 py-0.5 rounded">
                      {index + 1}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* 中间：画布 */}
        <main className="flex-1 relative">
          {currentPageData && currentPageData.layoutAnalysis && currentPageData.layoutAnalysis.elements && (
            <VerificationCanvas
              imageUrl={currentPageData.imageUrl}
              imageWidth={currentPageData.layoutAnalysis.width}
              imageHeight={currentPageData.layoutAnalysis.height}
              elements={currentPageData.layoutAnalysis.elements}
              elementStatus={currentElementStatus}
              onElementClick={handleElementClick}
            />
          )}

          {(!currentPageData || !currentPageData.layoutAnalysis || !currentPageData.layoutAnalysis.elements) && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
              <span>暂无分析数据</span>
              {currentPageData && (
                <span className="text-xs">
                  pageId: {currentPageData.pageId} |
                  hasLayout: {currentPageData.layoutAnalysis ? 'yes' : 'no'} |
                  imageUrl: {currentPageData.imageUrl ? 'yes' : 'no'}
                </span>
              )}
            </div>
          )}
        </main>
      </div>

      {/* 底栏 */}
      <footer className="h-16 bg-gray-800 border-t border-gray-700 flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            icon={<ChevronLeft size={16} />}
            onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
            disabled={currentIndex === 0}
            className="text-gray-300"
          >
            上一页
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<ChevronRight size={16} />}
            onClick={() => setCurrentIndex(Math.min(pagesData.length - 1, currentIndex + 1))}
            disabled={currentIndex === pagesData.length - 1}
            className="text-gray-300"
          >
            下一页
          </Button>
        </div>

        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-400">
            当前页：
            <span className="text-red-400 ml-1">删除 {currentStats.eraseCount}</span>
            <span className="mx-1">/</span>
            <span className="text-blue-400">保留 {currentStats.keepCount}</span>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSelectAll}
            className="text-gray-300"
          >
            全部删除
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDeselectAll}
            className="text-gray-300"
          >
            全部保留
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw size={14} />}
            onClick={() => {
              // 重置当前页到初始状态
              if (!currentPageData) return;
              const confirmedIds = new Set(currentPageData.confirmedElementIds || []);
              setElementStatusMap(prev => {
                const pageStatus = { ...prev[currentPageData.pageId] };
                for (const id of Object.keys(pageStatus)) {
                  pageStatus[id] = confirmedIds.has(id) ? 'erase' : 'keep';
                }
                return {
                  ...prev,
                  [currentPageData.pageId]: pageStatus
                };
              });
            }}
            className="text-gray-300"
          >
            重置
          </Button>
        </div>
      </footer>
    </div>
  );
};
