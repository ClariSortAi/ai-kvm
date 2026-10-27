from __future__ import annotations

import base64
import json

from mcp.server import MCPServer
from mcp.types import ImageContent, TextContent, ToolAnnotations

from .core import Action, Core


def content(metadata: dict, observation=None):
    result = [TextContent(type="text", text=json.dumps(metadata))]
    if observation:
        result.append(ImageContent(type="image", data=base64.b64encode(observation.png()).decode(), mime_type="image/png"))
    return result


def make_server(core: Core):
    server = MCPServer("aikvm_mcp", version="0.2.0", instructions=(
        "Controls physical USB input. Observe first, use explicit target/frame IDs, inspect each result. "
        "Input acknowledgments do not prove host outcomes. Use only on an operator-approved bench target. "
        "There is no semantic approval classifier. Obtain human authorization for consequential actions. "
        "STOP disarms; rearming requires a local controller restart. Holds expire after 1.5 seconds."))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))
    def kvm_status() -> dict:
        """Report configured target, connection and capture source; does not connect or arm input."""
        return {"target_id": core.target, "input": core.device.status(), "capture_source": core.capture.source,
                "last_frame": core.capture.last.metadata() if core.capture.last else None,
                "video_signal_verified": False, "mode": getattr(core,"mode","usb_same_pc")}

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))
    def kvm_observe(target_id: str, crop: list[int] | None = None) -> list[TextContent | ImageContent]:
        """Return a fresh native-size frame and metadata. Optional crop is [x,y,width,height]. Frames expire after 5 seconds for input."""
        if target_id != core.target:
            raise ValueError("Wrong target binding")
        if crop is not None and (len(crop) != 4 or any(type(v) is not int for v in crop)):
            raise ValueError("Crop must contain four integer coordinates")
        observation = core.capture.grab(tuple(crop) if crop else None)
        return content(observation.metadata(), observation)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False))
    def kvm_act(target_id: str, frame_id: str, action: Action) -> list[TextContent | ImageContent]:
        """Submit one bounded input action, then return a fresh observation or capture error. Use move_abs coordinates in the referenced image. No automatic retries. Keyboard layout: US ASCII. Input must be armed locally."""
        result, observation = core.act(target_id, frame_id, action)
        return content(result, observation)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True))
    def kvm_stop() -> dict:
        """Disarm, cancel typing between characters and request release-all. Reports device acknowledgment separately from host receipt. Unplug is the physical stop."""
        return core.device.stop()

    return server
