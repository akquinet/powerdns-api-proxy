#!/bin/sh
# Build a self-contained rpm/deb. Run from the repo root inside the target distro
# container (rockylinux:8 or debian:13) so native wheels match its glibc.
#   usage: VERSION=1.2.3 packaging/build.sh <rpm|deb>
set -eu

FORMAT="${1:?usage: build.sh <rpm|deb>}"
: "${VERSION:?VERSION is required}"

PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.14.8%2B20261009-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_SHA256="ddc902fd26460f728758c67d80417c1031edf97589f1f162c4ba3aa158a35998"
NFPM_URL="https://github.com/goreleaser/nfpm/releases/download/v2.48.0/nfpm_2.48.0_Linux_x86_64.tar.gz"
NFPM_SHA256="6d7f9a28b2f397934403950fcbba83f598b08d02edbe79a0815b3b4897341750"

PREFIX="build/opt/powerdns-api-proxy"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch() { # url sha256 dest
    curl -fsSL --retry 3 -o "$3" "$1"
    echo "$2  $3" | sha256sum -c -
}

rm -rf build dist
mkdir -p "$PREFIX" dist

fetch "$PYTHON_URL" "$PYTHON_SHA256" "$TMP/python.tar.gz"
tar -xzf "$TMP/python.tar.gz" -C "$TMP"
mv "$TMP/python" "$PREFIX/python"

"$PREFIX/python/bin/python3" -m venv --copies "$PREFIX/venv"
"$PREFIX/venv/bin/pip" --no-cache-dir install -r requirements.txt

# The venv was created at a build path; make interpreter symlinks/paths absolute
# to the install location.
sed -i "s|$PWD/build||g" "$PREFIX/venv/pyvenv.cfg"
for f in "$PREFIX"/venv/bin/*; do
    if [ -f "$f" ] && [ ! -L "$f" ] && [ "$(head -c2 "$f")" = "#!" ]; then
        sed -i "1s|^#!.*$PWD/build|#!|" "$f"
    fi
done
ln -sfn /opt/powerdns-api-proxy/python/bin/python3 "$PREFIX/venv/bin/python3"
ln -sfn python3 "$PREFIX/venv/bin/python"

cp -r powerdns_api_proxy "$PREFIX/venv/lib/python3.14/site-packages/"
find "$PREFIX" -name __pycache__ -type d -prune -exec rm -rf {} +

fetch "$NFPM_URL" "$NFPM_SHA256" "$TMP/nfpm.tar.gz"
tar -xzf "$TMP/nfpm.tar.gz" -C "$TMP" nfpm

VERSION="$VERSION" "$TMP/nfpm" package \
    --config packaging/nfpm.yaml --packager "$FORMAT" --target dist/
ls -l dist/
