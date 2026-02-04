import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from backend.services.image_editability.local_providers import LocalOCRElementExtractor, LocalInpaintProvider
from PIL import Image

class TestLocalProviders:
    @pytest.fixture
    def mock_requests_post(self):
        with patch('requests.post') as mock:
            yield mock

    @pytest.fixture
    def mock_lock(self):
        with patch('backend.services.image_editability.local_providers._local_api_lock') as mock:
            yield mock

    def test_ocr_timeout_and_lock(self, mock_requests_post, mock_lock):
        # Setup
        extractor = LocalOCRElementExtractor(api_url="http://test-ocr", output_dir=Path("/tmp"))
        mock_response = MagicMock()
        mock_response.json.return_value = {"json_content": {"rec_texts": [], "rec_polys": []}}
        mock_response.status_code = 200
        mock_requests_post.return_value = mock_response
        
        # Execute
        extractor.extract(image_path="test.png")
        
        # Verify
        mock_requests_post.assert_called_with(
            "http://test-ocr",
            json={
                "img_path": str(Path("test.png").absolute()),
                "output_dir": str(Path("/tmp").absolute())
            },
            timeout=120,
            proxies={"http": None, "https": None}
        )
        # Verify lock usage (enter/exit called)
        assert mock_lock.__enter__.called
        assert mock_lock.__exit__.called

    def test_inpaint_timeout_and_lock(self, mock_requests_post, mock_lock):
        # Setup
        provider = LocalInpaintProvider(api_url="http://test-inpaint", output_dir=Path("/tmp"))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_post.return_value = mock_response
        
        img = Image.new('RGB', (100, 100))
        
        # Execute
        # We need to mock file operations to avoid actual IO
        with patch.object(Image.Image, 'save'), \
             patch('backend.services.image_editability.local_providers.cv2.imwrite'), \
             patch('os.path.exists', return_value=True), \
             patch('PIL.Image.open', return_value=img):
             
            provider.inpaint_regions(image=img, bboxes=[(0,0,10,10)])
        
        # Verify
        # Check if any call matches the timeout
        assert mock_requests_post.called
        call_args = mock_requests_post.call_args
        assert call_args.kwargs['timeout'] == 120
        assert call_args.kwargs['proxies'] == {"http": None, "https": None}
        
        # Verify lock usage
        assert mock_lock.__enter__.called
        assert mock_lock.__exit__.called
