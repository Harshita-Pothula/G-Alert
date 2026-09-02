"""Small test-only YOLOv8 validation script.

Uses the existing YOLOv8Detector logic in ai/yolov8_detector.py and a local image
if one is already available in the project. No production code is modified.
"""

import os

from ai.yolov8_detector import YOLOv8Detector


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def find_local_image():
    search_roots = [
        ".",
        "ai",
        "satellite",
        "simulation",
    ]

    for root in search_roots:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith(IMAGE_EXTENSIONS):
                    return os.path.join(dirpath, name)
    return None


def main():
    print("G-ALERT YOLOv8 test")
    print("This is a test only. No production files are modified.")

    image_path = find_local_image()
    if image_path is None:
        print("❌ No suitable local test image found in the project.")
        print("YOLOv8 test failed: no image available for inference.")
        return

    print(f"Using local test image: {image_path}")

    try:
        detector = YOLOv8Detector(model_name="yolov8n.pt", confidence_threshold=0.25)
        print("✅ YOLOv8 model loaded successfully.")
    except Exception as exc:
        print(f"❌ YOLOv8 model failed to load: {exc}")
        print("YOLOv8 test failed: model unavailable.")
        return

    try:
        detections = detector.detect_objects(image_path)
        print(f"Detection count: {len(detections)}")
        if detections:
            for i, det in enumerate(detections[:5], start=1):
                print(f"  [{i}] {det.class_name} conf={det.confidence:.3f} bbox={det.bbox}")
        else:
            print("No objects detected in the local test image.")
        print("✅ YOLOv8 inference completed successfully.")
    except Exception as exc:
        print(f"❌ YOLOv8 inference failed: {exc}")
        print("YOLOv8 test failed: inference error.")
        return


if __name__ == "__main__":
    main()
