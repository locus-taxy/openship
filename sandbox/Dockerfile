FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/kotlin/bin:/opt/scala/bin:$PATH"
ENV JS_SANDBOX_DIR=/js-sandbox

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget unzip zip ca-certificates gnupg git build-essential \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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

# ── Rust ─────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends rustc cargo \
    && rm -rf /var/lib/apt/lists/*

# ── Kotlin ───────────────────────────────────────────────────────────────────
RUN wget --no-check-certificate -q \
    "https://github.com/JetBrains/kotlin/releases/download/v2.0.21/kotlin-compiler-2.0.21.zip" \
    && unzip -q kotlin-compiler-2.0.21.zip -d /opt \
    && mv /opt/kotlinc /opt/kotlin \
    && rm kotlin-compiler-2.0.21.zip

# ── Scala ────────────────────────────────────────────────────────────────────
RUN wget --no-check-certificate -q \
    "https://github.com/scala/scala/releases/download/v2.13.15/scala-2.13.15.tgz" \
    && tar xzf scala-2.13.15.tgz -C /opt \
    && mv /opt/scala-2.13.15 /opt/scala \
    && rm scala-2.13.15.tgz

# ── Swift (amd64 only — skip on arm64) ────────────────────────────────────────
RUN ARCH=$(uname -m) && if [ "$ARCH" = "x86_64" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev libedit2 libpython3-dev libsqlite3-dev \
        libxml2-dev pkg-config tzdata zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && wget --no-check-certificate -q \
        "https://download.swift.org/swift-6.0.3-release/ubuntu2404/swift-6.0.3-RELEASE/swift-6.0.3-RELEASE-ubuntu24.04.tar.gz" \
    && tar xzf swift-6.0.3-RELEASE-ubuntu24.04.tar.gz -C /opt \
    && ln -s /opt/swift-6.0.3-RELEASE-ubuntu24.04/usr/bin/swift /usr/local/bin/swift \
    && rm swift-6.0.3-RELEASE-ubuntu24.04.tar.gz; \
    else echo "Skipping Swift on $ARCH"; fi

# ── Crystal ──────────────────────────────────────────────────────────────────
RUN curl -fsSL https://crystal-lang.org/install.sh | bash

# ── Zig ──────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && wget --no-check-certificate -q \
        "https://ziglang.org/download/0.13.0/zig-linux-${ARCH}-0.13.0.tar.xz" \
    && tar xf "zig-linux-${ARCH}-0.13.0.tar.xz" -C /opt \
    && ln -sf "/opt/zig-linux-${ARCH}-0.13.0/zig" /usr/local/bin/zig \
    && rm "zig-linux-${ARCH}-0.13.0.tar.xz"

# ── Dart ─────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/') \
    && wget --no-check-certificate -q \
        "https://storage.googleapis.com/dart-archive/channels/stable/release/latest/sdk/dartsdk-linux-${ARCH}-release.zip" \
    && unzip -q "dartsdk-linux-${ARCH}-release.zip" -d /opt \
    && ln -s /opt/dart-sdk/bin/dart /usr/local/bin/dart \
    && rm "dartsdk-linux-${ARCH}-release.zip"

# ── Deno ─────────────────────────────────────────────────────────────────────
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -s /root/.deno/bin/deno /usr/local/bin/deno

# ── Julia ────────────────────────────────────────────────────────────────────
RUN ARCH=$(uname -m) \
    && wget --no-check-certificate -q \
        "https://julialang-s3.julialang.org/bin/linux/${ARCH}/1.10/julia-1.10.0-linux-${ARCH}.tar.gz" \
    && tar xzf "julia-1.10.0-linux-${ARCH}.tar.gz" -C /opt \
    && ln -sf "/opt/julia-1.10.0/bin/julia" /usr/local/bin/julia \
    && rm "julia-1.10.0-linux-${ARCH}.tar.gz"


# ── JS sandbox (esbuild + react + jsdom) ─────────────────────────────────────
RUN mkdir -p /js-sandbox && cd /js-sandbox \
    && echo '{"dependencies":{"react":"^18","react-dom":"^18","esbuild":"latest","jsdom":"22.1.0"}}' > package.json \
    && npm install --silent --no-audit --no-fund

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /sandbox
ENTRYPOINT ["/run.sh"]
