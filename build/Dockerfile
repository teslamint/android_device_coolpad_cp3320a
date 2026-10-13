# TWRP twrp-5.1 (AOSP 5.1.1 base) build hosts for CP3320A.
# Both stages are linux/amd64. On Apple Silicon they run under Colima VZ+Rosetta.
# Base images are pinned by multi-platform index digest.
# Every downloaded file is pinned by SHA-256.
#
# Build each stage from the repository root:
#   docker build --platform linux/amd64 --target repo-host -t twrp51-repo:r2 build
#   docker build --platform linux/amd64 --target build-host -t twrp51-build:r2 build

# Stage 1: source synchronization with the Google repo launcher.
FROM ubuntu:22.04@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401 AS repo-host
ENV DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git gnupg python3 file time \
 && curl -fSL https://storage.googleapis.com/git-repo-downloads/repo-2.65 -o /usr/local/bin/repo \
 && echo '1211b57b57e4122a9c546295a59b37d24068f1164d0e87bef096d5323c413e4f  /usr/local/bin/repo' \
      | sha256sum -c - \
 && chmod 755 /usr/local/bin/repo \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
CMD ["/bin/bash"]

# Stage 2: the AOSP 5.1 build.
# Java: Azul Zulu OpenJDK 7 (reports "openjdk version 1.7.0_352").
#   omnirom/android_build android-5.1 core/main.mk accepts javac 1.7/1.8 but
#   requires OpenJDK on Linux; xenial ships no openjdk-7, so use the tarball.
# Retain GNU make 3.81 for this legacy tree; no make 4.x failure was tested.
FROM ubuntu:16.04@sha256:1f1a2d56de1d604801a9671f301190704c25d604a416f59e03c04f5c6ffee0d6 AS build-host

ENV DEBIAN_FRONTEND=noninteractive

# Use the default Xenial archive; retry on the archive mirror if apt fails.
RUN apt-get update || { \
      sed -i -e 's|http://archive.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g' \
             -e 's|http://security.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g' \
             /etc/apt/sources.list; \
      apt-get update; \
    }
RUN apt-get install -y --no-install-recommends \
      build-essential git curl wget ca-certificates \
      zip unzip xz-utils lzop bc perl python rsync \
      bison flex gperf libxml2-utils xsltproc \
      gcc-multilib g++-multilib zlib1g-dev libncurses5-dev \
      lib32z1-dev lib32ncurses5-dev libsdl1.2-dev libssl-dev \
      schedtool pngcrush file ccache \
 && rm -rf /var/lib/apt/lists/*

# Java 7 (Azul Zulu OpenJDK 7.0.352, linux x64).
RUN curl -fSL https://cdn.azul.com/zulu/bin/zulu7.56.0.11-ca-jdk7.0.352-linux_x64.tar.gz \
      -o /tmp/zulu7.tar.gz \
 && echo '8a7387c1ed151474301b6553c6046f865dc6c1e1890bcf106acc2780c55727c8  /tmp/zulu7.tar.gz' \
      | sha256sum -c - \
 && tar -xzf /tmp/zulu7.tar.gz -C /opt \
 && mv /opt/zulu7.56.0.11-ca-jdk7.0.352-linux_x64 /opt/zulu7 \
 && rm /tmp/zulu7.tar.gz

# GNU make 3.81 (precise deb, unpacked not installed).
RUN mkdir -p /opt/make381 \
 && curl -fSL http://old-releases.ubuntu.com/ubuntu/pool/main/m/make-dfsg/make_3.81-8.1ubuntu1.1_amd64.deb \
      -o /tmp/make381.deb \
 && echo '026fa288a77ea5e267d930a9084ddceab9fe87753e537b8e1ab13b8718657c92  /tmp/make381.deb' \
      | sha256sum -c - \
 && dpkg -x /tmp/make381.deb /opt/make381 \
 && rm /tmp/make381.deb

ENV JAVA_HOME=/opt/zulu7 \
    PATH=/opt/zulu7/bin:/opt/make381/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /src
CMD ["/bin/bash"]
