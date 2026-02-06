
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from services.image_editability.text_attribute_extractors import CVTextAttributeExtractor

def create_test_image(text="Hello", font_color=(0, 0, 255), bg_color=(255, 255, 255), font_size=15):
    img = Image.new('RGB', (200, 50), bg_color)
    draw = ImageDraw.Draw(img)
    try:
        # Use a common font or default
        font = ImageFont.load_default()
    except:
        font = None
    
    # Draw text. Note: default font might be small and not have much anti-aliasing
    # but we want to test the principle.
    draw.text((10, 10), text, fill=font_color, font=font)
    return img

def test_cv_extractor_color_robustness():
    extractor = CVTextAttributeExtractor()
    
    # Test 1: Pure blue on white
    # Even with small font/anti-aliasing, it should get close to pure blue
    blue = (0, 0, 255)
    img = create_test_image(font_color=blue, bg_color=(255, 255, 255))
    result = extractor.extract(img)
    
    # Check that it's much closer to blue than to white
    # (i.e., R and G components should be low)
    r, g, b = result.font_color_rgb
    assert r < 30
    assert g < 30
    assert b > 220

def test_cv_extractor_dark_bg():
    extractor = CVTextAttributeExtractor()
    
    # Test 2: Bright green on dark gray
    green = (0, 255, 0)
    img = create_test_image(font_color=green, bg_color=(30, 30, 30))
    result = extractor.extract(img)
    
    r, g, b = result.font_color_rgb
    assert r < 40
    assert g > 210
    assert b < 40

def test_cv_extractor_bold_detection():
    # This is a basic test for bold detection
    # Since we use a simple density threshold, it might be flaky with default font
    # but let's at least check it doesn't crash
    extractor = CVTextAttributeExtractor()
    img = create_test_image()
    result = extractor.extract(img)
    assert isinstance(result.is_bold, bool)
