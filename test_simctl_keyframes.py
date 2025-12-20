#!/usr/bin/env python3
"""
Test simctl io recordVideo to check if it produces keyframes properly.
This will verify if simctl is better than idb for our use case.
"""

import subprocess
import asyncio
from av.codec import CodecContext

async def test_simctl_keyframes():
    """Test if simctl produces proper keyframes."""
    print("🔍 Testing simctl io recordVideo for keyframe support...")
    print()

    # Start simctl process
    process = subprocess.Popen(
        ['xcrun', 'simctl', 'io', 'booted', 'recordVideo', 'h264', '-'],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    # Create H.264 decoder
    codec = CodecContext.create('h264', 'r')

    keyframe_count = 0
    p_frame_count = 0
    total_frames = 0
    first_keyframe_at = None

    try:
        # Read for 3 seconds
        timeout = asyncio.get_event_loop().time() + 3.0

        while asyncio.get_event_loop().time() < timeout:
            # Read chunk
            data = process.stdout.read(4096)
            if not data:
                break

            # Parse and decode
            try:
                packets = codec.parse(data)
                for packet in packets:
                    is_keyframe = packet.is_keyframe

                    # Decode to verify
                    frames = codec.decode(packet)
                    for frame in frames:
                        total_frames += 1

                        if is_keyframe:
                            keyframe_count += 1
                            if first_keyframe_at is None:
                                first_keyframe_at = total_frames
                            print(f"🔑 Frame {total_frames}: KEYFRAME")
                        else:
                            p_frame_count += 1
                            if total_frames <= 10 or total_frames % 30 == 0:
                                print(f"📹 Frame {total_frames}: P-frame")

                        if total_frames >= 90:  # Test 3 seconds at 30fps
                            raise StopIteration()

            except StopIteration:
                break
            except Exception as e:
                if total_frames < 5:
                    print(f"⚠️  Decode error (early frames): {e}")
                continue

    finally:
        process.terminate()
        process.wait()

    print()
    print("=" * 60)
    print("📊 RESULTS:")
    print("=" * 60)
    print(f"Total frames decoded: {total_frames}")
    print(f"Keyframes (I-frames): {keyframe_count}")
    print(f"P-frames: {p_frame_count}")
    print(f"First keyframe at: frame #{first_keyframe_at}" if first_keyframe_at else "❌ NO KEYFRAMES FOUND")

    if keyframe_count > 0:
        keyframe_interval = total_frames / keyframe_count if keyframe_count > 0 else 0
        print(f"Keyframe interval: ~{keyframe_interval:.1f} frames")

    print()

    # Verdict
    if keyframe_count >= 3 and first_keyframe_at and first_keyframe_at <= 1:
        print("✅ VERDICT: simctl produces EXCELLENT keyframes!")
        print("   → Recommended for production use")
        print("   → Should have NO corruption during transitions")
        return True
    elif keyframe_count >= 1:
        print("⚠️  VERDICT: simctl produces SOME keyframes")
        print("   → Better than idb, but not perfect")
        print("   → May have minor corruption during fast transitions")
        return True
    else:
        print("❌ VERDICT: simctl has SAME PROBLEM as idb")
        print("   → No advantage over idb")
        print("   → Will have corruption issues")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_simctl_keyframes())
    exit(0 if result else 1)
