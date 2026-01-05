"""
Serial Link Layer with ACK/SYNC Protocol

Handles low-level serial communication with ESP32 and ACK message parsing.
This is the foundation layer for deterministic robot control.

ACK PROTOCOL:
- ESP32 → PC: ACK:MOVE (command accepted)
- ESP32 → PC: DONE:MOVE (motion complete)
- ESP32 → PC: ACK:STOP (stop acknowledged)
- ESP32 → PC: FAULT:LIMIT (limit switch hit)
- ESP32 → PC: FAULT:EMERGENCY (emergency stop)
- ESP32 → PC: HB (heartbeat - optional)

RULES:
1. All messages are line-based (terminated with \n)
2. PC never sends next motion until DONE:MOVE received
3. Emergency stop bypasses queue
4. Callbacks notify higher layers of state changes
"""

import serial
import serial.tools.list_ports
import threading
import time


class ESP32Serial:
    """
    Low-level serial communication with ACK listener.
    
    This class manages the physical serial connection and parses
    ESP32 acknowledgment messages in a separate thread.
    """
    
    def __init__(self, port=None, baudrate=115200):
        """
        Initialize serial link.
        
        Args:
            port: Serial port (e.g., 'COM3'). If None, auto-detect
            baudrate: Communication speed (default: 115200)
        """
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.connected = False
        
        # ACK state tracking
        self.last_ack = None
        self.last_ack_time = 0
        
        # Callbacks for different message types
        self.on_ack_move = None        # Called when ACK:MOVE received
        self.on_done_move = None       # Called when DONE:MOVE received
        self.on_ack_stop = None        # Called when ACK:STOP received
        self.on_fault = None           # Called when FAULT:* received
        self.on_heartbeat = None       # Called when HB received
        self.on_message = None         # Called for any message
        
        # Listener thread
        self.listen_thread = None
    
    def list_ports(self):
        """
        List all available serial ports.
        
        Returns:
            list: List of available port names
        """
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
    
    def connect(self, port=None):
        """
        Connect to ESP32.
        
        Args:
            port: Serial port. If None, uses self.port or auto-detects
        
        Returns:
            bool: True if connected successfully
        """
        if self.connected:
            print("⚠ Already connected")
            return True
        
        if port:
            self.port = port
        
        # Auto-detect if no port specified
        if not self.port:
            ports = self.list_ports()
            if not ports:
                print("❌ No serial ports found")
                return False
            self.port = ports[0]
            print(f"🔍 Auto-selected port: {self.port}")
        
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1,
                write_timeout=1
            )
            
            # Wait for ESP32 to initialize
            time.sleep(2)
            
            # Flush buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            self.connected = True
            
            # Start listener thread
            self.running = True
            self.listen_thread = threading.Thread(target=self._listen, daemon=True)
            self.listen_thread.start()
            
            print(f"✅ Serial Link: Connected to {self.port}")
            return True
            
        except serial.SerialException as e:
            print(f"❌ Serial Link: Connection failed - {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """
        Disconnect from ESP32.
        """
        if not self.connected:
            return
        
        # Stop listener thread
        self.running = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=2)
        
        # Close serial connection
        if self.ser and self.ser.is_open:
            self.ser.close()
        
        self.connected = False
        print("🔌 Serial Link: Disconnected")
    
    def send(self, command):
        """
        Send command to ESP32.
        
        Args:
            command: Command string to send
        
        Returns:
            bool: True if sent successfully
        """
        if not self.connected or not self.ser:
            print(f"⚠ Serial Link: Not connected - cannot send: {command[:50]}")
            return False
        
        try:
            # Ensure command ends with newline
            if not command.endswith('\n'):
                command += '\n'
            
            self.ser.write(command.encode('utf-8'))
            self.ser.flush()
            return True
            
        except Exception as e:
            print(f"❌ Serial Link: Send failed - {e}")
            return False
    
    def _listen(self):
        """
        Background thread that listens for ESP32 messages.
        Parses and dispatches ACK messages to callbacks.
        """
        buffer = ""
        
        while self.running:
            try:
                if self.ser and self.ser.in_waiting:
                    # Read available data
                    data = self.ser.read(self.ser.in_waiting)
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        msg = line.strip()
                        
                        if msg:
                            self._handle_message(msg)
                
                time.sleep(0.01)  # 10ms polling interval
                
            except Exception as e:
                print(f"❌ Serial Link: Listen error - {e}")
                time.sleep(0.1)
    
    def _handle_message(self, msg):
        """
        Parse and dispatch received message.
        
        Args:
            msg: Message string from ESP32
        """
        self.last_ack = msg
        self.last_ack_time = time.time()
        
        # Print for debugging
        print(f"📥 ESP32: {msg}")
        
        # Call generic message callback
        if self.on_message:
            try:
                self.on_message(msg)
            except Exception as e:
                print(f"⚠ Message callback error: {e}")
        
        # Dispatch specific message types
        if msg == "ACK:MOVE":
            if self.on_ack_move:
                try:
                    self.on_ack_move()
                except Exception as e:
                    print(f"⚠ ACK:MOVE callback error: {e}")
        
        elif msg == "DONE:MOVE":
            if self.on_done_move:
                try:
                    self.on_done_move()
                except Exception as e:
                    print(f"⚠ DONE:MOVE callback error: {e}")
        
        elif msg == "ACK:STOP":
            if self.on_ack_stop:
                try:
                    self.on_ack_stop()
                except Exception as e:
                    print(f"⚠ ACK:STOP callback error: {e}")
        
        elif msg.startswith("FAULT:"):
            fault_type = msg.split(":", 1)[1] if ":" in msg else "UNKNOWN"
            if self.on_fault:
                try:
                    self.on_fault(fault_type)
                except Exception as e:
                    print(f"⚠ FAULT callback error: {e}")
        
        elif msg == "HB":
            if self.on_heartbeat:
                try:
                    self.on_heartbeat()
                except Exception as e:
                    print(f"⚠ Heartbeat callback error: {e}")
    
    def is_connected(self):
        """
        Check if serial link is active.
        
        Returns:
            bool: True if connected
        """
        return self.connected
    
    def get_last_ack(self):
        """
        Get the last received ACK message.
        
        Returns:
            tuple: (message, timestamp) or (None, 0)
        """
        return (self.last_ack, self.last_ack_time)
    
    def __del__(self):
        """Cleanup on destruction."""
        self.disconnect()


# Testing
if __name__ == "__main__":
    print("Serial Link Test")
    print("=" * 50)
    
    # Create serial link
    link = ESP32Serial()
    
    # List ports
    ports = link.list_ports()
    print(f"Available ports: {ports}")
    
    if not ports:
        print("⚠ No ports available for testing")
        exit(1)
    
    # Set up callbacks
    def on_move_ack():
        print("✅ Move acknowledged!")
    
    def on_move_done():
        print("✅ Move completed!")
    
    def on_fault(fault_type):
        print(f"⚠ FAULT: {fault_type}")
    
    link.on_ack_move = on_move_ack
    link.on_done_move = on_move_done
    link.on_fault = on_fault
    
    # Connect
    if link.connect(ports[0]):
        print("\nConnected! Waiting for messages...")
        print("(Send commands from ESP32 to test)")
        
        try:
            # Keep alive for testing
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nTest stopped by user")
        finally:
            link.disconnect()
    else:
        print("❌ Connection failed")
