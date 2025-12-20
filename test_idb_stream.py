#!/usr/bin/env python3
"""
Test script to verify idb video streaming capabilities.
"""

import asyncio
import sys
from idb.grpc.client import Client
from idb.common.types import VideoFormat, TCPAddress

async def test_idb_connection():
    """Test basic idb connection to simulator."""
    print("🔍 Testing idb connection...")

    try:
        # Connect to idb_companion
        address = TCPAddress(host="localhost", port=10882)
        client = Client(address=address)

        # Connect
        await client.connect()

        print(f"✅ Connected to idb")

        # Get device info
        target = await client.describe()
        print(f"📱 Device: {target.name}")
        print(f"   UDID: {target.udid}")
        print(f"   OS: {target.target_description}")
        print(f"   State: {target.state}")

        return client

    except Exception as e:
        print(f"❌ Failed to connect to idb: {e}")
        print("\n💡 Tip: Make sure idb_companion is running:")
        print("   idb_companion --udid <SIMULATOR_UDID> --grpc-port 10882 &")
        import traceback
        traceback.print_exc()
        return None

async def test_video_stream(client):
    """Test video streaming from simulator."""
    print("\n🎥 Testing video stream...")

    try:
        # Start video stream
        # This returns an async generator of video bytes
        print("📡 Requesting video stream (H.264 format, 30 fps)...")

        frame_count = 0
        total_bytes = 0

        async for data in client.video_stream(
            format=VideoFormat.H264,
            fps=30,
            compression_quality=0.8,
        ):
            frame_count += 1
            total_bytes += len(data)
            print(f"   Frame {frame_count}: {len(data)} bytes (total: {total_bytes} bytes)")

            if frame_count >= 10:
                print("\n⏹️  Stopping after 10 frames...")
                break

        print(f"\n✅ Successfully received {frame_count} frames ({total_bytes} bytes total)!")
        return True

    except Exception as e:
        print(f"❌ Video stream failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    print("=" * 60)
    print("IDB Video Streaming Test")
    print("=" * 60)

    # Test connection
    client = await test_idb_connection()
    if not client:
        sys.exit(1)

    # Test video streaming
    success = await test_video_stream(client)

    if success:
        print("\n" + "=" * 60)
        print("✅ All tests passed! idb video streaming is working.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ Video streaming test failed.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
