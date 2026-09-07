#!/usr/bin/env python3
"""Encrypt a QA-owned FINN manifest for the protected production runner.

Only the public key is shared with QA. The matching private key remains on the
production host under its existing secret directory, so a sealed manifest is
never exposed to Build, GitHub logs, or a QA chat.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


VERSION = "finn-qa-manifest-v1"
INFO = b"FINN production QA manifest bundle v1"


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _derive_key(*, private_key: X25519PrivateKey, peer_key: X25519PublicKey) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(private_key.exchange(peer_key))


def encrypt_manifest(*, public_key_b64: str, plaintext: bytes) -> str:
    recipient = X25519PublicKey.from_public_bytes(_decode(public_key_b64))
    ephemeral = X25519PrivateKey.generate()
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key(private_key=ephemeral, peer_key=recipient)).encrypt(nonce, plaintext, INFO)
    public = ephemeral.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return ".".join((VERSION, _encode(public), _encode(nonce), _encode(ciphertext)))


def decrypt_manifest(*, private_key_path: Path, bundle: str) -> bytes:
    version, public_b64, nonce_b64, ciphertext_b64 = bundle.strip().split(".", 3)
    if version != VERSION:
        raise ValueError("manifest_bundle_version_invalid")
    private = X25519PrivateKey.from_private_bytes(private_key_path.read_bytes())
    peer = X25519PublicKey.from_public_bytes(_decode(public_b64))
    return AESGCM(_derive_key(private_key=private, peer_key=peer)).decrypt(_decode(nonce_b64), _decode(ciphertext_b64), INFO)


def ensure_private_key(path: Path) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_bytes()
        private = X25519PrivateKey.from_private_bytes(raw)
        os.chmod(path, 0o600)
    else:
        private = X25519PrivateKey.generate()
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    return _encode(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypt or decrypt a FINN QA manifest bundle")
    commands = parser.add_subparsers(dest="command", required=True)
    public = commands.add_parser("public-key")
    public.add_argument("--private-key-path", required=True)
    encrypt = commands.add_parser("encrypt")
    encrypt.add_argument("--public-key", required=True)
    encrypt.add_argument("--manifest", required=True)
    decrypt = commands.add_parser("decrypt")
    decrypt.add_argument("--private-key-path", required=True)
    decrypt.add_argument("--bundle-path", required=True)
    decrypt.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "public-key":
        print(ensure_private_key(Path(args.private_key_path)))
        return 0
    if args.command == "encrypt":
        manifest = Path(args.manifest).read_bytes()
        if len(manifest) > 48_000:
            raise SystemExit("manifest_plaintext_too_large")
        print(encrypt_manifest(public_key_b64=args.public_key, plaintext=manifest))
        return 0
    plaintext = decrypt_manifest(private_key_path=Path(args.private_key_path), bundle=Path(args.bundle_path).read_text(encoding="utf-8"))
    output = Path(args.output)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(plaintext)
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
