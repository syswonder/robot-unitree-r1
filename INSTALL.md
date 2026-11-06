# Prepare this deployment

This repository is the Unitree R1 deployment. It does not contain the Robonix runtime, the web client, the offline Python wheels, or the speech model archives. `scripts/01_build.sh` and `scripts/02_start.sh` expect those pieces in a workspace next to this clone.

## Supported target

| Item | Value |
| --- | --- |
| Machine | Unitree R1 EDU onboard computer |
| CPU | aarch64 |
| OS | Ubuntu 20.04.5, kernel `5.10.104-tegra` (JetPack 5 line) |
| Robonix source | <https://github.com/syswonder/robonix> at `ad2f90386234908b0f7e0a793cb8045bd5bc643d` (2026-10-14) |
| `rbnx` | `1.1.0-beta.1`, built with rustc 1.99.0 for `aarch64-unknown-linux-gnu` |
| Provider Python | CPython 3.10.22 |
| Web client Python | CPython 3.12.15 |

The checked runtime on this robot reports `rbnx 1.1.0-beta.1 (ad2f9038 2026-10-14)`.

## Workspace layout

`scripts/env.sh` sets `R1_ROOT` to `$HOME/r1-robonix` unless you export another directory first. This repository can live at `$R1_ROOT/robot-unitree-r1`. The other directories are siblings, not files inside this git repository.

```text
$R1_ROOT/
├── robot-unitree-r1/          # this repository
├── robonix/                   # Robonix source at the commit above
├── robonix-client/            # web client used by scripts/02_start.sh
├── bootstrap/
│   ├── wheels/                # aarch64 wheels for provider builds
│   ├── py312-wheels/          # wheels for the web client
│   └── speech-models/         # three archives listed below
├── vendor/                    # Cargo vendor directory for the offline Robonix build
└── toolchains/
    ├── cargo/
    ├── rust-1.99/
    ├── python-3.10.22/
    ├── python-3.12.15/
    └── robonix-home/codegen-venv/
```

`scripts/01_build.sh` stops if `robonix/`, `bootstrap/wheels/`, `vendor/`, or `robonix-client/` is missing. Those trees are prepared for the onboard computer and are not published here.

## Speech models

`services/r1_speech/scripts/build.sh` unpacks archives from `$R1_ROOT/bootstrap/speech-models`. It does not download them. URLs and SHA256 values are in `services/r1_speech/models.sources.json`. Fetch and check them before the first speech build:

```bash
export R1_ROOT="${R1_ROOT:-$HOME/r1-robonix}"
mkdir -p "$R1_ROOT/bootstrap/speech-models"
cd "$R1_ROOT/bootstrap/speech-models"
curl -fL -o sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30.tar.bz2
curl -fL -o vits-melo-tts-zh_en.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2
curl -fL -o sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
sha256sum -c <<'EOF'
f2ab7a5deb02717801f6a5b26c751b42f8a2db891b07f5b095e6da7442081448  sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30.tar.bz2
e58351ed7149f290a54534538badd4077cdbe6fddc964b24d0bee870415d1514  vits-melo-tts-zh_en.tar.bz2
68447f4fbc67e70eee3a93961f36e81e98f47aef73ce7e7ca00885c6cd3616a6  sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
EOF
```

The speech build also reads `$R1_ROOT/robonix/services/speech` and `$R1_ROOT/robonix/pylib/robonix-api` from the pinned Robonix tree.

## Build

```bash
export R1_ROOT="${R1_ROOT:-$HOME/r1-robonix}"
bash "$R1_ROOT/robot-unitree-r1/scripts/01_build.sh"
```

The script builds the Robonix binaries from `$R1_ROOT/robonix` with the offline Cargo vendor directory, installs them under `$R1_ROOT/toolchains/cargo/bin`, then builds every provider and service in this repository.

## Model key

Chat reads `VLM_BASE_URL`, `VLM_API_KEY`, and `VLM_MODEL`. Do not put the key in `robonix_manifest.yaml`.

`scripts/02_start.sh` sends requests to `http://127.0.0.1:16667/v1` unless `VLM_BASE_URL` is already set, and it uses the placeholder key `local-proxy` unless `VLM_API_KEY` is already set. Something on that address must accept the call. This repository does not include that proxy.

To store a key for a later proxy to read:

```bash
bash scripts/vlm_key.sh set deepseek
```

A non-DeepSeek endpoint needs its own base URL first:

```bash
export VLM_UPSTREAM='https://example.invalid/v1'
export VLM_MODEL='your-model'
bash scripts/vlm_key.sh set gateway
```

The file is `$R1_ROOT/secrets/deepseek_api_key` or `$R1_ROOT/secrets/gateway_api_key`, mode 600. Restart the proxy after replacing the file so it reads the new key, then restart the stack.
