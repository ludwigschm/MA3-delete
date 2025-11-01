from tabletop.sync.neon_manager import EyeTrackerManager, NeonDevice
import time


mgr = EyeTrackerManager([
    NeonDevice(id="NEON_A", host="192.168.137.121", port=8080, label="VP1"),
    NeonDevice(id="NEON_B", host="192.168.137.90", port=8080, label="VP2"),
])

mgr.start_all("probe_session")
time.sleep(3)
mgr.annotate("TEST_EVENT", {"note": "hello from probe"})
time.sleep(2)
mgr.stop_all()
time.sleep(1)
print("Probe done.")
