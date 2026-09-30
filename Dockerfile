# syntax=docker/dockerfile:1
#
# Test image for riscv-tools: insper-riscv/Infra's toolchain image (GHDL, the
# RISC-V GCC with picolibc, a patched Spike and uv, at the paths of the
# workstation install) plus this project's dependencies.
#
#   docker build -t riscv-tools-tests .
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests            # whole suite
#   docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v

ARG TOOLCHAIN_IMAGE=ghcr.io/insper-riscv/infra-toolchain:sha-a3481e0
FROM ${TOOLCHAIN_IMAGE}

# libatomic1: the node that pyright downloads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 \
 && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
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
