from prometheus_client import Counter, Gauge, start_http_server
import logging

from .message import MessageLevel

LOGGER = logging.getLogger(__name__)

# Metrics
# General metrics
observer_info = Gauge("observer_info", "Observer information", ["identity_address", "chain_id"])
reward_epoch_info = Gauge("reward_epoch_info", "Current reward epoch information", ["reward_epoch_id"])
voting_epoch_info = Gauge("voting_epoch_info", "Current voting epoch information", ["voting_epoch_id"])

# Protocol specific metrics
ftso_submit1_total = Counter("ftso_submit1_total", "Total FTSO submit1 transactions", ["identity_address"])
ftso_submit2_total = Counter("ftso_submit2_total", "Total FTSO submit2 transactions", ["identity_address"])
ftso_submit_signatures_total = Counter("ftso_submit_signatures_total", "Total FTSO submit signatures transactions", ["identity_address"])
ftso_reveal_offence_total = Counter("ftso_reveal_offence_total", "Total FTSO reveal offences", ["identity_address"])
ftso_none_values_total = Counter("ftso_none_values_total", "Total FTSO None values submitted", ["identity_address", "index"])
ftso_signature_mismatch_total = Counter("ftso_signature_mismatch_total", "Total FTSO signature mismatches", ["identity_address"])

fdc_submit1_total = Counter("fdc_submit1_total", "Total FDC submit1 transactions", ["identity_address"])
fdc_submit2_total = Counter("fdc_submit2_total", "Total FDC submit2 transactions", ["identity_address"])
fdc_submit_signatures_total = Counter("fdc_submit_signatures_total", "Total FDC submit signatures transactions", ["identity_address"])
fdc_reveal_offence_total = Counter("fdc_reveal_offence_total", "Total FDC reveal offences", ["identity_address"])
fdc_signature_mismatch_total = Counter("fdc_signature_mismatch_total", "Total FDC signature mismatches", ["identity_address"])

# Message level counters
message_total = Counter("message_total", "Total messages by level", ["level", "identity_address"])

# Entity metrics
entity_wnat_weight = Gauge("entity_wnat_weight", "Entity WNAT weight", ["identity_address"])
entity_wnat_capped_weight = Gauge("entity_wnat_capped_weight", "Entity WNAT capped weight", ["identity_address"])
entity_registration_weight = Gauge("entity_registration_weight", "Entity registration weight", ["identity_address"])
entity_normalized_weight = Gauge("entity_normalized_weight", "Entity normalized weight", ["identity_address"])

def init_metrics(port=8000):
    """Initialize and start the Prometheus metrics server"""
    try:
        start_http_server(port)
        LOGGER.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        LOGGER.error(f"Failed to start Prometheus metrics server: {e}")


def update_entity_metrics(entity):
    """Update metrics for an entity"""
    entity_wnat_weight.labels(identity_address=entity.identity_address).set(entity.w_nat_weight)
    entity_wnat_capped_weight.labels(identity_address=entity.identity_address).set(entity.w_nat_capped_weight)
    entity_registration_weight.labels(identity_address=entity.identity_address).set(entity.registration_weight)
    entity_normalized_weight.labels(identity_address=entity.identity_address).set(entity.normalized_weight)


def record_message(message, identity_address):
    """Record a message in the metrics"""
    message_total.labels(level=message.level.name, identity_address=identity_address).inc()


def record_ftso_submit1(identity_address):
    """Record a FTSO submit1 transaction"""
    ftso_submit1_total.labels(identity_address=identity_address).inc()


def record_ftso_submit2(identity_address):
    """Record a FTSO submit2 transaction"""
    ftso_submit2_total.labels(identity_address=identity_address).inc()


def record_ftso_submit_signatures(identity_address):
    """Record a FTSO submit signatures transaction"""
    ftso_submit_signatures_total.labels(identity_address=identity_address).inc()


def record_ftso_reveal_offence(identity_address):
    """Record a FTSO reveal offence"""
    ftso_reveal_offence_total.labels(identity_address=identity_address).inc()


def record_ftso_none_value(identity_address, index):
    """Record a FTSO None value"""
    ftso_none_values_total.labels(identity_address=identity_address, index=index).inc()


def record_ftso_signature_mismatch(identity_address):
    """Record a FTSO signature mismatch"""
    ftso_signature_mismatch_total.labels(identity_address=identity_address).inc()


def record_fdc_submit1(identity_address):
    """Record a FDC submit1 transaction"""
    fdc_submit1_total.labels(identity_address=identity_address).inc()


def record_fdc_submit2(identity_address):
    """Record a FDC submit2 transaction"""
    fdc_submit2_total.labels(identity_address=identity_address).inc()


def record_fdc_submit_signatures(identity_address):
    """Record a FDC submit signatures transaction"""
    fdc_submit_signatures_total.labels(identity_address=identity_address).inc()


def record_fdc_reveal_offence(identity_address):
    """Record a FDC reveal offence"""
    fdc_reveal_offence_total.labels(identity_address=identity_address).inc()


def record_fdc_signature_mismatch(identity_address):
    """Record a FDC signature mismatch"""
    fdc_signature_mismatch_total.labels(identity_address=identity_address).inc()