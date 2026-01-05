"""
Motion Queue - Buffered Command Execution

Ensures smooth, safe, and deterministic robot motion by:
1. Buffering commands in a queue
2. Sending one command at a time
3. Waiting for DONE:MOVE before sending next
4. Preventing command flooding to ESP32

This is how industrial robots maintain smooth motion during playback.

USAGE:
    queue = MotionQueue(serial_link)
    queue.add(command)  # Buffer command
    queue.update()      # Call in main loop to process queue
    
RULES:
1. Only one command in flight at a time
2. Must receive DONE:MOVE before sending next
3. Emergency stop clears entire queue
4. Queue has maximum size to prevent memory overflow
"""

from collections import deque
import time
import threading


class MotionQueue:
    """
    Buffered motion command queue with ACK synchronization.
    
    Maintains a FIFO queue of commands and sends them one at a time,
    waiting for DONE:MOVE acknowledgment before proceeding.
    """
    
    def __init__(self, serial_link, max_size=100):
        """
        Initialize motion queue.
        
        Args:
            serial_link: ESP32Serial instance for sending commands
            max_size: Maximum queue size (prevents memory overflow)
        """
        self.serial = serial_link
        self.queue = deque()
        self.max_size = max_size
        
        # State tracking
        self.busy = False              # True when command in flight
        self.current_command = None    # Command currently executing
        self.command_start_time = 0    # When current command was sent
        
        # Statistics
        self.commands_sent = 0
        self.commands_completed = 0
        self.commands_dropped = 0
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Connect to serial link callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """
        Connect to serial link ACK callbacks.
        """
        # When DONE:MOVE received, mark not busy
        self.serial.on_done_move = self.on_done
        
        # When fault received, stop queue
        original_fault_handler = self.serial.on_fault
        
        def fault_handler(fault_type):
            print(f"⚠ Motion Queue: Fault detected ({fault_type}) - clearing queue")
            self.clear()
            if original_fault_handler:
                original_fault_handler(fault_type)
        
        self.serial.on_fault = fault_handler
    
    def add(self, command):
        """
        Add command to queue.
        
        Args:
            command: Command string to queue
        
        Returns:
            bool: True if queued, False if queue full
        """
        with self.lock:
            if len(self.queue) >= self.max_size:
                print(f"⚠ Motion Queue: Full ({self.max_size}) - dropping command")
                self.commands_dropped += 1
                return False
            
            self.queue.append(command)
            return True
    
    def update(self):
        """
        Process queue - send next command if not busy.
        
        Call this regularly from your main loop or timer.
        Typically called at 10-100 Hz.
        """
        with self.lock:
            # If busy, wait for DONE:MOVE
            if self.busy:
                return
            
            # If queue empty, nothing to do
            if not self.queue:
                return
            
            # Get next command
            command = self.queue.popleft()
            
            # Send command
            if self.serial.send(command):
                self.busy = True
                self.current_command = command
                self.command_start_time = time.time()
                self.commands_sent += 1
            else:
                # Send failed - requeue at front
                print("⚠ Motion Queue: Send failed - requeueing")
                self.queue.appendleft(command)
    
    def on_done(self):
        """
        Called when DONE:MOVE received from ESP32.
        Marks queue as not busy so next command can be sent.
        """
        with self.lock:
            if not self.busy:
                print("⚠ Motion Queue: Received DONE:MOVE but not busy")
                return
            
            execution_time = time.time() - self.command_start_time
            print(f"✅ Motion Queue: Command completed ({execution_time:.2f}s)")
            
            self.busy = False
            self.current_command = None
            self.commands_completed += 1
    
    def clear(self):
        """
        Clear all queued commands.
        
        Use for emergency stop or when switching modes.
        Does NOT stop current command - use emergency_stop() for that.
        """
        with self.lock:
            dropped = len(self.queue)
            self.queue.clear()
            if dropped > 0:
                print(f"⚠ Motion Queue: Cleared {dropped} commands")
    
    def emergency_stop(self):
        """
        Emergency stop - clear queue and send STOP command.
        
        This bypasses the queue and sends stop immediately.
        """
        with self.lock:
            # Clear queue
            self.clear()
            
            # Send emergency stop (bypass queue)
            stop_cmd = "$STOP$"
            print(f"🚨 Motion Queue: EMERGENCY STOP")
            self.serial.send(stop_cmd)
            
            # Reset state
            self.busy = False
            self.current_command = None
    
    def is_busy(self):
        """
        Check if command is currently executing.
        
        Returns:
            bool: True if waiting for DONE:MOVE
        """
        return self.busy
    
    def get_queue_size(self):
        """
        Get number of commands in queue.
        
        Returns:
            int: Number of queued commands
        """
        return len(self.queue)
    
    def get_stats(self):
        """
        Get queue statistics.
        
        Returns:
            dict: Statistics including sent, completed, dropped counts
        """
        return {
            'queued': len(self.queue),
            'busy': self.busy,
            'sent': self.commands_sent,
            'completed': self.commands_completed,
            'dropped': self.commands_dropped,
            'current': self.current_command
        }
    
    def wait_until_empty(self, timeout=30.0):
        """
        Block until queue is empty and not busy.
        
        Useful for synchronous operations like Teach playback.
        
        Args:
            timeout: Maximum wait time in seconds
        
        Returns:
            bool: True if empty, False if timeout
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                if not self.busy and len(self.queue) == 0:
                    return True
            
            # Check timeout
            if time.time() - start_time > timeout:
                print(f"⚠ Motion Queue: wait_until_empty() timeout")
                return False
            
            time.sleep(0.1)
    
    def __repr__(self):
        """String representation for debugging."""
        return f"MotionQueue(queued={len(self.queue)}, busy={self.busy})"


# Testing
if __name__ == "__main__":
    print("Motion Queue Test")
    print("=" * 50)
    
    # Mock serial link for testing
    class MockSerial:
        def __init__(self):
            self.on_done_move = None
            self.on_fault = None
        
        def send(self, cmd):
            print(f"  📤 Sending: {cmd[:50]}")
            return True
        
        def simulate_done(self):
            """Simulate ESP32 sending DONE:MOVE"""
            if self.on_done_move:
                self.on_done_move()
    
    # Create queue with mock serial
    serial = MockSerial()
    queue = MotionQueue(serial, max_size=10)
    
    # Test 1: Add commands
    print("\n[TEST 1] Adding commands to queue:")
    for i in range(5):
        cmd = f"$MOVE\nJ1:{i*10}\n$"
        queue.add(cmd)
        print(f"  Added command {i+1}")
    
    print(f"  Queue size: {queue.get_queue_size()}")
    
    # Test 2: Process commands
    print("\n[TEST 2] Processing commands:")
    for i in range(5):
        print(f"\n  Cycle {i+1}:")
        queue.update()  # Send command
        time.sleep(0.5)
        serial.simulate_done()  # Simulate completion
        time.sleep(0.2)
    
    # Test 3: Statistics
    print("\n[TEST 3] Statistics:")
    stats = queue.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test 4: Emergency stop
    print("\n[TEST 4] Emergency stop:")
    queue.add("$MOVE\nJ1:90\n$")
    queue.add("$MOVE\nJ1:180\n$")
    print(f"  Queue size before stop: {queue.get_queue_size()}")
    queue.emergency_stop()
    print(f"  Queue size after stop: {queue.get_queue_size()}")
    
    print("\n✅ All tests completed!")
