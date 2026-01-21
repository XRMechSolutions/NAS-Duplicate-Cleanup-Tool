# Tests

Quick commands:

```bash
pytest
pytest -m "not integration"
pytest -m integration
pytest -m slow
```

Markers:
- `unit`: fast, isolated tests
- `integration`: multi-module tests
- `slow`: long-running tests
- `requires_imagehash`: depends on imagehash being installed
- `requires_geopy`: depends on geopy being installed
- `requires_dearpygui`: depends on Dear PyGui being installed
- `requires_easyocr`: depends on EasyOCR being installed
- `requires_cv2`: depends on OpenCV being installed

Snapshots:
- Stored in `tests/snapshots/`
- Update only when expected behavior changes intentionally
