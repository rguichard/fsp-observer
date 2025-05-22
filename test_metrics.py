#!/usr/bin/env python3
from observer.metrics import init_metrics, observer_info, ftso_submit1_total, message_total, entity_wnat_weight
import time
from prometheus_client import REGISTRY

# Initialize Prometheus metrics server
init_metrics(port=8000)
print("Prometheus metrics server started on port 8000")

# Set some example metrics
observer_info.labels(identity_address="0x1234567890123456789012345678901234567890", chain_id=1).set(1)
ftso_submit1_total.labels(identity_address="0x1234567890123456789012345678901234567890").inc()
message_total.labels(level="INFO", identity_address="0x1234567890123456789012345678901234567890").inc()
entity_wnat_weight.labels(identity_address="0x1234567890123456789012345678901234567890").set(123456)

print("Sample metrics set, metrics server is running...")
print("Press Ctrl+C to exit")

# Keep the server running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting...")