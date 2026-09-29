#!/bin/sh
# Container entrypoint for LGMT.
#
#   docker run <image>                  -> lgmt demo   (offline mock demo)
#   docker run <image> lgmt <args...>   -> any lgmt CLI subcommand
#   docker run <image> lgmt-web         -> Gradio web demo on :7860
set -e

if [ "$1" = "lgmt-web" ]; then
    shift
    exec python -m lgmt.webapp "$@"
fi

exec "$@"
