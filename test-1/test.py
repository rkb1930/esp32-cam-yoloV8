import cv2
import numpy as np
import time
from flask import Flask, render_template, Response, jsonify
from ultralytics import YOLO
import math
import threading
import queue
import json
import os

app = Flask(__name__)

# Configuration
CAM1_URL = "http://192.168.212.194:81/stream"  # Using your provided URL
CAM2_URL = "http://192.168.212.100:81/stream"  # Replace with your ESP32 CAM2 IP stream URL

# Distance between cameras (in meters)
CAMERA_DISTANCE = 1.0  # As specified in your requirement

# Set standard resolution for both cameras
STANDARD_WIDTH = 640
STANDARD_HEIGHT = 480

# Initialize YOLOv8 model
model = YOLO("yolov8n.pt")  # Using the nano version, you can use s, m, l, or x for better accuracy

# Camera calibration parameters (you'll need to calibrate your cameras)
# These are placeholder values - you'll need to replace with actual calibrated values
FOCAL_LENGTH_CAM1 = 800  # focal length in pixels for camera 1
FOCAL_LENGTH_CAM2 = 800  # focal length in pixels for camera 2
KNOWN_WIDTH_PERSON = 0.6  # average width of a person in meters
KNOWN_WIDTH_VEHICLE = 1.8  # average width of a vehicle in meters

# Classes for obstacle detection (CAM1) - adjust based on your needs
OBSTACLE_CLASSES = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck as obstacles

# Classes for vehicle detection (CAM2)
VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck

# Queues for frames and results
cam1_queue = queue.Queue(maxsize=10)
cam2_queue = queue.Queue(maxsize=10)
cam1_results_queue = queue.Queue(maxsize=10)
cam2_results_queue = queue.Queue(maxsize=10)

# File paths for storing JSON data
DATA_DIR = 'data'
CAM1_DATA_FILE = os.path.join(DATA_DIR, 'cam1_detections.json')
CAM2_DATA_FILE = os.path.join(DATA_DIR, 'cam2_detections.json')
COMBINED_DATA_FILE = os.path.join(DATA_DIR, 'combined_detections.json')


def ensure_data_dir():
    """Ensure data directory exists"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def calculate_distance(bbox_width, focal_length, known_width):
    """
    Calculate distance based on apparent object size
    """
    # Using the formula: distance = (known_width * focal_length) / apparent_width
    distance = (known_width * focal_length) / bbox_width

    # Add 20 meters as per requirement
    adjusted_distance = distance + 20

    return distance, adjusted_distance


def resize_frame(frame, width=STANDARD_WIDTH, height=STANDARD_HEIGHT):
    """
    Resize frame to standard resolution
    """
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def capture_camera_feed(cam_url, output_queue):
    """
    Capture feed from IP camera and put frames into queue
    """
    cap = cv2.VideoCapture(cam_url)

    if not cap.isOpened():
        print(f"Error: Unable to open camera feed at {cam_url}")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Error: Could not read frame from {cam_url}")
            time.sleep(1)  # Wait before retrying
            cap = cv2.VideoCapture(cam_url)  # Try to reconnect
            continue

        # Resize frame to standard resolution
        frame = resize_frame(frame, STANDARD_WIDTH, STANDARD_HEIGHT)

        # If queue is full, remove old frame
        if output_queue.full():
            try:
                output_queue.get_nowait()
            except queue.Empty:
                pass

        output_queue.put(frame)
        time.sleep(0.1)  # Reduce CPU usage


def process_frames(input_queue, output_queue, is_cam1, json_file_path):
    """
    Process frames with YOLOv8 and calculate distances
    """
    while True:
        if not input_queue.empty():
            frame = input_queue.get()

            # Run YOLOv8 on the frame
            results = model(frame)

            # Process results
            processed_frame = frame.copy()
            detections = []

            for r in results:
                boxes = r.boxes

                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])

                    # Check if the class is what we're looking for
                    if (is_cam1 and cls in OBSTACLE_CLASSES) or (not is_cam1 and cls in VEHICLE_CLASSES):
                        x1, y1, x2, y2 = map(int, box.xyxy[0])

                        # Calculate width of bounding box
                        bbox_width = x2 - x1

                        # Determine which objects to track
                        if is_cam1:  # CAM1 - Obstacles
                            known_width = KNOWN_WIDTH_PERSON if cls == 0 else KNOWN_WIDTH_VEHICLE
                            focal_length = FOCAL_LENGTH_CAM1
                            color = (0, 0, 255)  # Red for obstacles
                        else:  # CAM2 - Vehicles
                            known_width = KNOWN_WIDTH_VEHICLE
                            focal_length = FOCAL_LENGTH_CAM2
                            color = (255, 0, 0)  # Blue for vehicles

                        # Calculate distances
                        original_distance, adjusted_distance = calculate_distance(bbox_width, focal_length, known_width)

                        # Draw bounding box
                        cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 2)

                        # Get class name
                        cls_name = model.names[cls]

                        # Draw text with distance
                        text = f"{cls_name}: {adjusted_distance:.2f}m"
                        cv2.putText(processed_frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                        # Store detection info
                        detections.append({
                            'class': cls_name,
                            'confidence': conf,
                            'original_distance': original_distance,
                            'adjusted_distance': adjusted_distance,
                            'bbox': (x1, y1, x2, y2),
                            'timestamp': time.time()
                        })

            # Save detections to JSON file
            with open(json_file_path, 'w') as f:
                json.dump(detections, f)

            # Put processed frame and detections in output queue
            if output_queue.full():
                try:
                    output_queue.get_nowait()
                except queue.Empty:
                    pass

            output_queue.put((processed_frame, detections))

            # Update combined data file with total distance calculation
            update_combined_data()

        time.sleep(0.05)  # Small delay to reduce CPU usage


def update_combined_data():
    """
    Update the combined data file with calculations for total distance
    """
    try:
        # Read cam1 data
        if os.path.exists(CAM1_DATA_FILE):
            with open(CAM1_DATA_FILE, 'r') as f:
                cam1_data = json.load(f)
        else:
            cam1_data = []

        # Read cam2 data
        if os.path.exists(CAM2_DATA_FILE):
            with open(CAM2_DATA_FILE, 'r') as f:
                cam2_data = json.load(f)
        else:
            cam2_data = []

        # Calculate closest obstacles and vehicles
        closest_obstacle_distance = float('inf')
        closest_vehicle_distance = float('inf')

        for detection in cam1_data:
            if detection['adjusted_distance'] < closest_obstacle_distance:
                closest_obstacle_distance = detection['adjusted_distance']

        for detection in cam2_data:
            if detection['adjusted_distance'] < closest_vehicle_distance:
                closest_vehicle_distance = detection['adjusted_distance']

        # Handle cases where no detections are available
        if closest_obstacle_distance == float('inf'):
            closest_obstacle_distance = 0

        if closest_vehicle_distance == float('inf'):
            closest_vehicle_distance = 0

        # Calculate total distance
        total_distance = closest_obstacle_distance + closest_vehicle_distance + CAMERA_DISTANCE

        # Create combined data
        combined_data = {
            'cam1_detections': cam1_data,
            'cam2_detections': cam2_data,
            'closest_obstacle_distance': closest_obstacle_distance,
            'closest_vehicle_distance': closest_vehicle_distance,
            'camera_distance': CAMERA_DISTANCE,
            'total_distance': total_distance,
            'timestamp': time.time()
        }

        # Save to combined file
        with open(COMBINED_DATA_FILE, 'w') as f:
            json.dump(combined_data, f)

    except Exception as e:
        print(f"Error updating combined data: {e}")


def generate_frames(cam_results_queue):
    """
    Generator function for streaming processed frames
    """
    while True:
        if not cam_results_queue.empty():
            processed_frame, _ = cam_results_queue.get()

            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', processed_frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            time.sleep(0.1)


@app.route('/')
def index():
    """
    Main dashboard page
    """
    return render_template('index.html')


@app.route('/video_feed/cam1')
def video_feed_cam1():
    """
    Route for streaming CAM1 (obstacles)
    """
    return Response(generate_frames(cam1_results_queue),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_feed/cam2')
def video_feed_cam2():
    """
    Route for streaming CAM2 (vehicles)
    """
    return Response(generate_frames(cam2_results_queue),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/data')
def get_data():
    """
    API endpoint to get the latest detection data as JSON
    """
    # Check if combined data file exists
    if os.path.exists(COMBINED_DATA_FILE):
        with open(COMBINED_DATA_FILE, 'r') as f:
            combined_data = json.load(f)
        return jsonify(combined_data)
    else:
        # Fallback if file doesn't exist yet
        return jsonify({
            'cam1_detections': [],
            'cam2_detections': [],
            'closest_obstacle_distance': 0,
            'closest_vehicle_distance': 0,
            'camera_distance': CAMERA_DISTANCE,
            'total_distance': CAMERA_DISTANCE,
            'timestamp': time.time()
        })


def create_templates():
    """
    Create the required templates for Flask
    """
    import os

    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # Create index.html
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Dual Camera Object Detection</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f0f0f0;
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .container {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-around;
            margin-bottom: 20px;
        }
        .camera-container {
            width: 45%;
            min-width: 400px;
            margin: 10px;
            background-color: white;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .camera-feed {
            width: 100%;
            border-radius: 5px;
            height: auto;
            object-fit: contain;
        }
        .detection-info {
            margin-top: 15px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
            height: 200px;
            overflow-y: auto;
        }
        .total-distance {
            background-color: #e7f3ff;
            padding: 15px;
            border-radius: 10px;
            margin: 20px auto;
            width: 90%;
            max-width: 800px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .total-value {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }
        .distance-breakdown {
            display: flex;
            justify-content: space-around;
            margin-top: 15px;
            text-align: center;
        }
        .distance-component {
            padding: 10px;
            border-radius: 5px;
            background-color: #f8f9fa;
            width: 30%;
        }
        h2 {
            color: #555;
            margin-top: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .obstacle {
            color: #d9534f;
        }
        .vehicle {
            color: #337ab7;
        }
        .resolution-info {
            text-align: center;
            margin-bottom: 10px;
            font-size: 14px;
            color: #666;
        }
        @media (max-width: 900px) {
            .camera-container {
                width: 90%;
            }
            .distance-breakdown {
                flex-direction: column;
                align-items: center;
            }
            .distance-component {
                width: 80%;
                margin-bottom: 10px;
            }
        }
    </style>
</head>
<body>
    <h1>ESP32 Dual Camera Object Detection Dashboard</h1>
    <div class="resolution-info">Camera Resolution: 640 x 480</div>

    <div class="total-distance">
        <h2>Total Distance Calculation</h2>
        <div class="total-value" id="total-distance">0.00 m</div>
        <div class="distance-breakdown">
            <div class="distance-component">
                <h3>Closest Obstacle</h3>
                <div id="obstacle-distance">0.00 m</div>
            </div>
            <div class="distance-component">
                <h3>Camera Separation</h3>
                <div id="camera-distance">1.00 m</div>
            </div>
            <div class="distance-component">
                <h3>Closest Vehicle</h3>
                <div id="vehicle-distance">0.00 m</div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="camera-container">
            <h2>Camera 1: Obstacle Detection</h2>
            <img src="{{ url_for('video_feed_cam1') }}" class="camera-feed">
            <div class="detection-info">
                <h3>Detected Obstacles</h3>
                <table id="obstacles-table">
                    <thead>
                        <tr>
                            <th>Object</th>
                            <th>Distance (m)</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody id="obstacles-data">
                        <!-- Will be populated by JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>

        <div class="camera-container">
            <h2>Camera 2: Vehicle Detection</h2>
            <img src="{{ url_for('video_feed_cam2') }}" class="camera-feed">
            <div class="detection-info">
                <h3>Detected Vehicles</h3>
                <table id="vehicles-table">
                    <thead>
                        <tr>
                            <th>Vehicle</th>
                            <th>Distance (m)</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody id="vehicles-data">
                        <!-- Will be populated by JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // Function to update detection data
        function updateDetectionData() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    // Update obstacles table
                    const obstaclesTable = document.getElementById('obstacles-data');
                    obstaclesTable.innerHTML = '';

                    data.cam1_detections.forEach(item => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td class="obstacle">${item.class}</td>
                            <td>${item.adjusted_distance.toFixed(2)}</td>
                            <td>${(item.confidence * 100).toFixed(1)}%</td>
                        `;
                        obstaclesTable.appendChild(row);
                    });

                    // Update vehicles table
                    const vehiclesTable = document.getElementById('vehicles-data');
                    vehiclesTable.innerHTML = '';

                    data.cam2_detections.forEach(item => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td class="vehicle">${item.class}</td>
                            <td>${item.adjusted_distance.toFixed(2)}</td>
                            <td>${(item.confidence * 100).toFixed(1)}%</td>
                        `;
                        vehiclesTable.appendChild(row);
                    });

                    // Update total distance calculation
                    document.getElementById('total-distance').textContent = `${data.total_distance.toFixed(2)} m`;
                    document.getElementById('obstacle-distance').textContent = `${data.closest_obstacle_distance.toFixed(2)} m`;
                    document.getElementById('vehicle-distance').textContent = `${data.closest_vehicle_distance.toFixed(2)} m`;
                    document.getElementById('camera-distance').textContent = `${data.camera_distance.toFixed(2)} m`;
                })
                .catch(error => console.error('Error fetching data:', error));
        }

        // Update data every second
        setInterval(updateDetectionData, 1000);

        // Initial update
        updateDetectionData();
    </script>
</body>
</html>
        ''')


def main():
    """
    Main function to start all threads and the Flask app
    """
    # Ensure data directory exists
    ensure_data_dir()

    # Create necessary template files
    create_templates()

    # Start camera feed threads
    cam1_thread = threading.Thread(target=capture_camera_feed, args=(CAM1_URL, cam1_queue))
    cam2_thread = threading.Thread(target=capture_camera_feed, args=(CAM2_URL, cam2_queue))
    cam1_thread.daemon = True
    cam2_thread.daemon = True
    cam1_thread.start()
    cam2_thread.start()

    # Start processing threads
    cam1_processing_thread = threading.Thread(target=process_frames,
                                              args=(cam1_queue, cam1_results_queue, True, CAM1_DATA_FILE))
    cam2_processing_thread = threading.Thread(target=process_frames,
                                              args=(cam2_queue, cam2_results_queue, False, CAM2_DATA_FILE))
    cam1_processing_thread.daemon = True
    cam2_processing_thread.daemon = True
    cam1_processing_thread.start()
    cam2_processing_thread.start()

    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)


if __name__ == '__main__':
    main()