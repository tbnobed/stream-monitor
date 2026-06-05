from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sse_manager import sse_manager
import asyncio
import json

router = APIRouter(prefix="/stream", tags=["sse"])


@router.get("/status")
async def sse_status():
    """Server-Sent Events endpoint for live status updates."""

    async def event_generator():
        q = sse_manager.add_listener()
        try:
            # Send initial connected event
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            # Keep-alive loop
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except Exception:
            pass
        finally:
            sse_manager.remove_listener(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
