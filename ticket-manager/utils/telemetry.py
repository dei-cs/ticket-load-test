from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

# Tracing
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# ---- Setup ----

def setup_telemetry(service_name: str = "ticket-manager"):
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0",
    })

    # ---- Tracing ----
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    trace_exporter = OTLPSpanExporter(
        endpoint="localhost:4317",
        insecure=True,
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(trace_exporter)
    )

    # ---- Metrics ----
    metric_exporter = OTLPMetricExporter(
        endpoint="localhost:4317",
        insecure=True,
    )

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=5000,  # every 5s
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )

    metrics.set_meter_provider(meter_provider)


# ---- Shared instruments ----

tracer = trace.get_tracer("ticket-manager")
meter = metrics.get_meter("ticket-manager")

# Counters
reservation_attempts = meter.create_counter(
    "ticket_reservation_attempts",
    description="Number of ticket reservation attempts"
)

reservation_results = meter.create_counter(
    "ticket_reservation_results",
    description="Number of reservation results"
)

# Histogram
reservation_duration = meter.create_histogram(
    "ticket_reservation_duration_seconds",
    description="Duration of reservation operation",
    unit="s"
)