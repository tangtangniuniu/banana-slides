import React, { useRef, useState, useEffect, useCallback } from 'react';
import type { LayoutElement, ElementStatus } from '@/types';

interface VerificationCanvasProps {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  elements: LayoutElement[];
  elementStatus: Record<string, ElementStatus>;
  onElementClick: (elementId: string) => void;
}

export const VerificationCanvas: React.FC<VerificationCanvasProps> = ({
  imageUrl,
  imageWidth,
  imageHeight,
  elements,
  elementStatus,
  onElementClick,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [hoveredElement, setHoveredElement] = useState<string | null>(null);

  // 计算缩放比例以适应容器
  useEffect(() => {
    const updateScale = () => {
      if (!containerRef.current || !imageWidth || !imageHeight) return;

      const containerWidth = containerRef.current.clientWidth;
      const containerHeight = containerRef.current.clientHeight;

      // 留一些边距
      const availableWidth = containerWidth - 40;
      const availableHeight = containerHeight - 40;

      const scaleX = availableWidth / imageWidth;
      const scaleY = availableHeight / imageHeight;
      const newScale = Math.min(scaleX, scaleY, 1); // 不放大超过原始尺寸

      setScale(newScale);
    };

    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, [imageWidth, imageHeight]);

  // 渲染单个元素的包围盒
  const renderElement = useCallback((element: LayoutElement) => {
    const status = elementStatus[element.element_id] || 'erase';
    const isHovered = hoveredElement === element.element_id;

    // 使用 bbox_global（全局坐标），如果没有则使用 bbox
    const bbox = element.bbox_global || element.bbox;

    const style: React.CSSProperties = {
      position: 'absolute',
      left: bbox.x0 * scale,
      top: bbox.y0 * scale,
      width: (bbox.x1 - bbox.x0) * scale,
      height: (bbox.y1 - bbox.y0) * scale,
      border: `2px solid ${status === 'keep' ? '#3b82f6' : '#ef4444'}`,
      backgroundColor: status === 'keep'
        ? 'rgba(59, 130, 246, 0.1)'
        : 'rgba(239, 68, 68, 0.1)',
      cursor: 'pointer',
      transition: 'all 0.15s ease',
      boxShadow: isHovered ? '0 0 8px rgba(0,0,0,0.3)' : 'none',
      zIndex: isHovered ? 10 : 1,
    };

    return (
      <div
        key={element.element_id}
        style={style}
        onClick={(e) => {
          e.stopPropagation();
          onElementClick(element.element_id);
        }}
        onMouseEnter={() => setHoveredElement(element.element_id)}
        onMouseLeave={() => setHoveredElement(null)}
        title={`${element.element_type}: ${element.content?.slice(0, 50) || '(无文字内容)'}\n点击切换状态`}
      >
        {/* 状态指示器 */}
        <div
          className={`absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center text-white text-xs font-bold ${
            status === 'keep' ? 'bg-blue-500' : 'bg-red-500'
          }`}
        >
          {status === 'keep' ? '保' : '删'}
        </div>

        {/* 悬停时显示内容预览 */}
        {isHovered && element.content && (
          <div className="absolute left-0 bottom-full mb-1 bg-black/80 text-white text-xs px-2 py-1 rounded max-w-xs truncate z-20">
            {element.content.slice(0, 100)}
            {element.content.length > 100 ? '...' : ''}
          </div>
        )}
      </div>
    );
  }, [elementStatus, hoveredElement, scale, onElementClick]);

  // 递归获取所有元素（包括子元素）
  const getAllElements = useCallback((elements: LayoutElement[]): LayoutElement[] => {
    const result: LayoutElement[] = [];
    const traverse = (elems: LayoutElement[]) => {
      for (const elem of elems) {
        result.push(elem);
        if (elem.children && elem.children.length > 0) {
          traverse(elem.children);
        }
      }
    };
    traverse(elements);
    return result;
  }, []);

  const allElements = getAllElements(elements);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full flex items-center justify-center bg-gray-100 overflow-auto"
    >
      <div
        className="relative"
        style={{
          width: imageWidth * scale,
          height: imageHeight * scale,
        }}
      >
        {/* 图片 */}
        <img
          src={imageUrl}
          alt="Page preview"
          className="absolute top-0 left-0 w-full h-full object-contain select-none"
          draggable={false}
        />

        {/* 元素包围盒叠加层 */}
        {allElements.map(renderElement)}
      </div>

      {/* 图例 */}
      <div className="absolute bottom-4 left-4 bg-white/90 rounded-lg px-3 py-2 shadow-md text-xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <div className="w-4 h-4 border-2 border-blue-500 bg-blue-500/10 rounded"></div>
            <span>保留原样</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-4 h-4 border-2 border-red-500 bg-red-500/10 rounded"></div>
            <span>擦除重构</span>
          </div>
        </div>
        <p className="text-gray-500 mt-1">点击框体切换状态</p>
      </div>

      {/* 缩放信息 */}
      <div className="absolute top-4 right-4 bg-white/90 rounded-lg px-2 py-1 shadow-md text-xs text-gray-600">
        {Math.round(scale * 100)}%
      </div>
    </div>
  );
};
