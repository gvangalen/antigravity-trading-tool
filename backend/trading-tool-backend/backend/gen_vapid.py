import json
from pywebpush import webpush, WebPushException

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    
    def generate_vapid_keys():
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        
        # Get private key in PEM format (though we need base64 for VAPID usually)
        # pywebpush can also generate them or use them.
        # Actually, pywebpush doesn't have a direct "generate" but we can use cryptography.
        
        # A simpler way with pywebpush is often just using their internal helpers if they exist, 
        # but the standard is to generate an Elliptic Curve key.
        
        # Let's use a more direct method for VAPID keys which are URL-safe Base64 encoded.
        import base64
        
        private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
        public_bytes = public_key.public_numbers().x.to_bytes(32, 'big') + public_key.public_numbers().y.to_bytes(32, 'big')
        # VAPID public key prefix is 0x04
        public_bytes = b'\x04' + public_bytes
        
        private_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').strip('=')
        public_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').strip('=')
        
        return private_b64, public_b64

    private_key, public_key = generate_vapid_keys()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("\nAdd these to your .env file.")

except ImportError:
    print("Error: cryptography and pywebpush are required. Run 'pip install cryptography pywebpush'")
