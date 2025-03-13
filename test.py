from flask import Flask, Response, render_template
import cv2
import numpy as np
from ultralytics import YOLO

app = Flask(__name__)

# Webcam index (0 for built-in camera)
WEBCAM_INDEX = 0

# Load YOLOv8m model
model = YOLO("yolov8m.pt")

# Define Trapezium ROI
ROI_POINTS = np.array([[100, 300], [500, 300], [600, 480], [50, 480]])

# Focal length for distance calculation
FOCAL_LENGTH = 250  # Adjust this for accuracy
KNOWN_OBJECT_WIDTH = 1.7  # Average width of a human in meters


def is_inside_roi(x, y):
    """Check if a point is inside the trapezium ROI."""
    roi_mask = np.zeros((480, 640), dtype=np.uint8)
    cv2.fillPoly(roi_mask, [ROI_POINTS], 255)
    return roi_mask[y, x] == 255


def estimate_distance(bbox_width):
    """Estimate object distance using focal length formula."""
    if bbox_width > 0:
        distance = (KNOWN_OBJECT_WIDTH * FOCAL_LENGTH) / bbox_width
        return round(distance, 2)
    return None


def generate_frames():
    """Capture webcam frames, detect objects, and display results."""
    cap = cv2.VideoCapture(WEBCAM_INDEX)

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        # Run YOLO detection
        results = model(frame)
        accident_warning = False
        detected_distance = None

        # Draw ROI
        cv2.polylines(frame, [ROI_POINTS], isClosed=True, color=(255, 0, 0), thickness=2)

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = model.names[int(box.cls[0])]
                confidence = box.conf[0]

                # Calculate center of bounding box
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                bbox_width = x2 - x1

                # Estimate distance
                distance = estimate_distance(bbox_width)

                # Detect objects inside ROI
                if label in ["person", "dog", "cat", "car", "truck"] and is_inside_roi(center_x, center_y):
                    accident_warning = True
                    detected_distance = distance

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    cv2.putText(frame, f"Dist: {distance:.2f}m", (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Display warning message & distance at the top-right, inside frame
        if accident_warning and detected_distance:
            cv2.putText(frame, "Accident Can Happen!", (350, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(frame, f"Distance: {detected_distance}m", (350, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # Encode frame as JPEG
        ret, buffer = cv2.imencode(".jpg", frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
