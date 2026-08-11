#!/usr/bin/env bash
set -euo pipefail

VERSION="1.8.1"
DESTINATION="${1:-${TMPDIR:-/tmp}/mcp-publisher}"
OS_RAW="$(uname -s)"
ARCH_RAW="$(uname -m)"

case "$OS_RAW" in
  Linux) os="linux" ;;
  Darwin) os="darwin" ;;
  *) echo "Unsupported operating system for mcp-publisher: $OS_RAW" >&2; exit 1 ;;
esac

case "$ARCH_RAW" in
  x86_64|amd64) arch="amd64" ;;
  arm64|aarch64) arch="arm64" ;;
  *) echo "Unsupported architecture for mcp-publisher: $ARCH_RAW" >&2; exit 1 ;;
esac

case "${os}_${arch}" in
  darwin_amd64) expected="88126981225e7714fcc6b7a10cdba4a80ae5901e9740a8c06d0d5195c8bc294c" ;;
  darwin_arm64) expected="e45e520892460732a4bdf37255576415d4a53ec171f8b913faf15bb1aef7cb77" ;;
  linux_amd64) expected="a06c9096dcb9727c13555b6be26c7effa707b01f06a4c561ba7a3635443cf2cc" ;;
  linux_arm64) expected="8dd75a6cf6845688b5d4e46df58d3ca26d5c8d233bb0626606e1db82c5e883e4" ;;
  *) echo "Unsupported mcp-publisher platform: ${os}_${arch}" >&2; exit 1 ;;
esac

asset="mcp-publisher_${os}_${arch}.tar.gz"
url="https://github.com/modelcontextprotocol/registry/releases/download/v${VERSION}/${asset}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM
archive="$tmp/$asset"

curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --output "$archive" "$url"

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$archive" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
else
  echo "sha256sum or shasum is required" >&2
  exit 1
fi

if [ "$actual" != "$expected" ]; then
  echo "mcp-publisher checksum mismatch: expected $expected, got $actual" >&2
  exit 1
fi

mkdir -p "$DESTINATION"
tar -xzf "$archive" -C "$DESTINATION" mcp-publisher
chmod 0755 "$DESTINATION/mcp-publisher"
"$DESTINATION/mcp-publisher" --version >&2
printf '%s\n' "$DESTINATION/mcp-publisher"
