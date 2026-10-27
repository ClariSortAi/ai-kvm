import asyncio

from mcp import Client

from aikvm.core import Core
from aikvm.server import make_server
from test_controller import CaptureFixture, make_device


def test_mcp_tools_images_schemas_and_disarmed_input():
    async def scenario():
        capture = CaptureFixture()
        device, _transport = make_device()
        server = make_server(Core(device, capture, "bench"))
        async with Client(server) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            assert set(tools) == {"kvm_status", "kvm_observe", "kvm_act", "kvm_stop"}
            assert tools["kvm_act"].annotations.destructive_hint is True
            schema = tools["kvm_act"].input_schema
            assert "discriminator" in schema["properties"]["action"]
            result = await client.call_tool("kvm_observe", {"target_id": "bench", "crop": [0, 0, 64, 64]})
            assert not result.is_error
            assert any(part.type == "image" and part.mime_type == "image/png" for part in result.content)
            blocked = await client.call_tool("kvm_act", {"target_id": "bench", "frame_id": capture.last.id,
                                                         "action": {"op": "click", "button": "left"}})
            assert blocked.is_error and not device.armed
            bad = await client.call_tool("kvm_act", {"target_id": "bench", "frame_id": capture.last.id,
                                                     "action": {"op": "move", "dx": 999, "dy": 0}})
            assert bad.is_error
            device.arm()  # Transport fixture only; verifies successful MCP serialization.
            accepted = await client.call_tool("kvm_act", {"target_id": "bench", "frame_id": capture.last.id,
                                                          "action": {"op": "click", "button": "left"}})
            assert not accepted.is_error
            assert any(part.type == "image" for part in accepted.content)
            stopped = await client.call_tool("kvm_stop")
            assert not stopped.is_error
        device.close()
    asyncio.run(scenario())
