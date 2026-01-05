"""
Watchdog - Communication Health Monitor

Detects communication failures and prevents runaway robot by:
1. Monitoring time since last ESP32 response
2. Tracking heartbeat messages (optional)
3. Raising alerts when timeout exceeded
4. Providing fault recovery mechanisms

This is a critical safety layer for any robot control system.

USAGE:
    watchdog = Watchdog(timeout=2.0)
    
    # In your serial callback:
    watchdog.kick()  # Reset timer
    
    # In your main loop:
    try:
        watchdog.check()  # Raises exception on timeout
    except WatchdogTimeout:
        # Handle communication loss
        emergency_stop()

RULES:
1. Watchdog must be kicked regularly (on every ACK/response)
2. Timeout should be 2-5 seconds for typical systems
3. On timeout, immediately stop all motion
4. Heartbeat (HB) is optional but recommended for production
"""

import time
import threading


class WatchdogTimeout(Exception):
    """Exception raised when watchdog timeout occurs."""
    pass


class Watchdog:
    """
    Communication health monitor with timeout detection.
    
    Tracks time since last response and triggers fault condition
    if ESP32 stops responding.
    """
    
    def __init__(self, timeout=2.0, enable_heartbeat=False):
        """
        Initialize watchdog.
        
        Args:
            timeout: Maximum time (seconds) without response before fault
            enable_heartbeat: If True, requires periodic HB messages
        """
        self.timeout = timeout
        self.enable_heartbeat = enable_heartbeat
        
        # State tracking
        self.last_response = time.time()
        self.last_heartbeat = time.time()
        self.enabled = True
        self.fault_detected = False
        
        # Statistics
        self.kick_count = 0
        self.timeout_count = 0
        self.heartbeat_count = 0
        
        # Callbacks
        self.on_timeout = None         # Called when timeout detected
        self.on_recovery = None        # Called when communication restored
        
        # Thread safety
        self.lock = threading.Lock()
    
    def kick(self):
        """
        Reset watchdog timer - call on every ESP32 response.
        
        This tells the watchdog that communication is healthy.
        Call this from your serial message callback.
        """
        with self.lock:
            self.last_response = time.time()
            self.kick_count += 1
            
            # If recovering from fault, call recovery callback
            if self.fault_detected:
                self.fault_detected = False
                print("✅ Watchdog: Communication restored")
                if self.on_recovery:
                    try:
                        self.on_recovery()
                    except Exception as e:
                        print(f"⚠ Watchdog: Recovery callback error - {e}")
    
    def heartbeat(self):
        """
        Record heartbeat message from ESP32.
        
        If heartbeat monitoring is enabled, this must be called
        periodically (typically every 500ms from ESP32).
        """
        with self.lock:
            self.last_heartbeat = time.time()
            self.heartbeat_count += 1
            
            # Heartbeat also counts as general response
            self.kick()
    
    def check(self):
        """
        Check if watchdog timeout has occurred.
        
        Call this regularly from your main loop (10-100 Hz).
        Raises WatchdogTimeout exception if timeout detected.
        
        Raises:
            WatchdogTimeout: If timeout period exceeded without response
        """
        if not self.enabled:
            return
        
        with self.lock:
            current_time = time.time()
            time_since_response = current_time - self.last_response
            
            # Check general timeout
            if time_since_response > self.timeout:
                if not self.fault_detected:
                    self.fault_detected = True
                    self.timeout_count += 1
                    
                    print(f"🚨 Watchdog: TIMEOUT - No response for {time_since_response:.2f}s")
                    
                    # Call timeout callback
                    if self.on_timeout:
                        try:
                            self.on_timeout(time_since_response)
                        except Exception as e:
                            print(f"⚠ Watchdog: Timeout callback error - {e}")
                    
                    # Raise exception
                    raise WatchdogTimeout(
                        f"ESP32 not responding - {time_since_response:.1f}s since last response"
                    )
            
            # Check heartbeat timeout (if enabled)
            if self.enable_heartbeat:
                time_since_heartbeat = current_time - self.last_heartbeat
                heartbeat_timeout = self.timeout * 1.5  # More lenient than general timeout
                
                if time_since_heartbeat > heartbeat_timeout:
                    if not self.fault_detected:
                        self.fault_detected = True
                        self.timeout_count += 1
                        
                        print(f"🚨 Watchdog: HEARTBEAT LOST - {time_since_heartbeat:.2f}s since HB")
                        
                        if self.on_timeout:
                            try:
                                self.on_timeout(time_since_heartbeat)
                            except Exception as e:
                                print(f"⚠ Watchdog: Timeout callback error - {e}")
                        
                        raise WatchdogTimeout(
                            f"ESP32 heartbeat lost - {time_since_heartbeat:.1f}s since HB"
                        )
    
    def is_healthy(self):
        """
        Check if communication is currently healthy.
        
        Returns:
            bool: True if within timeout period
        """
        with self.lock:
            time_since_response = time.time() - self.last_response
            return time_since_response < self.timeout
    
    def enable(self):
        """Enable watchdog monitoring."""
        with self.lock:
            self.enabled = True
            self.last_response = time.time()  # Reset timer
            print("✅ Watchdog: Enabled")
    
    def disable(self):
        """Disable watchdog monitoring."""
        with self.lock:
            self.enabled = False
            print("⏸ Watchdog: Disabled")
    
    def reset(self):
        """
        Reset watchdog state.
        
        Clears fault condition and resets all timers.
        Use when reconnecting or recovering from fault.
        """
        with self.lock:
            self.last_response = time.time()
            self.last_heartbeat = time.time()
            self.fault_detected = False
            print("🔄 Watchdog: Reset")
    
    def get_stats(self):
        """
        Get watchdog statistics.
        
        Returns:
            dict: Statistics including kick count, timeout count, etc.
        """
        with self.lock:
            current_time = time.time()
            return {
                'enabled': self.enabled,
                'healthy': self.is_healthy(),
                'time_since_response': current_time - self.last_response,
                'time_since_heartbeat': current_time - self.last_heartbeat,
                'kick_count': self.kick_count,
                'timeout_count': self.timeout_count,
                'heartbeat_count': self.heartbeat_count,
                'fault_detected': self.fault_detected
            }
    
    def set_timeout(self, timeout):
        """
        Change timeout period.
        
        Args:
            timeout: New timeout in seconds
        """
        with self.lock:
            self.timeout = timeout
            print(f"⚙ Watchdog: Timeout set to {timeout}s")
    
    def __repr__(self):
        """String representation for debugging."""
        healthy = "✅" if self.is_healthy() else "❌"
        return f"Watchdog(timeout={self.timeout}s, healthy={healthy})"


# Testing
if __name__ == "__main__":
    print("Watchdog Test")
    print("=" * 50)
    
    # Test 1: Normal operation
    print("\n[TEST 1] Normal operation:")
    watchdog = Watchdog(timeout=1.0)
    
    for i in range(5):
        print(f"  Cycle {i+1}:")
        time.sleep(0.3)
        watchdog.kick()  # Simulate response
        try:
            watchdog.check()
            print(f"    ✅ Healthy (kicks: {watchdog.kick_count})")
        except WatchdogTimeout as e:
            print(f"    ❌ Timeout: {e}")
    
    # Test 2: Timeout detection
    print("\n[TEST 2] Timeout detection:")
    watchdog.reset()
    
    try:
        print("  Waiting 1.5s without kicking...")
        time.sleep(1.5)
        watchdog.check()
        print("  ❌ Should have timed out!")
    except WatchdogTimeout as e:
        print(f"  ✅ Timeout detected: {e}")
    
    # Test 3: Recovery
    print("\n[TEST 3] Recovery:")
    
    def on_recovery():
        print("  ✅ Recovery callback called!")
    
    watchdog.on_recovery = on_recovery
    watchdog.kick()  # Trigger recovery
    
    try:
        watchdog.check()
        print("  ✅ Healthy after recovery")
    except WatchdogTimeout:
        print("  ❌ Still in fault state")
    
    # Test 4: Heartbeat monitoring
    print("\n[TEST 4] Heartbeat monitoring:")
    watchdog_hb = Watchdog(timeout=1.0, enable_heartbeat=True)
    
    for i in range(3):
        print(f"  Heartbeat {i+1}")
        watchdog_hb.heartbeat()
        time.sleep(0.4)
        try:
            watchdog_hb.check()
            print(f"    ✅ Healthy (HB count: {watchdog_hb.heartbeat_count})")
        except WatchdogTimeout as e:
            print(f"    ❌ {e}")
    
    # Test 5: Statistics
    print("\n[TEST 5] Statistics:")
    stats = watchdog.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test 6: Enable/Disable
    print("\n[TEST 6] Enable/Disable:")
    watchdog.disable()
    time.sleep(2.0)  # Wait longer than timeout
    try:
        watchdog.check()
        print("  ✅ No timeout when disabled")
    except WatchdogTimeout:
        print("  ❌ Should not timeout when disabled")
    
    watchdog.enable()
    watchdog.kick()  # Reset timer
    
    print("\n✅ All tests completed!")
