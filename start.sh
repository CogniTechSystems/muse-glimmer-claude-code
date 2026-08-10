#!/bin/zsh
# Start Muse-Glimmer-30B with llama-server.
# Usage: zsh start.sh          with the dflash drafter (speculative decoding)
#        zsh start.sh plain    baseline, no drafter
cd "$(dirname "$0")"

MODEL=models/glimmer/Muse-Glimmer-30B-UD-Q4_K_XL.gguf
DRAFT=models/glimmer/dflash-kquant.gguf
COMMON=(--parallel 1 --cache-reuse 256 --host 127.0.0.1 --port 8000 -c 32768 -ngl 99 --jinja)

if [[ "$1" == "plain" ]]; then
  exec llama-server -m "$MODEL" "${COMMON[@]}"
else
  exec llama-server -m "$MODEL" -md "$DRAFT" \
    --spec-type draft-dflash --spec-draft-n-max 16 -ngld 99 "${COMMON[@]}"
fi
