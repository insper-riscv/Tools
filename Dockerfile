# syntax=docker/dockerfile:1
#
# Test image for riscv-tools: GHDL, the RISC-V GCC toolchain and a patched
# Spike on PATH at the same locations the workstation install
# (insper-riscv/Infra) uses, plus uv and the project's dependencies.
#
#   docker build -t riscv-tools-tests .
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests            # whole suite
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v
#
# By default the GCC is the riscv-collab release. To use the toolchain that
# insper-riscv/Infra's GCC_SETUP.md installed on the workstation instead (the
# one with picolibc), hand its directory over as a named build context:
#
#   docker build --build-context riscv-gcc=/opt/riscv-foundation/riscv32-elf \
#       -t riscv-tools-tests .

ARG GHDL_IMAGE=ghdl/ghdl:6.0.0-mcode-ubuntu-24.04
ARG UV_VERSION=0.12.20


# Spike, built the way Infra's SPIKE_SETUP.md builds it: the debug module is
# moved from address 0 to 0x70000000 so a target whose ROM starts at 0 can run.
FROM ${GHDL_IMAGE} AS spike-build
ARG SPIKE_COMMIT=0bff12123b1fd510e19e19634dd997dbade70e54

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential git ca-certificates device-tree-compiler \
      libboost-regex-dev libboost-system-dev \
 && rm -rf /var/lib/apt/lists/*

RUN git init /src \
 && git -C /src fetch --depth 1 https://github.com/riscv-software-src/riscv-isa-sim "${SPIKE_COMMIT}" \
 && git -C /src checkout FETCH_HEAD \
 && sed -i "s/^#define DEBUG_START .*/#define DEBUG_START        0x70000000/" /src/riscv/platform.h

RUN mkdir /build \
 && cd /build \
 && /src/configure --prefix=/opt/riscv-foundation/spike \
 && make -j"$(nproc)" \
 && make install


FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv


# The RISC-V GCC, with the toolchain directory as the root of the stage. This
# stage is replaced by a local directory when `--build-context riscv-gcc=...`
# is given.
FROM ${GHDL_IMAGE} AS gcc-download
ARG RISCV_GCC_TAG=2026.08.27
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir /toolchain \
 && curl -fsSL "https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/${RISCV_GCC_TAG}/riscv32-elf-ubuntu-24.04-gcc.tar.xz" \
    | tar -xJ -C /toolchain --strip-components=1

FROM scratch AS riscv-gcc
COPY --from=gcc-download /toolchain /


FROM ${GHDL_IMAGE}

# libmpc3/libmpfr6: cc1 of the RISC-V GCC links against them.
# libboost-*: Spike's runtime. libatomic1: the node that pyright downloads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates git \
      libmpc3 libmpfr6 libboost-regex1.83.0 libboost-system1.83.0 libatomic1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=riscv-gcc / /opt/riscv-foundation/riscv32-elf
COPY --from=spike-build /opt/riscv-foundation/spike /opt/riscv-foundation/spike
COPY --from=uv /uv /uvx /usr/local/bin/

ENV PATH=/opt/riscv-foundation/riscv32-elf/bin:/opt/riscv-foundation/spike/bin:$PATH \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    RUFF_CACHE_DIR=/tmp/ruff-cache

# Dependencies and pyright's node are baked in, so a run only installs the
# project itself.
WORKDIR /workspace
COPY .python-version pyproject.toml uv.lock ./
RUN uv python install \
 && uv sync --frozen --group dev --extra sim --no-install-project \
 && /opt/venv/bin/pyright --version

ENTRYPOINT ["uv", "run", "--frozen", "--group", "dev", "--extra", "sim", "pytest", "-p", "no:cacheprovider"]
CMD ["-q"]
