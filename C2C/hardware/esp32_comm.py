"""
ESP32 Communication Module

Handles serial communication with ESP32 microcontroller.
Ensures command synchronization between simulation and hardware.

CRITICAL RULES:
1. ESP32 receives IDENTICAL commands as simulator
2. No computation on ESP32 - only motor control
3. PC calculates all kinematics
4. Line-by-line command parsing
5. Emergency stop has highest priority

CONTROL LAYERS:
1. Serial Link - ACK/SYNC protocol handling
2. Motion Queue - Buffered command execution
3. Watchdog - Communication health monitoring
"""

import serial
import serial.tools.list_ports
import threading
import queue
import time

# Import new control layers
from .serial_link import ESP32Serial
from .motion_queue import MotionQueue
from .watchdog import Watchdog, WatchdogTimeout


class ESP32Communicator:
    """
    Serial communication handler for ESP32 with 3-layer control architecture.
    
    LAYERS:
    1. Serial Link - Low-level communication + ACK parsing
    2. Motion Queue - Buffered execution with sync
    3. Watchdog - Communication health monitoring
    
    This provides industrial-grade deterministic control.
    """
    
    def __init__(self, port=None, baudrate=115200, enable_watchdog=True):
        """
        Initialize ESP32 communicator with control layers.
        
        Args:
            port: Serial port (e.g., 'COM3'). If None, will auto-detect.
            baudrate: Communication speed (default: 115200)
            enable_watchdog: Enable communication monitoring (recommended)
        """
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False
        
        # === CONTROL LAYERS ===
        self.serial_link = None      # Layer 1: Serial communication
        self.motion_queue = None     # Layer 2: Buffered commands
        self.watchdog = None         # Layer 3: Health monitoring
        
        # Legacy compatibility
        self.serial_conn = None
        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
        # Callback for received messages
        self.on_response_callback = None
        
        # Command logging
        self.command_log = []
        self.max_log_size = 1000
        
        # Watchdog enabled flag
        self.enable_watchdog = enable_watchdog
        
        # Update timer for queue processing
        self.update_thread = None
        self.running = False
    
    def list_available_ports(self):
        """
        List all available serial ports.
        
        Returns:
            list: List of port names
        """
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
    
    def connect(self, port=None):
        """
        Connect to ESP32 and initialize control layers.
        
        Args:
            port: Serial port. If None, uses self.port or auto-detects.
        
        Returns:
            bool: True if connected successfully
        """
        if self.is_connected:
            print("⚠ Already connected")
            return True
        
        if port:
            self.port = port
        
        # Auto-detect if no port specified
        if not self.port:
            ports = self.list_available_ports()
            if not ports:
                print("❌ No serial ports found")
                return False
            self.port = ports[0]
            print(f"🔍 Auto-selected port: {self.port}")
        
        try:
            # === LAYER 1: Initialize Serial Link ===
            self.serial_link = ESP32Serial(port=self.port, baudrate=self.baudrate)
            if not self.serial_link.connect():
                return False
            
            # Set up message callback
            self.serial_link.on_message = self._handle_esp32_message
            
            # === LAYER 2: Initialize Motion Queue ===
            self.motion_queue = MotionQueue(self.serial_link, max_size=100)
            print("✅ Motion Queue: Initialized")
            
            # === LAYER 3: Initialize Watchdog ===
            if self.enable_watchdog:
                self.watchdog = Watchdog(timeout=2.0, enable_heartbeat=False)
                
                # Connect watchdog to serial link
                original_msg_handler = self.serial_link.on_message
                
                def msg_handler_with_watchdog(msg):
                    self.watchdog.kick()  # Reset watchdog on any message
                    if msg == "HB":
                        self.watchdog.heartbeat()
                    if original_msg_handler:
                        original_msg_handler(msg)
                
                self.serial_link.on_message = msg_handler_with_watchdog
                
                # Set up watchdog callbacks
                self.watchdog.on_timeout = self._handle_watchdog_timeout
                
                print("✅ Watchdog: Enabled (2.0s timeout)")
            
            # Legacy compatibility
            self.serial_conn = self.serial_link.ser
            
            # Start update thread for queue processing
            self.running = True
            self.update_thread = threading.Thread(target=self._update_worker, daemon=True)
            self.update_thread.start()
            
            self.is_connected = True
            print(f"✅ ESP32 Communicator: All layers active")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize control layers: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """
        Disconnect from ESP32 and cleanup all layers.
        """
        if not self.is_connected:
            return
        
        # Stop update thread
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2)
        
        # Cleanup layers
        if self.motion_queue:
            self.motion_queue.clear()
        
        if self.watchdog:
            self.watchdog.disable()
        
        if self.serial_link:
            self.serial_link.disconnect()
        
        self.is_connected = False
        print("🔌 Disconnected from ESP32")
    
    def send_command(self, command_string, priority=False):
        """
        Send command to ESP32 through motion queue.
        
        Args:
            command_string: Command to send (from command_builder)
            priority: If True, sends immediately (for emergency stop)
        
        Returns:
            bool: True if queued/sent successfully
        """
        if not self.is_connected:
            print(f"⚠ Not connected - Command queued for simulation only:")
            print(command_string)
            self._log_command(command_string, sent=False)
            return False
        
        if priority:
            # Emergency stop - bypass queue
            print(f"🚨 EMERGENCY: {command_string[:50]}")
            if self.motion_queue:
                self.motion_queue.emergency_stop()
            else:
                self.serial_link.send(command_string)
            self._log_command(command_string, sent=True)
            return True
        else:
            # Queue command through motion queue
            if self.motion_queue:
                success = self.motion_queue.add(command_string)
                if success:
                    self._log_command(command_string, sent=False)  # Queued, not sent yet
                return success
            else:
                # Fallback if queue not initialized
                return self.serial_link.send(command_string)
    
    def _update_worker(self):
        """
        Worker thread for updating motion queue and watchdog.
        Runs at ~50 Hz.
        """
        while self.running:
            try:
                # Update motion queue (send next command if ready)
                if self.motion_queue:
                    self.motion_queue.update()
                
                # Check watchdog
                if self.watchdog and self.watchdog.enabled:
                    try:
                        self.watchdog.check()
                    except WatchdogTimeout as e:
                        print(f"🚨 WATCHDOG TIMEOUT: {e}")
                        # Emergency stop on watchdog timeout
                        if self.motion_queue:
                            self.motion_queue.emergency_stop()
                
                time.sleep(0.02)  # 50 Hz update rate
                
            except Exception as e:
                print(f"❌ Update worker error: {e}")
                time.sleep(0.1)
    
    def _handle_esp32_message(self, msg):
        """
        Handle messages from ESP32.
        
        Args:
            msg: Message string from ESP32
        """
        # Add to legacy response queue for compatibility
        self.response_queue.put(msg)
        
        # Call user callback
        if self.on_response_callback:
            try:
                self.on_response_callback(msg)
            except Exception as e:
                print(f"⚠ Response callback error: {e}")
    
    def _handle_watchdog_timeout(self, time_since_response):
        """
        Called when watchdog times out.
        
        Args:
            time_since_response: Time since last response in seconds
        """
        print(f"🚨 Communication lost - {time_since_response:.1f}s without response")
        print("🚨 Stopping all motion for safety")
    
    def _send_raw(self, command_string):
        """
        Send raw command through serial (internal use - legacy compatibility).
        """
        if self.serial_link:
            self.serial_link.send(command_string)
        elif self.serial_conn and self.serial_conn.is_open:
            # Fallback to direct serial
            if not command_string.endswith("\n"):
                command_string += "\n"
            self.serial_conn.write(command_string.encode('utf-8'))
            self.serial_conn.flush()
    
    def _log_command(self, command_string, sent=True):
        """
        Log command for debugging and validation.
        """
        timestamp = time.time()
        self.command_log.append({
            'timestamp': timestamp,
            'command': command_string,
            'sent': sent
        })
        
        # Trim log if too large
        if len(self.command_log) > self.max_log_size:
            self.command_log = self.command_log[-self.max_log_size:]
    
    def get_command_log(self, count=10):
        """
        Get recent commands from log.
        
        Args:
            count: Number of recent commands to return
        
        Returns:
            list: Recent command log entries
        """
        return self.command_log[-count:]
    
    def clear_command_log(self):
        """
        Clear command log.
        """
        self.command_log.clear()
    
    def wait_for_response(self, timeout=5.0):
        """
        Wait for response from ESP32.
        
        Args:
            timeout: Maximum wait time in seconds
        
        Returns:
            str: Response line or None if timeout
        """
        try:
            response = self.response_queue.get(timeout=timeout)
            self.response_queue.task_done()
            return response
        except queue.Empty:
            return None
    
    def is_ready(self):
        """
        Check if ESP32 is ready to receive commands.
        
        Returns:
            bool: True if connected and queue has space
        """
        if not self.is_connected:
            return False
        
        if self.motion_queue:
            return self.motion_queue.get_queue_size() < 50
        
        return True
    
    def get_queue_stats(self):
        """
        Get motion queue statistics.
        
        Returns:
            dict: Queue stats or None if not connected
        """
        if self.motion_queue:
            return self.motion_queue.get_stats()
        return None
    
    def get_watchdog_stats(self):
        """
        Get watchdog statistics.
        
        Returns:
            dict: Watchdog stats or None if not enabled
        """
        if self.watchdog:
            return self.watchdog.get_stats()
        return None
    
    def emergency_stop(self):
        """
        Emergency stop - clear queue and stop all motion immediately.
        """
        print("🚨 EMERGENCY STOP TRIGGERED")
        if self.motion_queue:
            self.motion_queue.emergency_stop()
        else:
            self.send_command("$STOP$", priority=True)
    
    def __del__(self):
        """
        Cleanup on object destruction.
        """
        self.disconnect()


# Global communicator instance (singleton pattern)
_global_esp32 = None


def get_esp32_communicator():
    """
    Get global ESP32 communicator instance.
    
    Returns:
        ESP32Communicator: Global instance
    """
    global _global_esp32
    if _global_esp32 is None:
        _global_esp32 = ESP32Communicator()
    return _global_esp32


def send_command_to_esp32(command_string, priority=False):
    """
    Convenience function to send command using global communicator.
    
    Args:
        command_string: Command to send
        priority: Emergency priority flag
    
    Returns:
        bool: True if sent/queued successfully
    """
    esp32 = get_esp32_communicator()
    return esp32.send_command(command_string, priority=priority)


# Testing
if __name__ == "__main__":
    print("ESP32 Communicator Test")
    print("=" * 50)
    
    # List ports
    esp32 = ESP32Communicator()
    ports = esp32.list_available_ports()
    print(f"Available ports: {ports}")
    
    # Test connection (will fail if no ESP32 connected)
    if ports:
        print(f"\nTesting connection to {ports[0]}...")
        if esp32.connect(ports[0]):
            print("✅ Connected!")
            
            # Test command
            test_cmd = "$MOVE\nJ1:90\nJ2:120\nSPD:30\nTIME:100\n$"
            print(f"\nSending test command:")
            print(test_cmd)
            esp32.send_command(test_cmd)
            
            # Wait a bit
            time.sleep(2)
            
            # Disconnect
            esp32.disconnect()
        else:
            print("❌ Connection failed")
    else:
        print("⚠ No ports available for testing")
