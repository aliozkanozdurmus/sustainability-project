from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Iterator, Mapping

from fastapi import FastAPI

from app.core.settings import settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelemetryRuntime:
    enabled: bool
    tracer_provider: Any | None = None
    meter_provider: Any | None = None
    logger_provider: Any | None = None
    instrumentor: Any | None = None


def _parse_otlp_headers(raw_headers: str | None) -> dict[str, str]:
    if not raw_headers:
        return {}
    parsed: dict[str, str] = {}
    for part in raw_headers.split(","):
        key, separator, value = part.partition("=")
        if separator and key.strip() and value.strip():
            parsed[key.strip()] = value.strip()
    return parsed


def _import_opentelemetry() -> dict[str, Any] | None:
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        exported: dict[str, Any] = {
            "metrics": metrics,
            "trace": trace,
            "FastAPIInstrumentor": FastAPIInstrumentor,
            "MeterProvider": MeterProvider,
            "ConsoleMetricExporter": ConsoleMetricExporter,
            "PeriodicExportingMetricReader": PeriodicExportingMetricReader,
            "Resource": Resource,
            "TracerProvider": TracerProvider,
            "BatchSpanProcessor": BatchSpanProcessor,
            "ConsoleSpanExporter": ConsoleSpanExporter,
        }

        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exported["OTLPMetricExporter"] = OTLPMetricExporter
            exported["OTLPSpanExporter"] = OTLPSpanExporter
        except ImportError:
            exported["OTLPMetricExporter"] = None
            exported["OTLPSpanExporter"] = None

        try:
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
            from opentelemetry._logs import set_logger_provider

            exported["LoggerProvider"] = LoggerProvider
            exported["LoggingHandler"] = LoggingHandler
            exported["BatchLogRecordProcessor"] = BatchLogRecordProcessor
            exported["ConsoleLogExporter"] = ConsoleLogExporter
            exported["set_logger_provider"] = set_logger_provider
        except ImportError:
            exported["LoggerProvider"] = None
            exported["LoggingHandler"] = None
            exported["BatchLogRecordProcessor"] = None
            exported["ConsoleLogExporter"] = None
            exported["set_logger_provider"] = None

        try:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

            exported["OTLPLogExporter"] = OTLPLogExporter
        except ImportError:
            exported["OTLPLogExporter"] = None

        try:
            from opentelemetry.trace import Status, StatusCode

            exported["Status"] = Status
            exported["StatusCode"] = StatusCode
        except ImportError:
            exported["Status"] = None
            exported["StatusCode"] = None

        return exported
    except ImportError:
        return None


def _build_resource(otel: Mapping[str, Any]) -> Any:
    resource_cls = otel["Resource"]
    return resource_cls.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.api_version,
            "deployment.environment": settings.app_env,
        }
    )


def setup_telemetry(app: FastAPI) -> TelemetryRuntime:
    if not settings.otel_enabled:
        return TelemetryRuntime(enabled=False)

    otel = _import_opentelemetry()
    if otel is None:
        logger.warning("OpenTelemetry packages are unavailable; telemetry bootstrap is disabled.")
        return TelemetryRuntime(enabled=False)

    headers = _parse_otlp_headers(settings.otel_exporter_otlp_headers)
    resource = _build_resource(otel)

    tracer_provider = otel["TracerProvider"](resource=resource)
    meter_provider = None
    logger_provider = None

    if settings.otel_exporter_otlp_endpoint and otel.get("OTLPSpanExporter") is not None:
        tracer_provider.add_span_processor(
            otel["BatchSpanProcessor"](
                otel["OTLPSpanExporter"](
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    headers=headers or None,
                )
            )
        )
    elif settings.otel_console_export:
        tracer_provider.add_span_processor(
            otel["BatchSpanProcessor"](otel["ConsoleSpanExporter"]())
        )

    if settings.otel_exporter_otlp_endpoint and otel.get("OTLPMetricExporter") is not None:
        metric_reader = otel["PeriodicExportingMetricReader"](
            otel["OTLPMetricExporter"](
                endpoint=settings.otel_exporter_otlp_endpoint,
                headers=headers or None,
            )
        )
        meter_provider = otel["MeterProvider"](resource=resource, metric_readers=[metric_reader])
    elif settings.otel_console_export:
        metric_reader = otel["PeriodicExportingMetricReader"](otel["ConsoleMetricExporter"]())
        meter_provider = otel["MeterProvider"](resource=resource, metric_readers=[metric_reader])

    if (
        settings.otel_exporter_otlp_endpoint
        and otel.get("LoggerProvider") is not None
        and otel.get("OTLPLogExporter") is not None
    ):
        logger_provider = otel["LoggerProvider"](resource=resource)
        logger_provider.add_log_record_processor(
            otel["BatchLogRecordProcessor"](
                otel["OTLPLogExporter"](
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    headers=headers or None,
                )
            )
        )
        otel["set_logger_provider"](logger_provider)
    elif settings.otel_console_export and otel.get("LoggerProvider") is not None:
        logger_provider = otel["LoggerProvider"](resource=resource)
        logger_provider.add_log_record_processor(
            otel["BatchLogRecordProcessor"](otel["ConsoleLogExporter"]())
        )
        otel["set_logger_provider"](logger_provider)

    otel["trace"].set_tracer_provider(tracer_provider)
    if meter_provider is not None:
        otel["metrics"].set_meter_provider(meter_provider)

    instrumentor = otel["FastAPIInstrumentor"]()
    instrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    if logger_provider is not None and otel.get("LoggingHandler") is not None:
        logging.getLogger("app").addHandler(
            otel["LoggingHandler"](level=logging.INFO, logger_provider=logger_provider)
        )

    logger.info(
        "Telemetry bootstrapped",
        extra={
            "service_name": settings.otel_service_name,
            "otlp_endpoint": settings.otel_exporter_otlp_endpoint,
            "console_export": settings.otel_console_export,
        },
    )
    return TelemetryRuntime(
        enabled=True,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        instrumentor=instrumentor,
    )


def shutdown_telemetry(runtime: TelemetryRuntime | None) -> None:
    if runtime is None:
        return

    for provider_name in ("logger_provider", "meter_provider", "tracer_provider"):
        provider = getattr(runtime, provider_name, None)
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()


@contextmanager
def observe_operation(
    operation_name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[None]:
    attributes = dict(attributes or {})
    start = perf_counter()
    otel = _import_opentelemetry()
    span_context = nullcontext()
    span = None

    if settings.otel_enabled and otel is not None:
        tracer = otel["trace"].get_tracer(settings.otel_service_name)
        span_context = tracer.start_as_current_span(operation_name)

    with span_context as active_span:
        span = active_span
        if span is not None:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)

        try:
            yield
        except Exception as exc:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            if span is not None:
                span.record_exception(exc)
                status_cls = otel.get("Status") if otel is not None else None
                status_code = otel.get("StatusCode") if otel is not None else None
                if status_cls is not None and status_code is not None:
                    span.set_status(status_cls(status_code.ERROR, str(exc)))
                span.set_attribute("operation.duration_ms", duration_ms)
            logger.exception(
                "Operation failed",
                extra={
                    "operation": operation_name,
                    "duration_ms": duration_ms,
                    "attributes": attributes,
                },
            )
            raise
        else:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            if span is not None:
                span.set_attribute("operation.duration_ms", duration_ms)
            logger.info(
                "Operation completed",
                extra={
                    "operation": operation_name,
                    "duration_ms": duration_ms,
                    "attributes": attributes,
                },
            )
