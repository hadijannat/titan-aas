"""Dashboard connectors endpoints - OPC-UA/Modbus/MQTT control.

Provides:
- Connector status overview
- Manual connect/disconnect operations
- Test read/write operations
- Mapping inspection
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from titan.config import settings
from titan.security.deps import require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/connectors", tags=["Dashboard - Connectors"])


class ConnectorState(str, Enum):
    """Connector connection state."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    FAILED = "failed"
    DISABLED = "disabled"


class ConnectorStatus(BaseModel):
    """Status of a single connector."""

    name: str
    enabled: bool
    state: ConnectorState
    endpoint: str | None = None
    error: str | None = None
    metrics: dict[str, Any] | None = None


class AllConnectorsStatus(BaseModel):
    """Status of all connectors."""

    timestamp: datetime
    connectors: list[ConnectorStatus]


class ConnectionResult(BaseModel):
    """Result of a connect/disconnect operation."""

    connector: str
    success: bool
    state: ConnectorState
    message: str | None = None
    timestamp: datetime


class OpcUaReadRequest(BaseModel):
    """Request to read an OPC-UA node."""

    node_id: str


class OpcUaReadResult(BaseModel):
    """Result of an OPC-UA node read."""

    node_id: str
    value: Any
    data_type: str | None = None
    timestamp: datetime
    status: str


class OpcUaWriteRequest(BaseModel):
    """Request to write an OPC-UA node."""

    node_id: str
    value: Any


class ModbusReadRequest(BaseModel):
    """Request to read Modbus registers."""

    address: int
    count: int = 1
    register_type: str = "holding_register"


class ModbusReadResult(BaseModel):
    """Result of a Modbus register read."""

    address: int
    values: list[int]
    register_type: str
    timestamp: datetime


class ModbusWriteRequest(BaseModel):
    """Request to write a Modbus register."""

    address: int
    value: int
    register_type: str = "holding_register"


@router.get(
    "/status",
    response_model=AllConnectorsStatus,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_all_connectors_status() -> AllConnectorsStatus:
    """Get status of all connectors.

    Returns connection state for OPC-UA, Modbus, and MQTT.
    """
    connectors: list[ConnectorStatus] = []

    # OPC-UA status
    if settings.opcua_enabled:
        try:
            from titan.connectors.opcua.connection import get_opcua_connection_manager

            manager = await get_opcua_connection_manager()
            if manager:
                if manager.is_connected:
                    state = ConnectorState.CONNECTED
                else:
                    state = ConnectorState.DISCONNECTED
                metrics = manager.get_metrics() if hasattr(manager, "get_metrics") else None
                connectors.append(
                    ConnectorStatus(
                        name="OPC-UA",
                        enabled=True,
                        state=state,
                        endpoint=settings.opcua_endpoint,
                        metrics=metrics.__dict__ if metrics else None,
                    )
                )
            else:
                connectors.append(
                    ConnectorStatus(
                        name="OPC-UA",
                        enabled=True,
                        state=ConnectorState.DISCONNECTED,
                        endpoint=settings.opcua_endpoint,
                    )
                )
        except Exception as e:
            connectors.append(
                ConnectorStatus(
                    name="OPC-UA",
                    enabled=True,
                    state=ConnectorState.FAILED,
                    endpoint=settings.opcua_endpoint,
                    error=str(e),
                )
            )
    else:
        connectors.append(
            ConnectorStatus(
                name="OPC-UA",
                enabled=False,
                state=ConnectorState.DISABLED,
            )
        )

    # Modbus status
    if settings.modbus_enabled:
        try:
            from titan.connectors.modbus.connection import get_modbus_connection_manager

            modbus_manager = await get_modbus_connection_manager()
            if modbus_manager:
                if modbus_manager.is_connected:
                    state = ConnectorState.CONNECTED
                else:
                    state = ConnectorState.DISCONNECTED
                mb_metrics = (
                    modbus_manager.get_metrics() if hasattr(modbus_manager, "get_metrics") else None
                )
                connectors.append(
                    ConnectorStatus(
                        name="Modbus",
                        enabled=True,
                        state=state,
                        endpoint=f"{settings.modbus_host}:{settings.modbus_port}",
                        metrics=mb_metrics.__dict__ if mb_metrics else None,
                    )
                )
            else:
                connectors.append(
                    ConnectorStatus(
                        name="Modbus",
                        enabled=True,
                        state=ConnectorState.DISCONNECTED,
                        endpoint=f"{settings.modbus_host}:{settings.modbus_port}",
                    )
                )
        except Exception as e:
            connectors.append(
                ConnectorStatus(
                    name="Modbus",
                    enabled=True,
                    state=ConnectorState.FAILED,
                    endpoint=f"{settings.modbus_host}:{settings.modbus_port}",
                    error=str(e),
                )
            )
    else:
        connectors.append(
            ConnectorStatus(
                name="Modbus",
                enabled=False,
                state=ConnectorState.DISABLED,
            )
        )

    # MQTT status
    if settings.mqtt_broker:
        try:
            from titan.connectors.mqtt import get_mqtt_publisher

            publisher = await get_mqtt_publisher()
            if publisher:
                if getattr(publisher, "is_connected", False):
                    state = ConnectorState.CONNECTED
                else:
                    state = ConnectorState.DISCONNECTED
                connectors.append(
                    ConnectorStatus(
                        name="MQTT",
                        enabled=True,
                        state=state,
                        endpoint=f"{settings.mqtt_broker}:{settings.mqtt_port}",
                    )
                )
            else:
                connectors.append(
                    ConnectorStatus(
                        name="MQTT",
                        enabled=True,
                        state=ConnectorState.DISCONNECTED,
                        endpoint=f"{settings.mqtt_broker}:{settings.mqtt_port}",
                    )
                )
        except Exception as e:
            connectors.append(
                ConnectorStatus(
                    name="MQTT",
                    enabled=True,
                    state=ConnectorState.FAILED,
                    endpoint=f"{settings.mqtt_broker}:{settings.mqtt_port}",
                    error=str(e),
                )
            )
    else:
        connectors.append(
            ConnectorStatus(
                name="MQTT",
                enabled=False,
                state=ConnectorState.DISABLED,
            )
        )

    return AllConnectorsStatus(
        timestamp=datetime.utcnow(),
        connectors=connectors,
    )


# -------------------------------------------------------------------------
# OPC-UA Control
# -------------------------------------------------------------------------


@router.post(
    "/opcua/connect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def connect_opcua() -> ConnectionResult:
    """Manually connect to the OPC-UA server."""
    if not settings.opcua_enabled:
        raise HTTPException(status_code=400, detail="OPC-UA is not enabled")

    try:
        from titan.connectors.opcua.connection import get_opcua_connection_manager

        manager = await get_opcua_connection_manager()
        if manager is None:
            raise HTTPException(status_code=500, detail="Failed to get OPC-UA manager")

        await manager.connect()

        return ConnectionResult(
            connector="OPC-UA",
            success=True,
            state=ConnectorState.CONNECTED,
            message="Connected successfully",
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        return ConnectionResult(
            connector="OPC-UA",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )


@router.post(
    "/opcua/disconnect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def disconnect_opcua() -> ConnectionResult:
    """Manually disconnect from the OPC-UA server."""
    if not settings.opcua_enabled:
        raise HTTPException(status_code=400, detail="OPC-UA is not enabled")

    try:
        from titan.connectors.opcua.connection import close_opcua

        await close_opcua()

        return ConnectionResult(
            connector="OPC-UA",
            success=True,
            state=ConnectorState.DISCONNECTED,
            message="Disconnected successfully",
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        return ConnectionResult(
            connector="OPC-UA",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )


@router.post(
    "/opcua/read",
    response_model=OpcUaReadResult,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def opcua_read_node(request: OpcUaReadRequest) -> OpcUaReadResult:
    """Read a value from an OPC-UA node."""
    if not settings.opcua_enabled:
        raise HTTPException(status_code=400, detail="OPC-UA is not enabled")

    try:
        from titan.connectors.opcua.connection import get_opcua_connection_manager

        manager = await get_opcua_connection_manager()
        if manager is None or not manager.is_connected:
            raise HTTPException(status_code=503, detail="OPC-UA not connected")

        client = await manager.ensure_connected()
        result = await client.read_node(request.node_id)

        if result is None:
            raise HTTPException(status_code=500, detail="Failed to read node")

        return OpcUaReadResult(
            node_id=request.node_id,
            value=result.value,
            data_type=str(result.data_type) if hasattr(result, "data_type") else None,
            timestamp=datetime.utcnow(),
            status=str(result.status) if hasattr(result, "status") else "OK",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/opcua/write",
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def opcua_write_node(request: OpcUaWriteRequest) -> dict[str, Any]:
    """Write a value to an OPC-UA node."""
    if not settings.opcua_enabled:
        raise HTTPException(status_code=400, detail="OPC-UA is not enabled")

    try:
        from titan.connectors.opcua.connection import get_opcua_connection_manager

        manager = await get_opcua_connection_manager()
        if manager is None or not manager.is_connected:
            raise HTTPException(status_code=503, detail="OPC-UA not connected")

        client = await manager.ensure_connected()
        success = await client.write_node(request.node_id, request.value)

        return {
            "node_id": request.node_id,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Modbus Control
# -------------------------------------------------------------------------


@router.post(
    "/modbus/connect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def connect_modbus() -> ConnectionResult:
    """Manually connect to the Modbus server."""
    if not settings.modbus_enabled:
        raise HTTPException(status_code=400, detail="Modbus is not enabled")

    try:
        from titan.connectors.modbus.connection import get_modbus_connection_manager

        manager = await get_modbus_connection_manager()
        if manager is None:
            raise HTTPException(status_code=500, detail="Failed to get Modbus manager")

        await manager.connect()

        return ConnectionResult(
            connector="Modbus",
            success=True,
            state=ConnectorState.CONNECTED,
            message="Connected successfully",
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        return ConnectionResult(
            connector="Modbus",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )


@router.post(
    "/modbus/disconnect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def disconnect_modbus() -> ConnectionResult:
    """Manually disconnect from the Modbus server."""
    if not settings.modbus_enabled:
        raise HTTPException(status_code=400, detail="Modbus is not enabled")

    try:
        from titan.connectors.modbus.connection import close_modbus

        await close_modbus()

        return ConnectionResult(
            connector="Modbus",
            success=True,
            state=ConnectorState.DISCONNECTED,
            message="Disconnected successfully",
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        return ConnectionResult(
            connector="Modbus",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )


@router.post(
    "/modbus/read",
    response_model=ModbusReadResult,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def modbus_read_registers(request: ModbusReadRequest) -> ModbusReadResult:
    """Read values from Modbus registers."""
    if not settings.modbus_enabled:
        raise HTTPException(status_code=400, detail="Modbus is not enabled")

    try:
        from titan.connectors.modbus.connection import get_modbus_connection_manager

        manager = await get_modbus_connection_manager()
        if manager is None or not manager.is_connected:
            raise HTTPException(status_code=503, detail="Modbus not connected")

        client = await manager.ensure_connected()

        # Read based on register type
        raw_values: list[int] | list[bool] | None = None
        if request.register_type == "holding_register":
            raw_values = await client.read_holding_registers(request.address, request.count)
        elif request.register_type == "input_register":
            raw_values = await client.read_input_registers(request.address, request.count)
        elif request.register_type == "coil":
            raw_values = await client.read_coils(request.address, request.count)
        elif request.register_type == "discrete_input":
            raw_values = await client.read_discrete_inputs(request.address, request.count)
        else:
            msg = f"Unknown register type: {request.register_type}"
            raise HTTPException(status_code=400, detail=msg)

        if raw_values is None:
            raise HTTPException(status_code=500, detail="Failed to read registers")

        return ModbusReadResult(
            address=request.address,
            values=[int(v) for v in raw_values],
            register_type=request.register_type,
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/modbus/write",
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def modbus_write_register(request: ModbusWriteRequest) -> dict[str, Any]:
    """Write a value to a Modbus register."""
    if not settings.modbus_enabled:
        raise HTTPException(status_code=400, detail="Modbus is not enabled")

    try:
        from titan.connectors.modbus.connection import get_modbus_connection_manager

        manager = await get_modbus_connection_manager()
        if manager is None or not manager.is_connected:
            raise HTTPException(status_code=503, detail="Modbus not connected")

        client = await manager.ensure_connected()

        # Write based on register type
        if request.register_type == "holding_register":
            success = await client.write_register(request.address, request.value)
        elif request.register_type == "coil":
            success = await client.write_coil(request.address, bool(request.value))
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot write to register type: {request.register_type}",
            )

        return {
            "address": request.address,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# MQTT Control
# -------------------------------------------------------------------------


@router.post(
    "/mqtt/connect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def connect_mqtt() -> ConnectionResult:
    """Manually connect to the MQTT broker."""
    if not settings.mqtt_broker:
        raise HTTPException(status_code=400, detail="MQTT is not configured")

    try:
        from titan.connectors.mqtt import get_mqtt_publisher

        publisher = await get_mqtt_publisher()
        if publisher is None:
            raise HTTPException(status_code=500, detail="Failed to get MQTT publisher")

        # The publisher auto-connects, so just check status
        if getattr(publisher, "is_connected", False):
            return ConnectionResult(
                connector="MQTT",
                success=True,
                state=ConnectorState.CONNECTED,
                message="Already connected",
                timestamp=datetime.utcnow(),
            )
        else:
            return ConnectionResult(
                connector="MQTT",
                success=False,
                state=ConnectorState.DISCONNECTED,
                message="Connection pending",
                timestamp=datetime.utcnow(),
            )
    except Exception as e:
        return ConnectionResult(
            connector="MQTT",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )


@router.post(
    "/mqtt/disconnect",
    response_model=ConnectionResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def disconnect_mqtt() -> ConnectionResult:
    """Manually disconnect from the MQTT broker."""
    if not settings.mqtt_broker:
        raise HTTPException(status_code=400, detail="MQTT is not configured")

    try:
        from titan.connectors.mqtt import close_mqtt

        await close_mqtt()

        return ConnectionResult(
            connector="MQTT",
            success=True,
            state=ConnectorState.DISCONNECTED,
            message="Disconnected successfully",
            timestamp=datetime.utcnow(),
        )
    except Exception as e:
        return ConnectionResult(
            connector="MQTT",
            success=False,
            state=ConnectorState.FAILED,
            message=str(e),
            timestamp=datetime.utcnow(),
        )
