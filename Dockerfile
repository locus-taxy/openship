FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/kotlin/bin:/opt/scala/bin:$PATH"

# ── Base tooling ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget unzip zip ca-certificates gnupg git build-essential \
    software-properties-common \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Optional corporate proxy CA ───────────────────────────────────────────────
ARG CORPORATE_CA_CERT=""
RUN if [ -n "$CORPORATE_CA_CERT" ]; then \
    printf '%s' "$CORPORATE_CA_CERT" > /usr/local/share/ca-certificates/corporate-ca.crt \
    && update-ca-certificates; fi

# ── Scripting languages ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    ruby perl lua5.4 php-cli \
    nodejs npm \
    gawk tcl \
    && rm -rf /var/lib/apt/lists/*

# ── Systems languages ─────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ gfortran \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

# ── JVM ───────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk \
    && rm -rf /var/lib/apt/lists/*

# ── Functional / academic ─────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghc ocaml sbcl \
    && rm -rf /var/lib/apt/lists/*

# ── Other languages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    elixir swi-prolog \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    gnucobol racket nim \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    haxe r-base \
    && rm -rf /var/lib/apt/lists/*

# ── New languages ─────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    groovy clojure nasm \
    && rm -rf /var/lib/apt/lists/*

# ── SML (polyml) + Octave ─────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    polyml octave \
    && rm -rf /var/lib/apt/lists/*

# ── Fish, Raku, Guile, D, Vala, Pascal, Ada ──────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    fish rakudo guile-3.0 \
    gdc valac libglib2.0-dev fpc gnat \
    && ln -sf "$(command -v guile-3.0)" /usr/local/bin/guile \
    && rm -rf /var/lib/apt/lists/*

# ── Extended batch: shells, Lisps, Forth, BASIC, Algol, Objective-C ──────────
# High-confidence packages (available on amd64 + arm64). libgc-dev is for V's GC.
RUN apt-get update && apt-get install -y --no-install-recommends \
    zsh luajit expect m4 gforth regina-rexx gobjc libgc-dev \
    && rm -rf /var/lib/apt/lists/*

# Best-effort packages — some may be unavailable on a given arch; never fail the build.
RUN apt-get update; \
    for p in ksh tcsh clisp pike8.0 algol68g gambc chicken-bin newlisp yabasic; do \
        apt-get install -y --no-install-recommends "$p" || echo "skip $p"; \
    done; \
    if command -v pike8.0 >/dev/null; then ln -sf "$(command -v pike8.0)" /usr/local/bin/pike; fi; \
    if command -v chicken-csi >/dev/null; then ln -sf "$(command -v chicken-csi)" /usr/local/bin/csi; fi; \
    rm -rf /var/lib/apt/lists/*

# ── V (vlang) — built from source; best-effort ───────────────────────────────
RUN git clone --depth=1 https://github.com/vlang/v /opt/v \
    && ( cd /opt/v && make && ./v symlink ) \
    || echo "skip V build"

# ── .NET SDK 8 ────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    dotnet-sdk-8.0 \
    && rm -rf /var/lib/apt/lists/*

# ── PowerShell 7.4 LTS ───────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && PWSH_ARCH=$([ "$ARCH" = "aarch64" ] && echo "arm64" || echo "x64") \
    && curl -fL \
        "https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/powershell-7.4.6-linux-${PWSH_ARCH}.tar.gz" \
        -o /tmp/pwsh.tar.gz \
    && mkdir -p /opt/powershell \
    && tar xzf /tmp/pwsh.tar.gz -C /opt/powershell \
    && chmod +x /opt/powershell/pwsh \
    && ln -sf /opt/powershell/pwsh /usr/local/bin/pwsh \
    && rm /tmp/pwsh.tar.gz

# ── CoffeeScript ──────────────────────────────────────────────────────────────
RUN npm install -g coffeescript --silent

# ── Rust ─────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends rustc cargo \
    && rm -rf /var/lib/apt/lists/*

# ── Kotlin ───────────────────────────────────────────────────────────────────
RUN wget -q \
    "https://github.com/JetBrains/kotlin/releases/download/v2.0.21/kotlin-compiler-2.0.21.zip" \
    && unzip -q kotlin-compiler-2.0.21.zip -d /opt \
    && mv /opt/kotlinc /opt/kotlin \
    && rm kotlin-compiler-2.0.21.zip

# ── Scala ────────────────────────────────────────────────────────────────────
RUN wget -q \
    "https://github.com/scala/scala/releases/download/v2.13.15/scala-2.13.15.tgz" \
    && tar xzf scala-2.13.15.tgz -C /opt \
    && mv /opt/scala-2.13.15 /opt/scala \
    && rm scala-2.13.15.tgz

# ── Swift (amd64 only) ────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) && if [ "$ARCH" = "x86_64" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev libedit2 libpython3-dev libsqlite3-dev \
        libxml2-dev pkg-config tzdata zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && wget -q \
        "https://download.swift.org/swift-6.0.3-release/ubuntu2404/swift-6.0.3-RELEASE/swift-6.0.3-RELEASE-ubuntu24.04.tar.gz" \
    && tar xzf swift-6.0.3-RELEASE-ubuntu24.04.tar.gz -C /opt \
    && ln -s /opt/swift-6.0.3-RELEASE-ubuntu24.04/usr/bin/swift /usr/local/bin/swift \
    && rm swift-6.0.3-RELEASE-ubuntu24.04.tar.gz; \
    else echo "Skipping Swift on $ARCH"; fi

# ── Crystal (x86_64 only) ─────────────────────────────────────────────────────
RUN ARCH=$(uname -m) && if [ "$ARCH" = "x86_64" ]; then \
    curl -fsSL https://crystal-lang.org/install.sh | bash; \
    else echo "Skipping Crystal on $ARCH (no Linux ARM64 release available)"; fi

# ── Zig ──────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && wget -q \
        "https://ziglang.org/download/0.13.0/zig-linux-${ARCH}-0.13.0.tar.xz" \
    && tar xf "zig-linux-${ARCH}-0.13.0.tar.xz" -C /opt \
    && ln -sf "/opt/zig-linux-${ARCH}-0.13.0/zig" /usr/local/bin/zig \
    && rm "zig-linux-${ARCH}-0.13.0.tar.xz"

# ── Dart ─────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/') \
    && wget -q \
        "https://storage.googleapis.com/dart-archive/channels/stable/release/latest/sdk/dartsdk-linux-${ARCH}-release.zip" \
    && unzip -q "dartsdk-linux-${ARCH}-release.zip" -d /opt \
    && ln -s /opt/dart-sdk/bin/dart /usr/local/bin/dart \
    && rm "dartsdk-linux-${ARCH}-release.zip"

# ── Deno ─────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && DENO_ARCH=$([ "$ARCH" = "aarch64" ] && echo "aarch64" || echo "x86_64") \
    && curl -fL \
        "https://github.com/denoland/deno/releases/latest/download/deno-${DENO_ARCH}-unknown-linux-gnu.zip" \
        -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip

# ── Julia ────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && wget -q \
        "https://julialang-s3.julialang.org/bin/linux/${ARCH}/1.10/julia-1.10.0-linux-${ARCH}.tar.gz" \
    && tar xzf "julia-1.10.0-linux-${ARCH}.tar.gz" -C /opt \
    && ln -sf "/opt/julia-1.10.0/bin/julia" /usr/local/bin/julia \
    && rm "julia-1.10.0-linux-${ARCH}.tar.gz"

# ── Python (for the app) ──────────────────────────────────────────────────────
# Use Ubuntu 24.04's system Python 3.12 (the deadsnakes PPA needs a strict-TLS
# Launchpad call that fails behind intercepting corporate proxies). The app has
# no 3.13-only requirements.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-venv python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Pre-install JS sandbox packages (avoids runtime npm install) ──────────────
# Must match _SANDBOX_VERSION in controllers/execute.py. jsdom pinned to 22.x
# (jsdom >=24 pulls an ESM-only dep that breaks Node 18 + esbuild CJS bundling).
ENV OPENSHIP_JS_SANDBOX_PATH=/opt/openship_js_sandbox
RUN mkdir -p /opt/openship_js_sandbox \
    && echo '{"dependencies":{"react":"^18","react-dom":"^18","esbuild":"latest","jsdom":"22.1.0"}}' \
        > /opt/openship_js_sandbox/package.json \
    && cd /opt/openship_js_sandbox \
    && npm install --silent --no-audit --no-fund \
    && echo "3" > /opt/openship_js_sandbox/.ready

# ── App setup ─────────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
# Verify against the system CA bundle (includes CORPORATE_CA_CERT when provided)
# instead of disabling TLS verification.
RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --cert /etc/ssl/certs/ca-certificates.crt \
        --upgrade pip \
    && .venv/bin/pip install --no-cache-dir --cert /etc/ssl/certs/ca-certificates.crt \
        -r requirements.txt

COPY . .

# The container itself is the isolation boundary; code runs as subprocesses inside it.
# (The _run_in_docker path needs a Docker socket, which is intentionally not mounted.)
ENV SANDBOX_USE_DOCKER=false

EXPOSE 3005

COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run the API — and the user-submitted code it executes — as a non-root user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

ENTRYPOINT ["/entrypoint.sh"]
