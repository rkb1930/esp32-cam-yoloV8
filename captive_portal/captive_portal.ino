// #include <WiFi.h>
// #include <ESPAsyncWebServer.h>
// #include <DNSServer.h>

// const char* apSSID = "ESP32-Alert";  

// AsyncWebServer server(80);
// DNSServer dnsServer;

// void setup() {
//     Serial.begin(115200);

   
//     WiFi.softAP(apSSID);
//     IPAddress myAPIP = WiFi.softAPIP();
//     Serial.print("Captive Portal Active! IP: ");
//     Serial.println(myAPIP);

    
//     dnsServer.start(53, "*", myAPIP);

   
//     server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->redirect("/alert");
//     });

    
//     server.on("/generate_204", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
//     });

//     server.on("/hotspot-detect.html", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
//     });

//     server.on("/ncsi.txt", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
//     });

//     server.on("/fwlink", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
//     });

    
//     server.on("/alert", HTTP_GET, [](AsyncWebServerRequest *request){
//         request->send(200, "text/html",
//         "<html><body style='text-align:center; font-family:Arial;'>"
//         "<h2 style='color:red;'>Accident Can Happen</h2>"
//         "<h3>Drive Carefully</h3>"
//         "<p>Stay Safe!</p>"
//         "</body></html>");
//     });

    
//     server.onNotFound([](AsyncWebServerRequest *request) {
//         request->redirect("/alert");
//     });

    
//     server.begin();
// }

// void loop() {
//     dnsServer.processNextRequest(); 
//     delay(100);
// }




#include "esp_camera.h"
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <DNSServer.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// Camera model definition
#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"

// WiFi Credentials for external connection
const char* ssid = "Baibhav";
const char* password = "bbbsss2225";
const char* hostname = "ESP32-CAM1";

// Access Point settings for captive portal
const char* apSSID = "ESP32-Alert";
IPAddress myAPIP;

// Servers
AsyncWebServer server(80);
DNSServer dnsServer;

// Captive portal HTML
const char portal_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      text-align: center;
      font-family: Arial;
      margin-top: 20px;
    }
    .alert {
      color: red;
      font-size: 24px;
      margin-bottom: 10px;
    }
    .message {
      font-size: 18px;
      margin-bottom: 20px;
    }
    .cam-link {
      display: inline-block;
      margin-top: 20px;
      padding: 10px 20px;
      background-color: #4CAF50;
      color: white;
      text-decoration: none;
      border-radius: 5px;
    }
    .wifi-info {
      margin-top: 30px;
      padding: 10px;
      background-color: #f1f1f1;
      border-radius: 5px;
      display: inline-block;
    }
  </style>
</head>
<body>
  <div class="alert"><b>Accident Can Happen</b></div>
  <div class="message">Drive Carefully</div>
  <p>Stay Safe!</p>
  
  <a href="/camera" class="cam-link">View Camera Feed</a>
  
  <div class="wifi-info">
    <p>ESP32 is also streaming to WiFi network: <b>Apache</b></p>
    <p>Stream available at: <span id="stream-url">Connecting...</span></p>
  </div>
  
  <script>
    // This will be filled in by the server with the actual IP
    document.getElementById('stream-url').innerHTML = '[[STREAM_URL]]';
  </script>
</body>
</html>
)rawliteral";

// Camera view HTML
const char camera_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      text-align: center;
      font-family: Arial;
      margin-top: 20px;
    }
    h2 {
      color: #333;
    }
    .camera-container {
      max-width: 640px;
      margin: 0 auto;
    }
    img {
      width: 100%;
      max-width: 640px;
      height: auto;
      border: 1px solid #ddd;
    }
    .portal-link {
      display: inline-block;
      margin-top: 20px;
      padding: 10px 20px;
      background-color: #2196F3;
      color: white;
      text-decoration: none;
      border-radius: 5px;
    }
  </style>
</head>
<body>
  <h2>ESP32-CAM Live Feed</h2>
  
  <div class="camera-container">
    <img src="/stream" id="stream">
  </div>
  
  <a href="/alert" class="portal-link">Back to Alert Page</a>
  
  <script>
    window.onload = function() {
      var img = document.getElementById("stream");
      img.onerror = function() {
        setTimeout(function() {
          img.src = "/stream?" + new Date().getTime();
        }, 1000);
      };
    };
  </script>
</body>
</html>
)rawliteral";

// Global variable to store the external WiFi stream URL
String streamUrl = "Not connected";

// External function from app_httpd.cpp
void startCameraServer();  // Just declare, don't implement

// Function to initialize camera
bool initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    // Lower quality for stable streaming
    if (psramFound()) {
        config.frame_size = FRAMESIZE_QVGA;  // Use QVGA for better performance
        config.jpeg_quality = 15;            // Medium quality (1-63), lower is better
        config.fb_count = 2;
    } else {
        config.frame_size = FRAMESIZE_QVGA;
        config.jpeg_quality = 20;
        config.fb_count = 1;
    }

    // Initialize camera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed with error 0x%x\n", err);
        return false;
    }
    
    Serial.println("Camera initialized successfully!");
    return true;
}

// Handler for streaming MJPEG on the captive portal
void streamJpg(AsyncWebServerRequest *request) {
    camera_fb_t * fb = NULL;
    fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("Camera capture failed");
        request->send(500, "text/plain", "Camera capture failed");
        return;
    }

    request->send_P(200, "image/jpeg", (const uint8_t *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Disable brownout detector
    
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println("ESP32-CAM with Captive Portal");
    
    // Initialize the camera
    if (!initCamera()) {
        Serial.println("Camera initialization failed!");
        return;
    }
    
    // Setup Access Point for captive portal
    WiFi.mode(WIFI_AP_STA); // Set WiFi to station (client) and AP modes
    
    // Setup the Access Point
    WiFi.softAP(apSSID);
    myAPIP = WiFi.softAPIP();
    Serial.print("Captive Portal Active! IP: ");
    Serial.println(myAPIP);
    
    // Setup routes for captive portal
    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
        request->redirect("/alert");
    });
    
    // Handle alert page with dynamic WiFi streaming URL
    server.on("/alert", HTTP_GET, [](AsyncWebServerRequest *request){
        String html = String(portal_html);
        html.replace("[[STREAM_URL]]", streamUrl);
        request->send(200, "text/html", html);
    });
    
    // Camera routes
    server.on("/camera", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send_P(200, "text/html", camera_html);
    });
    
    server.on("/stream", HTTP_GET, [](AsyncWebServerRequest *request){
        streamJpg(request);
    });
    
    // Captive portal redirection routes
    server.on("/generate_204", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
    });
    
    server.on("/hotspot-detect.html", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
    });
    
    server.on("/ncsi.txt", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
    });
    
    server.on("/fwlink", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(200, "text/html", "<script>window.location.href='/alert';</script>");
    });
    
    // Redirect all not found requests to the alert page
    server.onNotFound([](AsyncWebServerRequest *request) {
        request->redirect("/alert");
    });
    
    // Start DNS server for captive portal
    dnsServer.start(53, "*", myAPIP);
    
    // Start web server
    server.begin();
    Serial.println("HTTP server started for captive portal");
    
    // Connect to WiFi network for streaming
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    
    // Set a timeout for WiFi connection (10 seconds)
    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        
        // Break after 10 seconds if not connected
        if (millis() - startTime > 10000) {
            Serial.println("\nFailed to connect to WiFi");
            streamUrl = "WiFi connection failed";
            break;
        }
    }
    
    // If connected, start the camera server
    if (WiFi.status() == WL_CONNECTED) {
        WiFi.setHostname(hostname);
        Serial.println("\nWiFi Connected!");
        Serial.print("ESP32 Stream URL: http://");
        Serial.print(WiFi.localIP());
        Serial.println(":81/stream");
        
        // Update the stream URL for display on captive portal
        streamUrl = "http://" + WiFi.localIP().toString() + ":81/stream";
        
        // Start the camera server on WiFi connection
        startCameraServer();
    }
}

void loop() {
    // Handle DNS requests for captive portal
    dnsServer.processNextRequest();
    
    // Check if WiFi got connected later
    if (WiFi.status() == WL_CONNECTED && streamUrl == "WiFi connection failed") {
        Serial.println("WiFi Connected!");
        Serial.print("ESP32 Stream URL: http://");
        Serial.print(WiFi.localIP());
        Serial.println(":81/stream");
        
        streamUrl = "http://" + WiFi.localIP().toString() + ":81/stream";
        
        // Start the camera server
        startCameraServer();
    }
    
    delay(10);
}