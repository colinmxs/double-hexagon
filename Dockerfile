# ==========================================================================
# Devcontainer for BBP HKBG (Holiday Kids Bike Giveaway)
# Python 3.12 + Node.js 22 + AWS CDK + AWS CLI
# ==========================================================================

FROM ubuntu:noble@sha256:186072bba1b2f436cbb91ef2567abca677337cfc786c86e107d25b7072feef0c

ENV DEBIAN_FRONTEND=noninteractive

# --- System packages ---
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        curl \
        wget \
        git \
        build-essential \
        unzip \
        sudo \
        ca-certificates \
        gnupg \
        software-properties-common \
        jq \
    && rm -rf /var/lib/apt/lists/*

# --- Python 3.12 from deadsnakes PPA ---
RUN add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
        python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /uvx /usr/local/bin/

# Python packages for local dev server and Lambda handlers
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed \
    flask flask-cors boto3 moto pytest

# ruff — Python linter (standalone binary, no pip conflicts)
COPY --from=ghcr.io/astral-sh/ruff:0.15.6 /ruff /usr/local/bin/ruff

# --- Node.js 22.x ---
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- AWS CLI v2 ---
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# --- Docker CLI (GPG-verified, no daemon) ---
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI ---
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user ---
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
ARG DOCKER_GID=985

RUN EXISTING_USER=$(getent passwd $USER_UID | cut -d: -f1) \
    && EXISTING_GROUP=$(getent group $USER_GID | cut -d: -f1) \
    && if [ -n "$EXISTING_GROUP" ] && [ "$EXISTING_GROUP" != "$USERNAME" ]; then \
        groupmod -n $USERNAME $EXISTING_GROUP; \
    elif [ -z "$EXISTING_GROUP" ]; then \
        groupadd --gid $USER_GID $USERNAME; \
    fi \
    && if [ -n "$EXISTING_USER" ] && [ "$EXISTING_USER" != "$USERNAME" ]; then \
        usermod -l $USERNAME -d /home/$USERNAME -m $EXISTING_USER; \
    elif [ -z "$EXISTING_USER" ]; then \
        useradd --uid $USER_UID --gid $USER_GID -m $USERNAME; \
    fi \
    && echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers \
    && groupadd -f -g $DOCKER_GID docker \
    && usermod -aG docker $USERNAME

COPY --chown=$USER_UID:$USER_GID entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER $USERNAME
WORKDIR /workspace

ENTRYPOINT ["entrypoint.sh"]
CMD ["sleep", "infinity"]
