# syntax=docker/dockerfile:1
#
# Test image for riscv-tools: GHDL, the RISC-V GCC toolchain and a patched
# Spike on PATH at the same locations the workstation install
# (insper-riscv/Infra) uses, plus uv and the project's dependencies.
#
#   docker build -t riscv-tools-tests .
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests            # whole suite
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v

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


FROM ${GHDL_IMAGE}
ARG RISCV_GCC_TAG=2026.08.27

# libmpc3/libmpfr6: cc1 of the RISC-V GCC links against them.
# libboost-*: Spike's runtime. libatomic1: the node that pyright downloads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git xz-utils \
      libmpc3 libmpfr6 libboost-regex1.83.0 libboost-system1.83.0 libatomic1 \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/riscv-foundation/riscv32-elf \
 && curl -fsSL "https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/${RISCV_GCC_TAG}/riscv32-elf-ubuntu-24.04-gcc.tar.xz" \
    | tar -xJ -C /opt/riscv-foundation/riscv32-elf --strip-components=1

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
