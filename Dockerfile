FROM python:3.14-slim-bookworm AS base

# Install ffmpeg
RUN apt-get update -qq && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir uv

WORKDIR /tool
COPY uv.lock /tool
COPY pyproject.toml /tool
COPY README.md /tool
COPY mcap_to_mp4 /tool/mcap_to_mp4
RUN uv sync --locked --no-dev

ENV PATH="/tool/.venv/bin:$PATH"

WORKDIR /works
ENTRYPOINT [ "mcap-to-mp4" ]

# FROM base AS develop

# # Enable apt-get completion
# RUN rm /etc/apt/apt.conf.d/docker-clean

# # Install development tools
# RUN apt-get update -qq && \
#     apt-get install -y unzip sudo curl && \
#     rm -rf /var/lib/apt/lists/*

# # Install mcap cli
# RUN curl -L -o mcap 'https://github.com/foxglove/mcap/releases/download/releases%2Fmcap-cli%2Fv0.0.42/mcap-linux-amd64' && \
#     chmod +x mcap && \
#     mv mcap /usr/local/bin/
# CMD ["/bin/bash"]
