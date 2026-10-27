"""Exercise real stdio + a 64px desktop crop. Never opens or arms a device."""
import asyncio
import base64
import io
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from PIL import Image


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "aikvm.cli", "serve", "--port", "COM999"])
    async with Client(params) as client:
        tools = await client.list_tools()
        status = await client.call_tool("kvm_status")
        frame = await client.call_tool("kvm_observe", {"target_id": "bench", "crop": [0, 0, 64, 64]})
        assert not status.is_error and not frame.is_error
        images = [p for p in frame.content if p.type == "image"]
        assert len(images) == 1
        image = Image.open(io.BytesIO(base64.b64decode(images[0].data)))
        assert image.size == (64, 64)
        assert not (await client.call_tool("kvm_stop")).is_error
        result = {"stdio_tools": [tool.name for tool in tools.tools], "desktop_image_decoded": True,
                  "image_size": list(image.size), "hardware_connected": False, "input_sent": False}
        root = Path(__file__).resolve().parents[1]
        (root/"artifacts/mcp-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))


asyncio.run(main())
