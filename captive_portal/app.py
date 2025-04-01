import cv2
import torch
import requests
from ultralytics import YOLO

# Load YOLOv8 model
model = YOLO("yolov8n.pt")  # Change this to your trained model

# Camera setup
cap = cv2.VideoCapture(0)  # Use 0 for webcam, or replace with video path

# Distance estimation parameters
FOCAL_LENGTH = 700  # Adjust this for your setup
KNOWN_HEIGHT = 1.5  # Object height in meters
ESP32_IP = "http://192.168.4.1/distance"

def estimate_distance(focal_length, real_height, bbox_height):
    return (focal_length * real_height) / bbox_height if bbox_height else -1

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame)  # Run YOLOv8 inference
    for result in results:
        for box in result.boxes.xyxy:  # Extract bounding boxes
            x1, y1, x2, y2 = map(int, box[:4])
            obj_height = y2 - y1  # Bounding box height in pixels

            distance = estimate_distance(FOCAL_LENGTH, KNOWN_HEIGHT, obj_height)
            print(f"Detected object at {distance:.2f} meters")

            # Send distance to ESP32
            try:
                requests.get(ESP32_IP, params={"distance": f"{distance:.2f}"})
            except Exception as e:
                print("Failed to send data:", e)

            # Draw bounding box and distance
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{distance:.2f}m", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    cv2.imshow("YOLOv8 Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
