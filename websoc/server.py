# import cv2
# import numpy as np
# import asyncio
# import websockets
# from flask import Flask, render_template, Response, jsonify
# from flask_cors import CORS
# from ultralytics import YOLO
#
# # ESP32-CAM URLs
# ESP32_CAM1_URL = "http://192.168.212.100:81/stream"  # Vehicle Detector
# ESP32_CAM2_URL = "http://192.168.212.194:81/stream"  # Obstacle Detector
#
# # Load YOLOv8 Model
# model = YOLO("yolov8m.pt")
#
# # Object Categories
# ANIMALS_HUMANS = ["person", "dog", "cat", "cow", "horse", "sheep"]  # CAM2
# VEHICLES = ["car", "truck", "bus", "motorbike"]  # CAM1
#
# # Constants for Distance Calculation
# KNOWN_HEIGHT_OBJ = 1  # Example: 1 ft reference height
# FOCAL_LENGTH = 500  # Pre-calculated focal length
# CAM2_DISTANCE = None  # Distance from CAM2
# VEHICLE_DISTANCE = None  # Distance from CAM1
#
# # Flask App
# app = Flask(__name__)
# CORS(app)  # Enable CORS
#
#
# async def receive_cam2_distance():
#     """Receives distance from CAM2 via WebSocket."""
#     global CAM2_DISTANCE
#     while True:
#         try:
#             async with websockets.connect("ws://192.168.1.101:8765") as websocket:
#                 while True:
#                     data = await websocket.recv()
#                     try:
#                         CAM2_DISTANCE = float(data)
#                         print(f"Received Distance from CAM2: {CAM2_DISTANCE:.2f} feet")
#                     except ValueError:
#                         print("Invalid data received from CAM2.")
#         except Exception as e:
#             print(f"WebSocket Error: {e}. Retrying in 5 sec...")
#             await asyncio.sleep(5)
#
#
# def calculate_distance(bbox_height):
#     """Calculates distance based on bounding box height."""
#     return (KNOWN_HEIGHT_OBJ * FOCAL_LENGTH) / bbox_height if bbox_height > 0 else None
#
#
# def detect_vehicle():
#     """Detects vehicles using YOLOv8 and calculates distance."""
#     global VEHICLE_DISTANCE
#     cap = cv2.VideoCapture(ESP32_CAM1_URL)
#
#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             continue
#
#         results = model(frame)
#         for r in results:
#             for box in r.boxes:
#                 x1, y1, x2, y2 = map(int, box.xyxy[0])
#                 label = r.names[int(box.cls[0])]
#                 if label in VEHICLES:
#                     bbox_height = y2 - y1
#                     VEHICLE_DISTANCE = calculate_distance(bbox_height)
#         cap.release()
#
#
# def generate_feed(cam_url, object_classes):
#     """Generates the camera feed with bounding boxes."""
#     cap = cv2.VideoCapture(cam_url)
#
#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             continue
#
#         results = model(frame)
#         for r in results:
#             for box in r.boxes:
#                 x1, y1, x2, y2 = map(int, box.xyxy[0])
#                 label = r.names[int(box.cls[0])]
#                 if label in object_classes:
#                     color = (255, 0, 0)
#                     cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
#                     cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
#
#         _, buffer = cv2.imencode('.jpg', frame)
#         yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
#
#     cap.release()
#
#
# @app.route('/')
# def index():
#     return render_template('index.html')
#
#
# @app.route('/video_feed/cam1')
# def video_feed_cam1():
#     return Response(generate_feed(ESP32_CAM1_URL, VEHICLES), mimetype='multipart/x-mixed-replace; boundary=frame')
#
#
# @app.route('/video_feed/cam2')
# def video_feed_cam2():
#     return Response(generate_feed(ESP32_CAM2_URL, ANIMALS_HUMANS), mimetype='multipart/x-mixed-replace; boundary=frame')
#
#
# @app.route('/get_distances')
# def get_distances():
#     vehicle_distance = VEHICLE_DISTANCE if VEHICLE_DISTANCE is not None else 0
#     obstacle_distance = CAM2_DISTANCE if CAM2_DISTANCE is not None else 0
#     total_distance = vehicle_distance + obstacle_distance + 1  # 1ft assumed camera distance
#
#     print(f"Sending distances: Vehicle={vehicle_distance}, Obstacle={obstacle_distance}, Total={total_distance}")  # Debugging
#
#     return jsonify({
#         "vehicle_distance": round(vehicle_distance, 2),
#         "obstacle_distance": round(obstacle_distance, 2),
#         "total_distance": round(total_distance, 2)
#     })
#
#
#
# if __name__ == "__main__":
#     loop = asyncio.get_event_loop()
#     loop.create_task(receive_cam2_distance())
#     app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
import cv2
import numpy as np
from flask import Flask, render_template, Response
from flask_cors import CORS
from ultralytics import YOLO

# Initialize Flask App
app = Flask(__name__)
CORS(app)  # Enable CORS

# ESP32-CAM URLs
ESP32_CAM1_URL = "http://192.168.123.100:81/stream"  # Vehicle Detector
ESP32_CAM2_URL = "http://192.168.123.194:81/stream"  # Obstacle Detector

# Load YOLOv8 Model
model = YOLO("yolov8m.pt")

# Object Categories
ANIMALS_HUMANS = ["person", "dog", "cat", "cow", "horse", "sheep"]  # CAM2
VEHICLES = ["car", "truck", "bus", "motorbike"]  # CAM1

# Constants for Distance Calculation
KNOWN_HEIGHT_OBJ = 1.5  # Example: Average vehicle height in meters
FOCAL_LENGTH = 50  # Estimated focal length from camera calibration


def calculate_distance(bbox_height):
    """Calculates object distance from the camera using a known height."""
    if bbox_height > 0:
        distance_meters = (KNOWN_HEIGHT_OBJ * FOCAL_LENGTH) / bbox_height
        return round(distance_meters * 3.281, 2)  # Convert meters to feet
    return None


def generate_feed(cam_url, object_classes):
    """Generates the camera feed with bounding boxes and distances."""
    cap = cv2.VideoCapture(cam_url)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            continue

        results = model(frame)
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = r.names[int(box.cls[0])]

                if label in object_classes:
                    bbox_height = y2 - y1
                    distance = calculate_distance(bbox_height)

                    # Draw Bounding Box & Label
                    color = (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    text = f"{label}: {distance} ft" if distance else label
                    cv2.putText(frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

    cap.release()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed/cam1')
def video_feed_cam1():
    return Response(generate_feed(ESP32_CAM1_URL, VEHICLES), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_feed/cam2')
def video_feed_cam2():
    return Response(generate_feed(ESP32_CAM2_URL, ANIMALS_HUMANS), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
