#!/bin/bash
# Script-render a Smokeview case to an MP4.
#
# Usage: scripts/make_smv_video.sh <fds_dir> [framerate]
#
# Expects <fds_dir>/<CHID>.ssf to exist with at least:
#   LOADPARTICLES
#   RENDERDIR
#    ./frames
#   RENDERALL
#    1
#    <CHID>
#   EXIT
#
# Writes PNGs to <fds_dir>/frames/ and stitches them into
# <fds_dir>/<CHID>.mp4 via ffmpeg.

set -euo pipefail

FDS_DIR="${1:?usage: $0 <fds_dir> [framerate]}"
FRAMERATE="${2:-30}"

if [ ! -d "$FDS_DIR" ]; then
    echo "make_smv_video: $FDS_DIR is not a directory" >&2
    exit 1
fi

SMV_FILE=$(find "$FDS_DIR" -maxdepth 1 -name "*.smv" | head -n1)
if [ -z "$SMV_FILE" ]; then
    echo "make_smv_video: no .smv file in $FDS_DIR" >&2
    exit 1
fi
CHID=$(basename "$SMV_FILE" .smv)

if [ ! -f "$FDS_DIR/$CHID.ssf" ]; then
    echo "make_smv_video: no $FDS_DIR/$CHID.ssf — create one with RENDERALL first" >&2
    exit 1
fi

mkdir -p "$FDS_DIR/frames"
rm -f "$FDS_DIR/frames/$CHID"_*.png

(cd "$FDS_DIR" && smv-dev -runscript "$CHID")

shopt -s nullglob
FRAMES=("$FDS_DIR/frames/${CHID}_"*.png)
if [ "${#FRAMES[@]}" -eq 0 ]; then
    echo "make_smv_video: smokeview produced no frames — check the .ssf" >&2
    exit 1
fi
echo "rendered ${#FRAMES[@]} frames at ${FRAMERATE} fps"

# Smokeview names frames "<CHID>_0001.png" (4-digit pad).
ffmpeg -y -framerate "$FRAMERATE" \
    -i "$FDS_DIR/frames/${CHID}_%04d.png" \
    -c:v libx264 -pix_fmt yuv420p \
    -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=white" \
    "$FDS_DIR/$CHID.mp4"

echo "wrote $FDS_DIR/$CHID.mp4"
