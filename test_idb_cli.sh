#!/bin/bash

# Test idb video-stream command
echo "Testing idb CLI video-stream"

# Run idb video-stream and capture output to file
python3 -c "from idb.cli.main import main; import sys; sys.argv = ['idb', '--companion', 'localhost:10882', 'video-stream', '--fps', '30', '--compression-quality', '0.8']; main()" > /tmp/video_stream.h264 &

STREAM_PID=$!
echo "Stream PID: $STREAM_PID"

# Let it run for 3 seconds
sleep 3

# Kill the stream
kill $STREAM_PID 2>/dev/null

# Check file size
FILE_SIZE=$(wc -c < /tmp/video_stream.h264)
echo "Captured ${FILE_SIZE} bytes"

if [ "$FILE_SIZE" -gt 0 ]; then
    echo "✅ Video stream working!"
    hexdump -C /tmp/video_stream.h264 | head -20
else
    echo "❌ No data captured"
fi
