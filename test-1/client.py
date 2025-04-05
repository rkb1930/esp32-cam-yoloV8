from flask import Flask, render_template, jsonify
import requests
import time
import threading
import json
import os

app = Flask(__name__)

# Configuration
ADMIN_SERVER_URL = "http://192.168.212.44:5000/"  # Change this to the admin server IP
REFRESH_INTERVAL = 1.0  # Time in seconds between data refreshes
DATA_FILE = "client_data.json"

# Global variables for caching data
latest_data = {
    'cam1_detections': [],
    'cam2_detections': [],
    'closest_obstacle_distance': 0,
    'closest_vehicle_distance': 0,
    'camera_distance': 1.0,
    'total_distance': 1.0,
    'timestamp': time.time(),
    'status': 'Initializing',
    'connected': False
}


def fetch_data_thread():
    """Background thread to periodically fetch data from the admin server"""
    global latest_data

    while True:
        try:
            response = requests.get(f"{ADMIN_SERVER_URL}/data", timeout=2)
            if response.status_code == 200:
                data = response.json()
                data['status'] = 'Connected'
                data['connected'] = True
                latest_data = data

                # Save to file for persistence
                with open(DATA_FILE, 'w') as f:
                    json.dump(latest_data, f)
            else:
                latest_data['status'] = f"Error: HTTP {response.status_code}"
                latest_data['connected'] = False
        except requests.exceptions.RequestException as e:
            latest_data['status'] = f"Connection error: {str(e)}"
            latest_data['connected'] = False

        time.sleep(REFRESH_INTERVAL)


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('client_index.html')


@app.route('/data')
def get_data():
    """API endpoint to get the latest fetched data"""
    return jsonify(latest_data)


def create_templates():
    """Create the required templates directory and HTML file"""
    if not os.path.exists('templates'):
        os.makedirs('templates')

    with open('templates/client_index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Distance Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
        }

        h1 {
            text-align: center;
            color: #2c3e50;
            margin-top: 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
            font-size: 24px;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }

        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }

        .status-online {
            background-color: #28a745;
        }

        .status-offline {
            background-color: #dc3545;
        }

        .main-display {
            text-align: center;
            padding: 20px;
            background-color: #e7f3ff;
            border-radius: 10px;
            margin-bottom: 20px;
        }

        .main-label {
            font-size: 16px;
            margin-bottom: 5px;
        }

        .total-distance {
            font-size: 38px;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        }

        .distance-cards {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }

        .distance-card {
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        .card-title {
            font-size: 14px;
            color: #6c757d;
            margin-bottom: 5px;
        }

        .card-value {
            font-size: 24px;
            font-weight: bold;
        }

        .obstacle-value {
            color: #d9534f;
        }

        .vehicle-value {
            color: #337ab7;
        }

        .footer {
            text-align: center;
            font-size: 12px;
            color: #6c757d;
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }

        @media (max-width: 600px) {
            .distance-cards {
                grid-template-columns: 1fr;
            }

            .total-distance {
                font-size: 32px;
            }

            .card-value {
                font-size: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Distance Monitor</h1>

        <div class="status-bar">
            <div>
                <span class="status-indicator" id="connection-indicator"></span>
                <span id="connection-status">Connecting...</span>
            </div>
            <div id="last-updated">Last updated: --:--:--</div>
        </div>

        <div class="main-display">
            <div class="main-label">Total Distance</div>
            <div class="total-distance" id="total-distance">0.00 m</div>
        </div>

        <div class="distance-cards">
            <div class="distance-card">
                <div class="card-title">Closest Obstacle</div>
                <div class="card-value obstacle-value" id="obstacle-distance">0.00 m</div>
            </div>

            <div class="distance-card">
                <div class="card-title">Closest Vehicle</div>
                <div class="card-value vehicle-value" id="vehicle-distance">0.00 m</div>
            </div>
        </div>

        <div class="footer">
            Distance Monitor | Updates every second
        </div>
    </div>

    <script>
        // Update data function
        function updateData() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    // Update connection status
                    const indicator = document.getElementById('connection-indicator');
                    const statusText = document.getElementById('connection-status');

                    if (data.connected) {
                        indicator.className = 'status-indicator status-online';
                        statusText.textContent = 'Connected';
                    } else {
                        indicator.className = 'status-indicator status-offline';
                        statusText.textContent = 'Disconnected';
                    }

                    // Update distance values
                    document.getElementById('total-distance').textContent = data.total_distance.toFixed(2) + ' m';
                    document.getElementById('obstacle-distance').textContent = data.closest_obstacle_distance.toFixed(2) + ' m';
                    document.getElementById('vehicle-distance').textContent = data.closest_vehicle_distance.toFixed(2) + ' m';

                    // Update last updated time
                    const now = new Date();
                    const timeString = now.toLocaleTimeString();
                    document.getElementById('last-updated').textContent = 'Updated: ' + timeString;
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                    document.getElementById('connection-indicator').className = 'status-indicator status-offline';
                    document.getElementById('connection-status').textContent = 'Disconnected';
                });
        }

        // Update data every second
        setInterval(updateData, 1000);

        // Initial update
        updateData();
    </script>
</body>
</html>
        ''')


def main():
    """Main function to start all threads and the Flask app"""
    # Create necessary template files
    create_templates()

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