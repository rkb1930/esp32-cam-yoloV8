from flask import Flask, Response, render_template
import cv2
from ultralytics import YOLO

app = Flask(__name__)

# ESP32 Stream URL (Replace with your ESP32 IP)
ESP32_URL = "http://192.168.184.100:81/stream"  # Update with actual ESP32 stream URL

# Load YOLOv8m model
model = YOLO("yolov8m.pt")

# Define class IDs for person and animals (COCO dataset)
VALID_CLASSES = {0, 16, 17, 18, 19, 20, 21, 22, 23}  # person, bird, cat, dog, horse, sheep, cow, elephant, bear

def generate_frames():
    cap = cv2.VideoCapture(ESP32_URL)

    while True:
        success, frame = cap.read()
        if not success:
            break

        # Run YOLOv8 on the frame
        results = model(frame)

        # Draw detection boxes only for person and animals
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                if class_id in VALID_CLASSES:  # Filter only valid detections
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    label = model.names[class_id]
                    confidence = box.conf[0]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Encode frame as JPEG
        _, buffer = cv2.imencode(".jpg", frame)
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
