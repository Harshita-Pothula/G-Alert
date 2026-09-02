"""Small test-only YOLOv8 inference check.

Uses the existing yolov8n.pt model already present in the environment and a tiny
public sample image URL. This is test-only and does not modify production code.
"""

from ultralytics import YOLO


SAMPLE_IMAGE_URL = "https://ultralytics.com/images/bus.jpg"


def main():
    print("YOLOv8 test")
    print("This is a YOLOv8 test, not a real G-ALERT observation.")

    try:
        model = YOLO("yolov8n.pt")
        print("model loaded successfully")
    except Exception as exc:
        print(f"FAIL: model load error: {exc}")
        return

    print(f"image used: {SAMPLE_IMAGE_URL}")

    try:
        results = model(SAMPLE_IMAGE_URL, conf=0.25, verbose=False)
        detections = results[0].boxes
        count = 0 if detections is None else len(detections)
        print(f"number of detections: {count}")

        if detections is not None:
            names = results[0].names
            for i, box in enumerate(detections, start=1):
                cls_id = int(box.cls[0])
                name = names.get(cls_id, str(cls_id))
                conf = float(box.conf[0])
                print(f"  [{i}] {name} conf={conf:.3f}")

        print("PASS: YOLOv8 inference completed successfully")
    except Exception as exc:
        print(f"FAIL: image inference error: {exc}")


if __name__ == "__main__":
    main()
