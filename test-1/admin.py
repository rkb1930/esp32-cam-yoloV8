from flask import Flask, render_template, jsonify, Response, send_from_directory
import requests
import time
import threading
import json
import os
import io
from PIL import Image

app = Flask(__name__)

# Configuration
ADMIN_SERVER_URL = "http://192.168.212.44:5000/"  # Change this to the admin server IP
REFRESH_INTERVAL = 1.0  # Time in seconds between data refreshes
DATA_FILE = "client_data.json"
IMAGE_CACHE_DIR = "detections"  # Local directory to cache images

# Create image cache directory if it doesn't exist
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

# Global variables for caching data
latest_data = {
    'cam1_detections': [],
    'cam2_detections': [],
    'camera_distance': 1.0,
    'total_distance': 1.0,
    'timestamp': time.time(),
    'status': 'Initializing',
    'connected': False,
    'latest_images': []  # To store paths of latest obstacle images
}

# Store the latest monitor image data
latest_monitor_image = None
latest_monitor_image_path = None
last_image_update = 0


def fetch_data_thread():
    """Background thread to periodically fetch data from the admin server"""
    global latest_data, latest_monitor_image, latest_monitor_image_path, last_image_update
    while True:
        try:
            # Fetch JSON data
            response = requests.get(f"{ADMIN_SERVER_URL}/data", timeout=2)
            if response.status_code == 200:
                data = response.json()
                # Remove closest distances
                data.pop('closest_obstacle_distance', None)
                data.pop('closest_vehicle_distance', None)
                data['status'] = 'Connected'
                data['connected'] = True

                # Maintain the latest images list
                if 'latest_images' in latest_data:
                    data['latest_images'] = latest_data['latest_images']
                else:
                    data['latest_images'] = []

                latest_data = data

                # Save to file for persistence
                with open(DATA_FILE, 'w') as f:
                    json.dump(latest_data, f)
            else:
                latest_data['status'] = f"Error: HTTP {response.status_code}"
                latest_data['connected'] = False

            # Fetch latest obstacle images list
            try:
                img_response = requests.get(f"{ADMIN_SERVER_URL}/obstacle_images", timeout=2)
                if img_response.status_code == 200:
                    image_list = img_response.json()
                    latest_data['latest_images'] = image_list

                    # Download the most recent images if we don't have them cached
                    for img_info in image_list[:5]:  # Limit to most recent 5 images
                        img_path = img_info['path']
                        local_path = os.path.join(IMAGE_CACHE_DIR, os.path.basename(img_path))

                        if not os.path.exists(local_path):
                            download_image(img_path, local_path)

                    # Use the first image as the monitor image if available
                    if image_list and len(image_list) > 0:
                        img_path = image_list[0]['path']
                        local_path = os.path.join(IMAGE_CACHE_DIR, os.path.basename(img_path))
                        if os.path.exists(local_path):
                            with open(local_path, 'rb') as f:
                                latest_monitor_image = f.read()
                            latest_monitor_image_path = os.path.basename(img_path)
                            last_image_update = time.time()
            except requests.exceptions.RequestException:
                # If image fetch fails, continue with existing data
                pass

            # Fetch the latest monitor image
            current_time = time.time()
            if current_time - last_image_update >= REFRESH_INTERVAL:
                try:
                    img_response = requests.get(f"{ADMIN_SERVER_URL}/monitor_image", timeout=2, stream=True)
                    if img_response.status_code == 200:
                        latest_monitor_image = img_response.content
                        # Save the monitor image to disk
                        monitor_img_path = os.path.join(IMAGE_CACHE_DIR, f"monitor_{int(time.time())}.jpg")
                        with open(monitor_img_path, 'wb') as f:
                            f.write(latest_monitor_image)
                        latest_monitor_image_path = os.path.basename(monitor_img_path)
                        last_image_update = current_time
                except requests.exceptions.RequestException:
                    # If monitor image fetch fails, keep the existing image
                    pass

        except requests.exceptions.RequestException as e:
            latest_data['status'] = f"Connection error: {str(e)}"
            latest_data['connected'] = False

        time.sleep(REFRESH_INTERVAL)


def download_image(remote_path, local_path):
    """Download an image from the admin server and cache it locally"""
    try:
        img_response = requests.get(f"{ADMIN_SERVER_URL}/get_image/{os.path.basename(remote_path)}", timeout=2)
        if img_response.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(img_response.content)
            return True
    except requests.exceptions.RequestException:
        return False
    return False


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('client_index.html')


@app.route('/data')
def get_data():
    """API endpoint to get the latest fetched data"""
    data_to_send = latest_data.copy()
    if latest_monitor_image_path:
        data_to_send['monitor_image_path'] = latest_monitor_image_path
    return jsonify(data_to_send)


@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve cached images"""
    return send_from_directory(IMAGE_CACHE_DIR, filename)


@app.route('/image')
def get_monitor_image():
    """API endpoint to get the latest monitor image"""
    global latest_monitor_image, latest_monitor_image_path

    if latest_monitor_image:
        return Response(latest_monitor_image, mimetype='image/jpeg')
    else:
        # Try to find the most recent image in the cache
        image_files = [f for f in os.listdir(IMAGE_CACHE_DIR) if f.endswith('.jpg') or f.endswith('.jpeg')]
        if image_files:
            # Sort by modification time, most recent first
            image_files.sort(key=lambda x: os.path.getmtime(os.path.join(IMAGE_CACHE_DIR, x)), reverse=True)
            latest_image_path = os.path.join(IMAGE_CACHE_DIR, image_files[0])
            with open(latest_image_path, 'rb') as f:
                image_data = f.read()
            return Response(image_data, mimetype='image/jpeg')
        else:
            # Create a simple placeholder image if no image is available
            img = Image.new('RGB', (400, 300), color=(200, 200, 200))
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG')
            img_io.seek(0)
            return Response(img_io.getvalue(), mimetype='image/jpeg')


def main():
    """Main function to start all threads and the Flask app"""
    # Try to load any previously saved data
    global latest_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                latest_data = json.load(f)
        except json.JSONDecodeError:
            pass

    # Start data fetching thread
    data_thread = threading.Thread(target=fetch_data_thread)
    data_thread.daemon = True
    data_thread.start()

    # Start Flask app
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)


if __name__ == '__main__':
    main()