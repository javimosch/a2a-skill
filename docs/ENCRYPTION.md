# a2a Message Encryption (v1.3)

End-to-end encrypted messaging for sensitive communications.

## Overview

Optional encryption for messages using:
- **Symmetric encryption** — Shared key (fast, for small groups)
- **Asymmetric encryption** — Public/private keys (secure, scalable)
- **Transparent wrapping** — Automatic encryption/decryption with metadata

## Installation

```bash
pip install cryptography
```

## Quick Start

### Symmetric Encryption (Shared Key)

```python
from a2a_crypto import CryptoClient

crypto = CryptoClient("my-project", "alice")

# Generate shared key
key = crypto.generate_symmetric_key()
print(f"Shared key: {key}")

# Encrypt message
encrypted = crypto.encrypt_message("Secret message", key)

# Decrypt message
decrypted = crypto.decrypt_message(encrypted, key)
print(decrypted)  # "Secret message"
```

### Asymmetric Encryption (Public/Private Keys)

```python
from a2a_crypto import CryptoClient

# Alice generates keypair
alice_crypto = CryptoClient("my-project", "alice")
public_key, private_key = alice_crypto.generate_keypair()

# Bob encrypts message to Alice using her public key
bob_crypto = CryptoClient("my-project", "bob")
encrypted = bob_crypto.encrypt_with_public_key("Secret for Alice", public_key)

# Alice decrypts with her private key
decrypted = alice_crypto.decrypt_with_private_key(encrypted)
print(decrypted)  # "Secret for Alice"
```

### Transparent Message Wrapping

```python
from a2a_crypto import CryptoClient
import json
from a2a_client import A2AClient

crypto = CryptoClient("my-project", "alice")
a2a = A2AClient("my-project", "alice")

# Get Bob's public key (shared previously)
bob_public_key = "-----BEGIN PUBLIC KEY-----\n..."

# Send encrypted message
encrypted_msg = crypto.wrap_encrypted_message("Confidential", bob_public_key)
a2a.send("bob", encrypted_msg)

# Receive and decrypt
messages = a2a.recv(unread_only=True)
for msg in messages:
    decrypted = CryptoClient.unwrap_encrypted_message(msg["body"], crypto)
    if decrypted:
        print(f"Decrypted: {decrypted}")
```

## API Reference

### CryptoClient

```python
class CryptoClient:
    # Key Management
    def generate_symmetric_key(self) -> str
    def generate_keypair(self) -> Tuple[str, str]
    def get_public_key(self) -> str

    # Symmetric Encryption
    def encrypt_message(message: str, symmetric_key: str) -> str
    def decrypt_message(encrypted: str, symmetric_key: str) -> str

    # Asymmetric Encryption
    def encrypt_with_public_key(message: str, public_key_pem: str) -> str
    def decrypt_with_private_key(encrypted: str, private_key_pem=None) -> str

    # Message Wrapping
    def wrap_encrypted_message(message: str, recipient_public_key: str, ...) -> str
    @staticmethod
    def unwrap_encrypted_message(wrapped: str, crypto_client) -> Optional[str]
```

## Integration with A2AClient

```python
from a2a_client_async import A2AClientAsync
from a2a_crypto import CryptoClient
import json

async def secure_send():
    crypto = CryptoClient("myproject", "alice")
    async with A2AClientAsync("myproject", "alice") as a2a:
        # Publish public key
        public_key = crypto.get_public_key()
        await a2a.send("all", json.dumps({
            "type": "public_key",
            "agent": "alice",
            "key": public_key
        }))

        # Send encrypted message
        recipient_key = "..."  # from received message
        encrypted = crypto.wrap_encrypted_message("Secret", recipient_key)
        await a2a.send("bob", encrypted)

        # Receive encrypted message
        messages = await a2a.recv(unread_only=True)
        for msg in messages:
            decrypted = CryptoClient.unwrap_encrypted_message(msg["body"], crypto)
            if decrypted:
                print(f"From {msg['sender']}: {decrypted}")
```

## Use Cases

### Confidential Communications

```python
# Alice and Bob exchange sensitive information
alice_crypto = CryptoClient("myproject", "alice")
bob_crypto = CryptoClient("myproject", "bob")

# Asymmetric: Each party publishes public key
alice_public = alice_crypto.get_public_key()
bob_public = bob_crypto.get_public_key()

# Alice sends to Bob (encrypted with Bob's public key)
msg = alice_crypto.wrap_encrypted_message("Budget: $X", bob_public)
a2a.send("bob", msg)

# Bob decrypts (with his private key)
decrypted = bob_crypto.unwrap_encrypted_message(msg, bob_crypto)
```

### Shared Team Communications

```python
# Team of 5 people shares symmetric key
key = crypto.generate_symmetric_key()
# Distribute key through secure channel (not via a2a)

# All team members encrypt/decrypt with shared key
encrypted = crypto.encrypt_message("Team meeting at 3pm", key)
a2a.send("all", encrypted)

# Recipients decrypt with same key
decrypted = crypto.decrypt_message(encrypted, key)
```

### File Encryption

```python
from a2a_crypto import encrypt_file, decrypt_file

key = crypto.generate_symmetric_key()

# Encrypt sensitive file
encrypt_file("secrets.txt", key)

# Decrypt when needed
content = decrypt_file("secrets.txt", key)
```

## Key Management

### Best Practices

1. **Never share private keys** — Only distribute public keys
2. **Secure key distribution** — Use out-of-band channels for sensitive keys
3. **Rotate keys regularly** — Generate new keys periodically
4. **Store securely** — Keys stored in `~/.a2a/{project}/keys/`
5. **Environment variables** — Use env vars for key distribution in CI/CD

### Key Storage

```
~/.a2a/{project}/keys/
├── {agent_id}_private.pem      # Private key (protect!)
├── {agent_id}_public.pem       # Public key (shareable)
└── shared_key                  # Symmetric key (if used)
```

## Security Considerations

### Symmetric Encryption
- **Pros**: Fast, simple
- **Cons**: Key must be shared securely
- **Best for**: Small groups with secure key distribution

### Asymmetric Encryption
- **Pros**: Scalable, no shared key needed
- **Cons**: Slower, larger ciphertext
- **Best for**: Teams, public key infrastructure

### Limitations

1. **No perfect forward secrecy** — Compromised key reveals all messages
2. **No authentication** — Doesn't verify sender identity (use signatures for that)
3. **No replay protection** — Old messages can be resent
4. **Message metadata visible** — Sender, recipient, timestamp still unencrypted

## Algorithms

- **Symmetric**: Fernet (AES-128 CBC + HMAC)
- **Asymmetric**: RSA-2048 with OAEP-SHA256
- **Key generation**: Cryptographically secure random

## Performance

- **Symmetric encrypt/decrypt**: < 1ms
- **Asymmetric encrypt/decrypt**: 10-50ms (RSA-2048)
- **Key generation**: 100-500ms (RSA-2048)

## Troubleshooting

### "cryptography library not found"

```bash
pip install cryptography
```

### "Decryption failed: Bad token"

- Wrong key used for decryption
- Message corrupted during transmission
- Encrypted with different algorithm/version

### Key files not found

- Call `generate_keypair()` to create keys
- Check permissions on `~/.a2a/{project}/keys/`

## See Also

- [README.md](../README.md) — Project overview
- [CLIENT_API.md](CLIENT_API.md) — Python client
- [CHANGELOG.md](../CHANGELOG.md) — Release history and roadmap
